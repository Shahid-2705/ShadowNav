"""Heading-only map constraint (research/SIH26168-open-track-findings.md, Track C).

Every rule the brief names has a test here: bearing folding, candidate
agreement, junction lookahead, the 200 m self-disable, the chi-square gate, the
pipeline hook being a no-op when absent, and a synthetic end-to-end run that
shows the constraint removing gyro-bias heading drift on a straight road.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from shadownav import geo
from shadownav import pipeline_kinematic as pipeline
from shadownav.data import iovnbd
from shadownav.evaluation import masking
from shadownav.map import heading_constraint as hc
from shadownav.map import index as road_index
from shadownav.map import osm

from .conftest import synth_s_rows, write_s_csv

LAT0, LON0 = 52.881744, -1.717480
DEG_PER_M_LAT = 1.0 / 111_200.0


def _deg_lon(metres: float) -> float:
    return metres / (111_200.0 * math.cos(math.radians(LAT0)))


def _way(way_id: int, highway: str, nodes: list[tuple[int, float, float]], **tags) -> dict:
    return {
        "type": "way", "id": way_id,
        "tags": {"highway": highway, **tags},
        "nodes": [n[0] for n in nodes],
        "geometry": [{"lat": n[1], "lon": n[2]} for n in nodes],
    }


def _fixture_blob() -> dict:
    """Two roads and a footway. Node 3 is where the side road meets the main one."""
    main = [(1, LAT0, LON0), (3, LAT0, LON0 + _deg_lon(200.0)), (2, LAT0, LON0 + _deg_lon(500.0))]
    side = [(3, LAT0, LON0 + _deg_lon(200.0)), (4, LAT0 + 100.0 * DEG_PER_M_LAT, LON0 + _deg_lon(200.0))]
    foot = [(5, LAT0 - 20.0 * DEG_PER_M_LAT, LON0), (6, LAT0 - 20.0 * DEG_PER_M_LAT, LON0 + _deg_lon(500.0))]
    return {"elements": [
        _way(10, "residential", main),
        _way(11, "service", side, oneway="yes"),
        _way(12, "footway", foot),
    ]}


def _east_west_way(way_id: int, north_m: float, e0: float = -100.0, e1: float = 600.0,
                   oneway: int = 0, node_ids: tuple[int, ...] = (0, 0)) -> osm.ProjectedWay:
    return osm.ProjectedWay(
        way_id=way_id, highway="residential", oneway=oneway,
        east=np.array([e0, e1]), north=np.array([north_m, north_m]),
        node_ids=node_ids,
    )


def _index(*ways: osm.ProjectedWay, junctions: frozenset[int] = frozenset()) -> road_index.RoadIndex:
    return road_index.RoadIndex.build(ways, junctions)


def _run_epochs(constraint: hc.HeadingConstraint, east: float, north: float,
                heading_deg: float, n: int) -> list[hc.Epoch]:
    state = hc.ConstraintState()
    epochs = []
    for row in range(n):
        state, epoch = constraint.step(state, row, east, north, math.radians(heading_deg))
        epochs.append(epoch)
    return epochs


# -- OSM parsing ------------------------------------------------------------

def test_parse_keeps_roads_drops_footways_and_reads_oneway():
    net = osm.parse_overpass(_fixture_blob(), name="fixture")
    ids = {w.way_id: w for w in net.ways}
    assert set(ids) == {10, 11}, "footway must be dropped, service road kept"
    assert ids[10].oneway == 0
    assert ids[11].oneway == 1
    assert ids[10].node_ids == (1, 3, 2)
    assert ids[10].lat.shape == (3,) and ids[10].lon.shape == (3,)


def test_parse_finds_the_junction_node_by_graph_degree():
    net = osm.parse_overpass(_fixture_blob(), name="fixture")
    # Node 3 is interior to way 10 (two arms) and the end of way 11 (one arm).
    assert net.junction_nodes == frozenset({3})


def test_projected_way_uses_the_pipeline_reference():
    net = osm.parse_overpass(_fixture_blob(), name="fixture")
    ways = osm.project_network(net, LAT0, LON0)
    main = next(w for w in ways if w.way_id == 10)
    e, n = geo.lla_to_enu(net.ways[0].lat, net.ways[0].lon, LAT0, LON0)
    assert np.allclose(main.east, e) and np.allclose(main.north, n)
    # The fixture uses a spherical 111.2 km/deg; geo uses WGS84 radii (0.3 %).
    assert abs(main.east[-1] - 500.0) < 3.0


def test_bbox_from_track_pads_in_metres():
    lat = np.array([LAT0, LAT0 + 0.01, np.nan])
    lon = np.array([LON0, LON0 + 0.01, np.nan])
    box = osm.BBox.from_track(lat, lon, pad_m=300.0)
    assert box.south < LAT0 and box.north > LAT0 + 0.01
    assert abs((LAT0 - box.south) / DEG_PER_M_LAT - 300.0) < 5.0


# -- fetching ----------------------------------------------------------------

def test_fetch_never_raises_and_reports_an_unreachable_server(tmp_path: Path):
    box = osm.BBox(LAT0, LON0, LAT0 + 0.001, LON0 + 0.001)
    res = osm.fetch_highways("probe", box, tmp_path,
                             endpoints=("http://127.0.0.1:9/",), timeout_s=2.0)
    assert res.network is None
    assert res.source == "error"
    assert res.message


def test_fetch_uses_the_cache_when_present(tmp_path: Path):
    (tmp_path / "cached.json").write_text(json.dumps(_fixture_blob()), encoding="utf-8")
    box = osm.BBox(LAT0, LON0, LAT0 + 0.001, LON0 + 0.001)
    res = osm.fetch_highways("cached", box, tmp_path, endpoints=("http://127.0.0.1:9/",))
    assert res.source == "cache"
    assert res.network is not None and len(res.network.ways) == 2


# -- bearings ----------------------------------------------------------------

@pytest.mark.parametrize("deg, folded", [(90, 90), (270, 90), (-90, 90), (0, 0), (180, 0), (359, 179)])
def test_fold_bearing_maps_onto_a_half_turn(deg, folded):
    assert math.degrees(hc.fold_bearing(math.radians(deg))) == pytest.approx(folded, abs=1e-9)


def test_parallel_roads_in_opposite_senses_agree_after_folding():
    window = math.radians(5.0)
    assert hc.bearings_agree([math.radians(90), math.radians(270), math.radians(92)], window)
    assert not hc.bearings_agree([math.radians(90), math.radians(0)], window)
    assert not hc.bearings_agree([math.radians(90), math.radians(97)], window)


# -- spatial index -----------------------------------------------------------

def test_candidates_report_distance_and_both_directions():
    idx = _index(_east_west_way(1, 0.0))
    cands = idx.candidates(50.0, 10.0, radius_m=30.0)
    assert len(cands) == 1
    c = cands[0]
    assert c.distance_m == pytest.approx(10.0)
    assert sorted(round(math.degrees(b)) % 360 for b in c.bearings) == [90, 270]
    assert idx.candidates(50.0, 45.0, radius_m=30.0) == ()


def test_oneway_candidate_offers_a_single_direction():
    idx = _index(_east_west_way(1, 0.0, oneway=-1))
    (c,) = idx.candidates(50.0, 0.0, radius_m=30.0)
    assert [round(math.degrees(b)) % 360 for b in c.bearings] == [270]


# -- the constraint's rules --------------------------------------------------

def test_parallel_roads_agree_and_the_constraint_applies_after_n_epochs():
    idx = _index(_east_west_way(1, 0.0), _east_west_way(2, 8.0))
    constraint = hc.HeadingConstraint(idx, hc.HeadingConstraintConfig(min_consistent_epochs=5))
    epochs = _run_epochs(constraint, 100.0, 4.0, 88.0, 7)
    assert [e.decision for e in epochs[:4]] == [hc.Decision.WARMING] * 4
    assert epochs[4].decision is hc.Decision.APPLIED
    assert epochs[6].decision is hc.Decision.APPLIED
    assert math.degrees(epochs[6].bearing_rad) == pytest.approx(90.0)


def _crossing_at(angle_deg: float) -> osm.ProjectedWay:
    """A road through (110, 0) at ``angle_deg`` clockwise from north."""
    de, dn = 60.0 * math.sin(math.radians(angle_deg)), 60.0 * math.cos(math.radians(angle_deg))
    return osm.ProjectedWay(
        way_id=3, highway="residential", oneway=0,
        east=np.array([110.0 - de, 110.0 + de]), north=np.array([-dn, dn]), node_ids=(7, 8),
    )


def test_a_crossing_road_within_the_radius_rejects_when_all_candidates_must_agree():
    idx = _index(_east_west_way(1, 0.0), _crossing_at(0.0))
    constraint = hc.HeadingConstraint(idx, hc.HeadingConstraintConfig(gate_candidates=False))
    epochs = _run_epochs(constraint, 100.0, 4.0, 90.0, 6)
    assert all(e.decision is hc.Decision.REJECTED_DISAGREEMENT for e in epochs)


def test_gated_candidates_ignore_a_perpendicular_road_but_not_a_shallow_fork():
    cfg = hc.HeadingConstraintConfig(gate_candidates=True, gate_sigma_deg=10.0)
    perpendicular = hc.HeadingConstraint(_index(_east_west_way(1, 0.0), _crossing_at(0.0)), cfg)
    fork = hc.HeadingConstraint(_index(_east_west_way(1, 0.0), _crossing_at(70.0)), cfg)
    assert _run_epochs(perpendicular, 100.0, 4.0, 90.0, 6)[-1].decision is hc.Decision.APPLIED
    assert all(e.decision is hc.Decision.REJECTED_DISAGREEMENT
               for e in _run_epochs(fork, 100.0, 4.0, 90.0, 6))


def test_a_junction_within_the_lookahead_rejects_and_beyond_it_does_not():
    main = osm.ProjectedWay(
        way_id=1, highway="residential", oneway=0,
        east=np.array([-100.0, 130.0, 600.0]), north=np.array([0.0, 0.0, 0.0]),
        node_ids=(1, 3, 2),
    )
    idx = _index(main, junctions=frozenset({3}))
    cfg = hc.HeadingConstraintConfig(junction_lookahead_m=40.0)
    constraint = hc.HeadingConstraint(idx, cfg)
    near = _run_epochs(constraint, 100.0, 2.0, 90.0, 6)   # node 3 is 30 m ahead
    far = _run_epochs(constraint, 50.0, 2.0, 90.0, 6)     # node 3 is 80 m ahead
    behind = _run_epochs(constraint, 100.0, 2.0, 270.0, 6)  # heading away from it
    assert all(e.decision is hc.Decision.REJECTED_JUNCTION for e in near)
    assert far[-1].decision is hc.Decision.APPLIED
    assert behind[-1].decision is hc.Decision.APPLIED


def test_no_candidate_within_200m_hard_disables_and_within_it_only_skips():
    idx = _index(_east_west_way(1, 0.0))
    constraint = hc.HeadingConstraint(idx, hc.HeadingConstraintConfig())
    (off,) = _run_epochs(constraint, 100.0, 500.0, 90.0, 1)
    (near,) = _run_epochs(constraint, 100.0, 60.0, 90.0, 1)
    assert off.decision is hc.Decision.DISABLED
    assert near.decision is hc.Decision.NO_CANDIDATES
    assert off.bearing_rad is None and near.bearing_rad is None


def test_leaving_the_network_resets_the_consistency_counter():
    idx = _index(_east_west_way(1, 0.0))
    constraint = hc.HeadingConstraint(idx, hc.HeadingConstraintConfig(min_consistent_epochs=3))
    state = hc.ConstraintState()
    for row in range(3):
        state, epoch = constraint.step(state, row, 100.0, 0.0, math.radians(90))
    assert epoch.decision is hc.Decision.APPLIED
    state, epoch = constraint.step(state, 3, 100.0, 500.0, math.radians(90))
    assert epoch.decision is hc.Decision.DISABLED
    state, epoch = constraint.step(state, 4, 100.0, 0.0, math.radians(90))
    assert epoch.decision is hc.Decision.WARMING


def test_chi_square_gate_rejects_a_60_degree_innovation_at_5_degree_sigma():
    idx = _index(_east_west_way(1, 0.0))
    cfg = hc.HeadingConstraintConfig(gate_sigma_deg=5.0, min_consistent_epochs=1)
    constraint = hc.HeadingConstraint(idx, cfg)
    (bad,) = _run_epochs(constraint, 100.0, 0.0, 30.0, 1)
    (good,) = _run_epochs(constraint, 100.0, 0.0, 84.0, 1)
    assert bad.decision is hc.Decision.REJECTED_GATE
    assert good.decision is hc.Decision.APPLIED


def test_wrong_way_on_a_oneway_road_is_a_disagreement_not_a_fix():
    idx = _index(_east_west_way(1, 0.0, oneway=1))
    strict = hc.HeadingConstraint(idx, hc.HeadingConstraintConfig(min_consistent_epochs=1, gate_candidates=False))
    gated = hc.HeadingConstraint(idx, hc.HeadingConstraintConfig(min_consistent_epochs=1, gate_candidates=True))
    (epoch,) = _run_epochs(strict, 100.0, 0.0, 270.0, 1)
    assert epoch.decision is hc.Decision.REJECTED_DISAGREEMENT
    # With gated candidates the wrong-way road simply has no survivor.
    (epoch,) = _run_epochs(gated, 100.0, 0.0, 270.0, 1)
    assert epoch.decision is hc.Decision.REJECTED_GATE


def test_observer_adapter_counts_decisions_and_returns_the_hook_tuple():
    idx = _index(_east_west_way(1, 0.0))
    observer = hc.HeadingObserver(hc.HeadingConstraint(idx, hc.HeadingConstraintConfig(min_consistent_epochs=2)))
    assert observer(0, 100.0, 0.0, math.radians(90)) is None
    out = observer(1, 100.0, 0.0, math.radians(90))
    assert out is not None and math.degrees(out[0]) == pytest.approx(90.0)
    assert out[1] == pytest.approx(math.radians(observer.constraint.config.sigma_deg))
    assert observer.counts()["applied"] == 1 and observer.counts()["warming"] == 1


# -- pipeline integration ----------------------------------------------------

def test_pipeline_is_byte_identical_without_an_observer(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    a = pipeline.run(seq)
    b = pipeline.run(seq, heading_observer=None)
    for name in ("east_m", "north_m", "heading_rad", "speed_ms", "cov_xy"):
        assert np.array_equal(getattr(a, name), getattr(b, name)), name


def _straight_road_network(length_m: float) -> osm.RoadNetwork:
    blob = {"elements": [_way(1, "primary", [
        (1, LAT0, LON0 - _deg_lon(50.0)), (2, LAT0, LON0 + _deg_lon(length_m)),
    ])]}
    return osm.parse_overpass(blob, name="straight")


def test_constraint_removes_gyro_bias_drift_on_a_straight_road(tmp_path: Path):
    path = write_s_csv(tmp_path / "S-Fixture03.csv", synth_s_rows(n_rows=400, heading_deg=90.0))
    clean = iovnbd.load_s_sequence(path)
    biased = clean.with_columns(gyr_z=clean.df["gyr_z"].to_numpy(dtype=float) + 0.02)
    window = masking.make_window(biased, start_s=float(biased.time_s[50]), duration_s=30.0)
    masked = masking.apply_mask(biased, window)

    ref_lat, ref_lon = pipeline.enu_reference(masked)
    true_e, true_n = geo.lla_to_enu(
        clean.df["gps_lat_deg"].to_numpy(dtype=float),
        clean.df["gps_lon_deg"].to_numpy(dtype=float), ref_lat, ref_lon,
    )
    observer = hc.HeadingObserver.from_network(_straight_road_network(800.0), ref_lat, ref_lon)

    free = pipeline.run(masked)
    held = pipeline.run(masked, heading_observer=observer)

    k = window.end_row
    course = float(geo.heading_from_track(true_e, true_n)[k])
    cte_free = abs((free.east_m[k] - true_e[k]) * math.cos(course) - (free.north_m[k] - true_n[k]) * math.sin(course))
    cte_held = abs((held.east_m[k] - true_e[k]) * math.cos(course) - (held.north_m[k] - true_n[k]) * math.sin(course))
    assert cte_free > 10.0, "the injected bias must actually produce drift"
    assert cte_held < 0.25 * cte_free, (cte_free, cte_held)
    assert observer.counts()["applied"] > 100


def test_snap_point_projects_onto_road_segment():
    idx = _index(_east_west_way(1, north_m=50.0, e0=0.0, e1=200.0))
    # Query point at (100.0, 62.0) -> nearest road is at north=50.0
    snapped = idx.snap_point(100.0, 62.0, radius_m=30.0)
    assert snapped is not None
    se, sn, cand = snapped
    assert se == pytest.approx(100.0)
    assert sn == pytest.approx(50.0)
    assert cand.way_id == 1

    # Query point far away (> 50 m) returns None
    assert idx.snap_point(100.0, 200.0, radius_m=30.0) is None
