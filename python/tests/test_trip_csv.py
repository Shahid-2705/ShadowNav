"""Tests for the phone trip-CSV loader and the device replay script.

Two fixture layouts are generated here, both deterministic:

``v1``  the 26-column file ``TripRecorder.kt`` writes today, byte-for-byte the
        same header (``TripRecorder.HEADER``), at the UI's 10 Hz. It carries the
        filter's *estimate* and the GNSS telemetry, but no accelerometer, no
        gyroscope and no raw fix -- so it cannot be replayed through the
        pipeline, only summarised.

``raw`` the same 26 columns plus the raw-sample columns the recorder must add
        before a replay is possible: ``time_ns``, ``acc_*``, ``gyr_*`` and the
        raw ``gps_*`` fix fields, one row per IMU sample at 400 Hz. Fixes keep
        being written inside the simulated blackout, which is what makes them
        ground truth.

The drive is 60 s at 12 m/s: a straight leg, a 15 s left turn, another straight
leg, with a 20 s simulated blackout over the turn.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from shadownav import geo
from shadownav.data import trip_csv
from shadownav.data.trip_csv import TripSchemaError, load_trip, read_trip
from shadownav.utils.seed import rng

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import replay_trip  # noqa: E402

# Verbatim copy of TripRecorder.HEADER. If the app changes its header this
# string must change with it, which is the point of keeping it literal.
V1_HEADER = (
    "time_s,mode,has_fix,simulated_blackout,est_lat_deg,est_lon_deg,"
    "east_m,north_m,speed_ms,heading_deg,sigma_m,time_since_fix_s,"
    "dr_distance_m,gps_sats_used,gps_sats_visible,cn0_mean,"
    "navic_visible,navic_used,agc_db,alignment_quality,aligned,"
    "stationary,imu_hz,gps_accepted,gps_rejected,gate_overrides"
)
V1_COLUMNS = V1_HEADER.split(",")
RAW_EXTRA = [
    "time_ns", "acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z",
    "gps_lat_deg", "gps_lon_deg", "gps_speed_ms", "gps_course_deg", "gps_accuracy_m",
]

REF_LAT, REF_LON = 12.9716, 77.5946     # Bengaluru
SPEED_MS = 12.0
DURATION_S = 60.0
BLACKOUT = (30.0, 50.0)
TURN = (25.0, 40.0)
YAW_RATE = 0.1                          # rad/s, positive = left turn
GYRO_BIAS = 0.001
G = 9.80665


def _truth(t: np.ndarray) -> dict[str, np.ndarray]:
    """Kinematic ground truth on a time grid. Heading is clockwise from north
    and a positive gyro z (left turn) decreases it, matching the filter."""
    dt = np.diff(t, prepend=t[0])
    omega = np.where((t >= TURN[0]) & (t < TURN[1]), YAW_RATE, 0.0)
    psi = 0.3 - np.cumsum(omega * dt)
    east = np.cumsum(SPEED_MS * np.sin(psi) * dt)
    north = np.cumsum(SPEED_MS * np.cos(psi) * dt)
    m_rad, n_rad = geo.curvature_radii(REF_LAT)
    lat = REF_LAT + np.degrees(north / m_rad)
    lon = REF_LON + np.degrees(east / (n_rad * np.cos(np.radians(REF_LAT))))
    return {"omega": omega, "psi": psi, "east": east, "north": north, "lat": lat, "lon": lon}


def _fix_rows(t: np.ndarray, period_s: float = 1.0) -> np.ndarray:
    """First row at or after each whole second: where the recorder writes a fix."""
    edges = np.arange(0.0, t[-1] + 1e-9, period_s)
    return np.unique(np.searchsorted(t, edges, side="left"))


def _v1_frame(t: np.ndarray, blackout: tuple[float, float] | None = BLACKOUT) -> pd.DataFrame:
    """The app's 26 columns: estimate, mode machine and telemetry."""
    tr = _truth(t)
    n = len(t)
    in_bo = np.zeros(n, dtype=bool) if blackout is None else (t >= blackout[0]) & (t < blackout[1])
    since = np.where(in_bo, t - (blackout[0] if blackout else 0.0), 0.0)
    mode = np.where(since > 1.0, "DEAD_RECKONING", "AIDED").astype(object)
    if blackout is not None:
        mode[(t >= blackout[1]) & (t < blackout[1] + 2.0)] = "REACQUIRING"
    # The app's estimate drifts cross-track at 0.3 m/s while dead reckoning.
    drift = np.where(in_bo, 0.3 * since, 0.0)
    est_e = tr["east"] + drift * np.cos(tr["psi"])
    est_n = tr["north"] - drift * np.sin(tr["psi"])
    return pd.DataFrame({
        "time_s": np.round(t, 3),
        "mode": mode,
        "has_fix": 1,
        "simulated_blackout": in_bo.astype(int),
        "est_lat_deg": tr["lat"], "est_lon_deg": tr["lon"],
        "east_m": est_e, "north_m": est_n,
        "speed_ms": SPEED_MS, "heading_deg": np.degrees(tr["psi"]) % 360.0,
        "sigma_m": 5.0 + 0.8 * since,
        "time_since_fix_s": since,
        "dr_distance_m": SPEED_MS * since,
        "gps_sats_used": 12, "gps_sats_visible": 18, "cn0_mean": 35.0,
        "navic_visible": 2, "navic_used": 0, "agc_db": np.nan,
        "alignment_quality": 0.0, "aligned": 0, "stationary": 0,
        "imu_hz": 401.0, "gps_accepted": 0, "gps_rejected": 0, "gate_overrides": 0,
    })[V1_COLUMNS]


def _raw_frame(
    rate_hz: float = 400.0, blackout: tuple[float, float] | None = BLACKOUT,
    seed: int = 7, log_fixes_in_blackout: bool = True,
) -> pd.DataFrame:
    """v1 columns plus raw IMU at ``rate_hz`` and a raw fix every second."""
    gen = rng(seed)
    n = int(DURATION_S * rate_hz)
    step_ns = int(round(1e9 / rate_hz))
    jitter = gen.integers(-50_000, 50_000, size=n)
    t_ns = 1_000_000_000_000 + np.arange(n) * step_ns + jitter
    t_ns[int(10 * rate_hz):] += 12_000_000       # one 12 ms hiccup at t = 10 s
    t = (t_ns - t_ns[0]) / 1e9
    tr = _truth(t)
    df = _v1_frame(t, blackout)
    df["time_ns"] = t_ns
    df["acc_x"] = -SPEED_MS * tr["omega"] + gen.normal(0.0, 0.02, n)
    df["acc_y"] = gen.normal(0.0, 0.02, n)
    df["acc_z"] = G + gen.normal(0.0, 0.02, n)
    df["gyr_x"] = gen.normal(0.0, 0.001, n)
    df["gyr_y"] = gen.normal(0.0, 0.001, n)
    df["gyr_z"] = tr["omega"] + GYRO_BIAS + gen.normal(0.0, 0.001, n)
    for col in ("gps_lat_deg", "gps_lon_deg", "gps_speed_ms", "gps_course_deg", "gps_accuracy_m"):
        df[col] = np.nan
    rows = _fix_rows(t)
    if blackout is not None and not log_fixes_in_blackout:
        rows = rows[(t[rows] < blackout[0]) | (t[rows] >= blackout[1])]
    df.loc[rows, "gps_lat_deg"] = tr["lat"][rows] + gen.normal(0.0, 2e-6, rows.size)
    df.loc[rows, "gps_lon_deg"] = tr["lon"][rows] + gen.normal(0.0, 2e-6, rows.size)
    df.loc[rows, "gps_speed_ms"] = SPEED_MS
    df.loc[rows, "gps_course_deg"] = np.degrees(tr["psi"][rows]) % 360.0
    df.loc[rows, "gps_accuracy_m"] = 4.0
    return df[V1_COLUMNS + RAW_EXTRA]


def _write(df: pd.DataFrame, path: Path) -> Path:
    df.to_csv(path, index=False, float_format="%.9g", lineterminator="\n")
    return path


@pytest.fixture(scope="module")
def raw_df() -> pd.DataFrame:
    return _raw_frame()


@pytest.fixture(scope="module")
def raw_path(tmp_path_factory, raw_df) -> Path:
    return _write(raw_df, tmp_path_factory.mktemp("trip") / "shadownav-raw.csv")


@pytest.fixture(scope="module")
def v1_path(tmp_path_factory) -> Path:
    t = np.arange(0.0, DURATION_S, 0.1)
    return _write(_v1_frame(t), tmp_path_factory.mktemp("trip") / "shadownav-v1.csv")


# ---------------------------------------------------------------- parsing


def test_v1_layout_is_read_but_not_replayable(v1_path):
    trip = read_trip(v1_path)
    assert trip.info.has_imu is False
    assert trip.info.has_raw_gnss is False
    assert trip.info.replayable is False
    assert trip.info.time_unit == "s"
    assert trip.sequence.sample_rate_hz == pytest.approx(10.0, rel=1e-3)
    assert "app_east_m" in trip.sequence.df.columns
    assert trip.sequence.df["app_mode"].iloc[0] == "AIDED"
    # No raw fix -> no ground truth rows at all.
    assert not trip.sequence.df["gps_fix_is_new"].any()
    assert np.isnan(trip.sequence.df["gps_lat_deg"]).all()


def test_raw_layout_units_and_rate(raw_path):
    trip = read_trip(raw_path)
    seq = trip.sequence
    assert trip.info.time_unit == "ns"
    assert trip.info.replayable is True
    assert seq.time_s[0] == 0.0
    assert seq.duration_s == pytest.approx(DURATION_S, abs=0.05)
    assert trip.info.imu_rate_hz == pytest.approx(400.0, rel=0.01)
    assert trip.info.max_gap_ms == pytest.approx(14.5, abs=0.2)
    assert seq.df["acc_z"].mean() == pytest.approx(G, abs=0.01)
    assert seq.df["gps_speed_ms"].dropna().iloc[0] == SPEED_MS
    assert trip.info.gnss_period_s == pytest.approx(1.0, abs=0.01)


def test_time_in_milliseconds_is_detected(tmp_path, raw_df):
    df = raw_df.drop(columns=["time_ns"]).copy()
    df["time_ms"] = (raw_df["time_ns"] - raw_df["time_ns"].iloc[0]) / 1e6
    trip = read_trip(_write(df, tmp_path / "ms.csv"))
    assert trip.info.time_unit == "ms"
    assert trip.sequence.duration_s == pytest.approx(DURATION_S, abs=0.05)


def test_unitless_timestamp_falls_back_to_magnitude(tmp_path, raw_df):
    df = raw_df.rename(columns={"time_ns": "timestamp"}).drop(columns=["time_s"])
    trip = read_trip(_write(df, tmp_path / "unitless.csv"))
    assert trip.info.time_unit == "ns"
    assert trip.sequence.duration_s == pytest.approx(DURATION_S, abs=0.05)


def test_fix_detection_marks_only_genuine_position_changes(raw_path, raw_df):
    seq = load_trip(raw_path)
    written = raw_df["gps_lat_deg"].notna().sum()
    assert int(seq.df["gps_fix_is_new"].sum()) == written
    # Fix values are held forward for at most GNSS_HOLD_S so the estimator
    # sees a fix between arrivals, but the held rows are never "new".
    held = seq.df["gps_lat_deg"].notna().sum()
    assert held > written
    new_rows = np.flatnonzero(seq.df["gps_fix_is_new"].to_numpy())
    assert np.all(np.diff(seq.time_s[new_rows]) > 0.9)


def test_repeated_fix_is_not_a_new_fix(tmp_path, raw_df):
    df = raw_df.copy()
    rows = np.flatnonzero(df["gps_lat_deg"].notna().to_numpy())
    # Repeat fix #3 verbatim on the row of fix #4: the receiver re-reported it.
    for col in ("gps_lat_deg", "gps_lon_deg"):
        df.loc[rows[4], col] = df.loc[rows[3], col]
    seq = load_trip(_write(df, tmp_path / "repeat.csv"))
    assert int(seq.df["gps_fix_is_new"].sum()) == rows.size - 1


# ------------------------------------------------------------------ mask


def test_mask_recovered_from_simulated_blackout_column(raw_path):
    trip = read_trip(raw_path)
    assert trip.info.mask_source == "simulated_blackout column"
    assert len(trip.info.spans) == 1
    span = trip.info.spans[0]
    assert span.start_s == pytest.approx(BLACKOUT[0], abs=0.01)
    assert span.duration_s == pytest.approx(BLACKOUT[1] - BLACKOUT[0], abs=0.01)
    assert span.n_fixes_inside == 20
    avail = trip.sequence.df["gnss_available"].to_numpy()
    assert not avail[span.start_row:span.end_row].any()
    assert avail[span.start_row - 1] and avail[span.end_row + 5]
    # The fixes inside remain in the frame: they are the ground truth.
    assert trip.sequence.df["gps_fix_is_new"].to_numpy()[span.start_row:span.end_row].sum() == 20


def test_mask_derived_from_gnss_gaps_when_column_absent(tmp_path):
    df = _raw_frame(log_fixes_in_blackout=False).drop(columns=["simulated_blackout"])
    trip = read_trip(_write(df, tmp_path / "nocol.csv"))
    assert trip.info.mask_source.startswith("gnss-unavailable spans")
    assert len(trip.info.spans) == 1
    span = trip.info.spans[0]
    # The gap starts one hold period after the last fix before the blackout.
    assert span.start_s == pytest.approx(BLACKOUT[0] - 1.0 + trip_csv.GNSS_HOLD_S, abs=0.05)
    assert span.end_s == pytest.approx(BLACKOUT[1], abs=0.05)
    assert span.n_fixes_inside == 0


# ------------------------------------------------------ timestamp hygiene


def test_duplicate_timestamps_are_dropped(tmp_path, raw_df):
    df = pd.concat([raw_df.iloc[:100], raw_df.iloc[50:60], raw_df.iloc[100:]])
    df = df.sort_values("time_ns", kind="stable").reset_index(drop=True)
    trip = read_trip(_write(df, tmp_path / "dup.csv"))
    assert trip.info.duplicate_rows_dropped == 10
    assert len(trip.sequence) == len(raw_df)
    assert np.all(np.diff(trip.sequence.time_s) > 0)


def test_non_monotonic_time_fails_fast(tmp_path, raw_df):
    df = raw_df.copy()
    df.loc[500, "time_ns"] = df.loc[400, "time_ns"] - 1
    with pytest.raises(TripSchemaError, match="not strictly increasing.*row 500"):
        load_trip(_write(df, tmp_path / "back.csv"))


# ------------------------------------------------------ column resolution


def test_shuffled_header_resolves_identically(tmp_path, raw_df, raw_path):
    cols = list(raw_df.columns)
    order = rng(3).permutation(len(cols))
    shuffled = raw_df[[cols[i] for i in order]]
    a = load_trip(raw_path).df
    b = load_trip(_write(shuffled, tmp_path / "shuffled.csv")).df
    for col in ("acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z",
                "gps_lat_deg", "gps_lon_deg", "app_east_m", "time_s"):
        np.testing.assert_array_equal(a[col].to_numpy(), b[col].to_numpy(), err_msg=col)


def test_inserted_column_cannot_shift_imu_into_wrong_field(tmp_path, raw_df, raw_path):
    df = raw_df.copy()
    df.insert(loc=list(df.columns).index("acc_y"), column="magnetometer_x", value=1.0)
    a = load_trip(raw_path).df
    b = load_trip(_write(df, tmp_path / "inserted.csv")).df
    np.testing.assert_array_equal(a["acc_y"].to_numpy(), b["acc_y"].to_numpy())
    np.testing.assert_array_equal(a["gyr_z"].to_numpy(), b["gyr_z"].to_numpy())


def test_ambiguous_column_is_a_hard_error(tmp_path, raw_df):
    df = raw_df.copy()
    df["accel_x"] = df["acc_x"]
    with pytest.raises(TripSchemaError, match="ambiguous"):
        load_trip(_write(df, tmp_path / "ambiguous.csv"))


def test_partial_imu_is_a_hard_error(tmp_path, raw_df):
    with pytest.raises(TripSchemaError, match="gyr_z"):
        load_trip(_write(raw_df.drop(columns=["gyr_z"]), tmp_path / "partial.csv"))


def test_missing_time_column_is_a_hard_error(tmp_path, raw_df):
    df = raw_df.drop(columns=["time_ns", "time_s"])
    with pytest.raises(TripSchemaError, match="time column"):
        load_trip(_write(df, tmp_path / "notime.csv"))


def test_load_never_mutates_the_frame_it_returns_from(raw_path):
    trip = read_trip(raw_path)
    before = trip.sequence.df.copy()
    _ = replay_trip.replay(raw_path, horizons=(), out=None, factors={})
    pd.testing.assert_frame_equal(before, trip.sequence.df)


# ----------------------------------------------------------------- replay


@pytest.fixture(scope="module")
def raw_report(raw_path, tmp_path_factory) -> dict:
    out = tmp_path_factory.mktemp("results") / "device_replay_test.json"
    return replay_trip.replay(raw_path, horizons=(), out=out, factors={10.0: 2.0, 30.0: 3.0})


def test_replay_scores_the_recorded_blackout(raw_report):
    assert raw_report["method"] == "device_replay"
    assert raw_report["device"]["replayable"] is True
    recorded = [r for r in raw_report["results"] if r["kind"] == "recorded"]
    assert len(recorded) == 1
    r = recorded[0]
    assert np.isfinite(r["crse_m"]) and r["crse_m"] >= 0.0
    assert r["horizon_s"] == pytest.approx(20.0, abs=0.01)
    assert r["n_fixes_suppressed"] >= 20
    assert r["distance_m"] == pytest.approx(SPEED_MS * r["t_eval_s"], rel=0.05)
    assert r["meets_10pct_target"] == (r["drift_pct"] < 10.0)
    # Ideal-ish IMU on a 240 m span: the estimator must at least beat 10 %.
    assert r["drift_pct"] < 10.0, r
    assert r["detection_latency_s"] == pytest.approx(1.0, abs=0.05)
    assert np.isfinite(r["reacq_snap_m"]) and np.isfinite(r["reacq_max_step_m"])
    assert r["radius90_cal_m"] == pytest.approx(3.0 * r["radius90_raw_m"], rel=1e-9)


def test_replay_json_schema_and_device_block(raw_report, raw_path):
    d = raw_report["device"]
    assert d["imu_rate_hz_measured"] == pytest.approx(400.0, rel=0.01)
    assert d["imu_max_gap_ms"] == pytest.approx(14.5, abs=0.2)
    assert d["mask_source"] == "simulated_blackout column"
    assert d["n_recorded_blackouts"] == 1
    assert d["ground_truth"].startswith("recorded fixes")
    assert set(raw_report) >= {"method", "seed", "n_sequences", "n_outages", "summary", "results", "device"}
    written = json.loads((raw_path.parent.parent / "results0" / "device_replay_test.json").read_text())
    assert written["n_outages"] == raw_report["n_outages"]


def test_synthetic_outages_on_continuous_gnss(tmp_path):
    path = _write(_raw_frame(blackout=None), tmp_path / "plain.csv")
    report = replay_trip.replay(path, horizons=(10.0,), out=None, factors={})
    assert report["device"]["n_recorded_blackouts"] == 0
    synthetic = [r for r in report["results"] if r["kind"] == "synthetic"]
    assert len(synthetic) >= 2
    assert all(np.isfinite(r["crse_m"]) for r in synthetic)
    assert all(r["horizon_s"] == 10.0 for r in synthetic)
    # extend_to_row: the scoring fix itself was hidden, so at least one
    # more fix than the horizon holds was suppressed.
    assert all(r["n_fixes_suppressed"] >= 10 for r in synthetic)
    assert "10.0" in report["summary"]


def test_synthetic_outages_skip_recorded_blackouts(raw_path):
    report = replay_trip.replay(raw_path, horizons=(10.0,), out=None, factors={})
    spans = report["device"]["recorded_blackouts"]
    for r in report["results"]:
        if r["kind"] != "synthetic":
            continue
        for s in spans:
            overlap = r["start_s"] < s["end_s"] and r["start_s"] + r["t_eval_s"] > s["start_s"]
            assert not overlap, (r, s)


def test_v1_replay_reports_self_consistency_only(v1_path):
    report = replay_trip.replay(v1_path, horizons=(10.0,), out=None, factors={30.0: 4.0})
    assert report["device"]["replayable"] is False
    assert report["results"] == []
    assert report["device"]["ground_truth"].startswith("none")
    sc = report["device"]["self_consistency"]
    assert len(sc) == 1
    assert sc[0]["app_dr_distance_m"] == pytest.approx(SPEED_MS * 19.9, rel=0.02)
    assert sc[0]["app_detection_latency_s"] == pytest.approx(1.1, abs=0.15)
    assert sc[0]["app_radius90_cal_m"] == pytest.approx(4.0 * 2.146 * (5.0 + 0.8 * 19.9), rel=0.02)
    assert sc[0]["app_reacq_settle_s"] == pytest.approx(2.0, abs=0.15)


def test_cli_writes_default_output(tmp_path, raw_path, monkeypatch):
    monkeypatch.setattr(replay_trip, "RESULTS_DIR", tmp_path)
    assert replay_trip.main([str(raw_path)]) == 0
    out = tmp_path / "device_replay_shadownav-raw.json"
    assert out.exists()
    assert json.loads(out.read_text())["method"] == "device_replay"


def test_replay_with_modular_map_matching(raw_path):
    from shadownav.map import osm
    # Build a simple road network around the synthetic trip's start position
    blob = {
        "elements": [
            {
                "type": "way",
                "id": 101,
                "tags": {"highway": "primary"},
                "nodes": [1, 2],
                "geometry": [
                    {"lat": REF_LAT - 0.01, "lon": REF_LON},
                    {"lat": REF_LAT + 0.01, "lon": REF_LON + 0.01},
                ],
            }
        ]
    }
    net = osm.parse_overpass(blob, name="synth_net")
    report = replay_trip.replay(raw_path, horizons=(10.0,), osm_network=net)
    assert report["n_outages"] >= 1
    # Check that map matching evaluated modularly alongside raw EKF
    for res in report["results"]:
        if "map_matched_drift_m" in res:
            assert isinstance(res["map_matched_drift_m"], float)
            assert "map_decisions" in res


# ------------------------------------------------------- real recordings


def _real_trips() -> list[Path]:
    root = Path(__file__).resolve().parents[2]
    found = []
    for base in (root / "android", root / "data"):
        found.extend(p for p in base.rglob("shadownav-*.csv") if p.is_file())
    return found


@pytest.mark.parametrize("path", _real_trips() or [None])
def test_real_trip_smoke(path):
    if path is None:
        pytest.skip("no shadownav-*.csv recorded by the app exists under android/ or data/")
    trip = read_trip(path)
    assert len(trip.sequence) > 10
    assert np.all(np.diff(trip.sequence.time_s) > 0)
