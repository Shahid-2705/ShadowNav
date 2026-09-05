"""Geodesy, masking, metrics and the naive strapdown baseline.

The load-bearing test in this file is
:func:`test_strapdown_reproduces_a_clean_trajectory`. Without it, "the naive
baseline drifts badly on real data" is not evidence of anything -- a broken
integrator also drifts badly. Proving the integrator is correct on coherent
synthetic data is what makes its failure on real data meaningful.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from shadownav import geo
from shadownav.baselines import naive
from shadownav.data import iovnbd
from shadownav.evaluation import masking, metrics
from shadownav.utils import seed as seedmod


# --------------------------------------------------------------------------
# geo
# --------------------------------------------------------------------------

def test_meridional_radius_is_always_the_smaller():
    """Measured at 53N: 6376234 m and 6391797 m, a 0.24% difference.

    Both exceed the 6371 km mean radius, so a single spherical radius is wrong
    in the same direction for both axes -- which is why lla_to_enu uses the
    two proper radii rather than one.
    """
    m, n = geo.curvature_radii(53.0)
    assert m < n
    assert m == pytest.approx(6376234.0, abs=50.0)
    assert n == pytest.approx(6391797.0, abs=50.0)
    assert 0.002 < (n - m) / n < 0.003


def test_enu_origin_is_the_first_sample():
    e, n = geo.lla_to_enu(np.array([52.0, 52.001]), np.array([-1.0, -1.0]))
    assert e[0] == pytest.approx(0.0)
    assert n[0] == pytest.approx(0.0)


def test_one_millidegree_of_latitude_is_about_111_metres():
    _, n = geo.lla_to_enu(np.array([53.0, 53.001]), np.array([0.0, 0.0]))
    assert n[1] == pytest.approx(111.2, abs=0.5)


def test_longitude_scale_shrinks_with_latitude():
    e_lo, _ = geo.lla_to_enu(np.array([0.0, 0.0]), np.array([0.0, 0.001]))
    e_hi, _ = geo.lla_to_enu(np.array([60.0, 60.0]), np.array([0.0, 0.001]))
    assert e_hi[1] == pytest.approx(e_lo[1] * math.cos(math.radians(60.0)), rel=0.01)


def test_heading_from_track_is_clockwise_from_north():
    # Due east: heading = +90 degrees.
    e = np.array([0.0, 1.0, 2.0])
    n = np.array([0.0, 0.0, 0.0])
    assert geo.heading_from_track(e, n)[0] == pytest.approx(math.pi / 2)
    # Due north: heading = 0.
    assert geo.heading_from_track(n, e)[0] == pytest.approx(0.0)


def test_path_length_of_a_unit_square():
    e = np.array([0.0, 1.0, 1.0, 0.0, 0.0])
    n = np.array([0.0, 0.0, 1.0, 1.0, 0.0])
    assert geo.path_length(e, n) == pytest.approx(4.0)


# --------------------------------------------------------------------------
# determinism gate
# --------------------------------------------------------------------------

def test_rng_is_reproducible_from_the_seed_alone():
    a = seedmod.rng(123).normal(size=64)
    b = seedmod.rng(123).normal(size=64)
    np.testing.assert_array_equal(a, b)


def test_different_seeds_differ():
    a = seedmod.rng(1).normal(size=32)
    b = seedmod.rng(2).normal(size=32)
    assert not np.allclose(a, b)


# --------------------------------------------------------------------------
# masking
# --------------------------------------------------------------------------

def test_outage_plan_is_deterministic(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    a = masking.plan_outages(seq, 5.0, n=3, seed=42)
    b = masking.plan_outages(seq, 5.0, n=3, seed=42)
    assert [w.start_s for w in a] == [w.start_s for w in b]


def test_masking_does_not_mutate_the_source(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    before = seq.df["gps_lat_deg"].to_numpy().copy()
    w = masking.make_window(seq, 5.0, 10.0)
    masked = masking.apply_mask(seq, w)
    np.testing.assert_array_equal(seq.df["gps_lat_deg"].to_numpy(), before)
    assert masked.df["gps_lat_deg"].isna().sum() > 0


def test_masked_rows_keep_imu_and_timestamps(s_csv_straight: Path):
    """The estimator must keep running at 10 Hz through the outage."""
    seq = iovnbd.load_s_sequence(s_csv_straight)
    masked = masking.apply_mask(seq, masking.make_window(seq, 5.0, 10.0))
    assert len(masked) == len(seq)
    np.testing.assert_array_equal(masked.time_s, seq.time_s)
    assert masked.df["acc_x"].notna().all()
    assert masked.df["gyr_z"].notna().all()


def test_window_counts_the_fixes_it_actually_suppressed(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    w = masking.make_window(seq, 5.0, 10.0)
    # Fixture GPS updates every 10 rows = 1 s, so a 10 s outage hides ~10 fixes.
    assert w.n_fixes_suppressed == pytest.approx(10, abs=1)
    assert w.informative


def test_an_outage_hiding_no_fix_is_flagged_uninformative(s_csv_straight: Path):
    """Given the real 9 s fix period, short horizons produce these routinely."""
    seq = iovnbd.load_s_sequence(s_csv_straight)
    w = masking.OutageWindow(
        sequence=seq.name, start_s=1.0, duration_s=0.5,
        start_row=11, end_row=12, n_fixes_suppressed=0, distance_m=5.0,
    )
    assert not w.informative


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------

def test_resultant_error_is_euclidean():
    err = metrics.resultant_error(
        np.array([3.0]), np.array([4.0]), np.array([0.0]), np.array([0.0])
    )
    assert err[0] == pytest.approx(5.0)


def test_cross_track_error_is_perpendicular_only():
    # Travelling due north (course 0). A purely along-track error has zero CTE.
    assert metrics.cross_track_error(0.0, 10.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)
    # A purely eastward error is entirely cross-track.
    assert metrics.cross_track_error(7.0, 0.0, 0.0, 0.0, 0.0) == pytest.approx(7.0)


def test_cross_track_error_rotates_with_course():
    # Travelling due east (course pi/2): a northward error is cross-track.
    assert metrics.cross_track_error(
        0.0, 7.0, 0.0, 0.0, math.pi / 2
    ) == pytest.approx(7.0)


def test_nees_of_a_unit_error_under_unit_covariance_is_two():
    err = np.array([[1.0, 1.0]])
    cov = np.array([np.eye(2)])
    assert metrics.nees(err, cov) == pytest.approx(2.0)


def test_nees_detects_overconfidence():
    err = np.array([[3.0, 0.0]])
    tight = np.array([np.eye(2) * 0.25])
    assert metrics.nees(err, tight) > 2.0


def test_evaluate_window_returns_none_when_no_truth_exists_at_the_horizon():
    """A real outcome on this dataset, not an error -- fixes are 9 s apart."""
    t = np.arange(0.0, 5.0, 0.1)
    z = np.zeros_like(t)
    out = metrics.evaluate_window(
        sequence="x", method="m", horizon_s=180.0, time_s=t,
        est_e=z, est_n=z, true_e=z, true_n=z,
        fix_rows=np.array([0, 10]), start_row=0,
        distance_m=100.0, n_fixes_suppressed=1,
    )
    assert out is None


# --------------------------------------------------------------------------
# the naive strapdown baseline
# --------------------------------------------------------------------------

def test_initial_attitude_is_a_proper_rotation():
    acc = np.array([[0.0, 0.0, 9.80665]])
    for heading in (0.0, 0.7, math.pi / 2, 3.0, -2.0):
        r = naive.initial_attitude(acc, heading)
        np.testing.assert_allclose(r @ r.T, np.eye(3), atol=1e-9)
        assert np.linalg.det(r) == pytest.approx(1.0), "reflection, not rotation"


def test_initial_attitude_maps_body_forward_to_the_requested_heading():
    acc = np.array([[0.0, 0.0, 9.80665]])
    for heading in (0.0, math.pi / 2, math.pi, -math.pi / 4):
        r = naive.initial_attitude(acc, heading)
        fwd_nav = r @ np.array([0.0, 1.0, 0.0])
        assert fwd_nav[0] == pytest.approx(math.sin(heading), abs=1e-9)
        assert fwd_nav[1] == pytest.approx(math.cos(heading), abs=1e-9)


def test_initial_attitude_maps_body_up_to_nav_up():
    r = naive.initial_attitude(np.array([[0.0, 0.0, 9.80665]]), 1.1)
    np.testing.assert_allclose(r @ np.array([0.0, 0.0, 1.0]), [0, 0, 1], atol=1e-9)


@pytest.mark.parametrize("fixture,yaw_dps", [("s_csv_straight", 0.0), ("s_csv_turning", 6.0)])
def test_strapdown_reproduces_a_clean_trajectory(request, fixture: str, yaw_dps: float):
    """The integrator must be correct before its failure on real data means anything.

    On noise-free-ish synthetic data with exact initial conditions, 20 s of
    strapdown integration should track the truth to within a few metres. If this
    regresses, every drift number reported downstream is measuring a bug.
    """
    path = request.getfixturevalue(fixture)
    seq = iovnbd.load_s_sequence(path)

    true_e, true_n = geo.lla_to_enu(
        seq.df["gps_lat_deg"].to_numpy(), seq.df["gps_lon_deg"].to_numpy()
    )
    start, end = 20, 220  # 20 s of integration at 10 Hz

    # Exact initial attitude: this test validates the integrator, and the
    # aligner is tested separately below. Levelling from a turning vehicle's
    # mean specific force is a genuine 200 m failure mode, not something to
    # smuggle into an integrator test.
    psi0 = math.radians(float(seq.df["gps_orientation_deg"].iloc[start]))
    c, s_ = math.cos(psi0), math.sin(psi0)
    r0 = np.array([[c, s_, 0.0], [-s_, c, 0.0], [0.0, 0.0, 1.0]])

    out = naive.dead_reckon(
        seq, start, end,
        init_speed_ms=float(seq.df["gps_speed_ms"].iloc[start]),
        init_heading_rad=psi0,
        init_rotation=r0,
    )

    err = math.hypot(
        out.east_m[-1] - (true_e[end] - true_e[start]),
        out.north_m[-1] - (true_n[end] - true_n[start]),
    )
    travelled = float(seq.df["gps_speed_ms"].iloc[start]) * (
        seq.time_s[end] - seq.time_s[start]
    )
    assert err < 0.05 * travelled, (
        f"strapdown diverged {err:.1f} m over {travelled:.0f} m "
        f"({100 * err / travelled:.1f}%) on clean synthetic data -- "
        f"the integrator or a sign convention is wrong"
    )


def test_strapdown_output_shapes_and_finiteness(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    out = naive.dead_reckon(seq, 10, 110, init_speed_ms=10.0, init_heading_rad=0.0)
    assert out.east_m.shape == out.north_m.shape == (101,)
    for arr in (out.east_m, out.north_m, out.speed_ms, out.heading_rad):
        assert np.all(np.isfinite(arr))
