"""Fair comparators and the PS-graded transition metrics.

The naive strapdown floor is the denominator every claim was measured against,
but nobody ships double integration. A judge's first question is "how does
this compare with simply freezing the last fix?" -- and the second is "what
happens on the map when GPS comes back?". These tests pin down the three
comparators and the metrics that answer both, on the synthetic fixtures whose
truth is known exactly.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from shadownav import geo
from shadownav import pipeline_kinematic as pipeline
from shadownav.baselines import constant_velocity, freeze, gyro_heading
from shadownav.data import iovnbd
from shadownav.evaluation import compare, conformal, masking, metrics


# --------------------------------------------------------------------------
# comparators
# --------------------------------------------------------------------------

def test_freeze_never_moves(s_csv_straight):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    out = freeze.dead_reckon(seq, 20, 220, init_speed_ms=10.0, init_heading_rad=1.0)
    assert len(out.east_m) == 201
    assert np.all(out.east_m == 0.0)
    assert np.all(out.north_m == 0.0)
    assert np.all(out.speed_ms == 0.0)
    assert out.heading_rad[-1] == pytest.approx(1.0)


def test_constant_velocity_reproduces_a_straight_drive(s_csv_straight):
    """36 km/h due east for 20 s: the CV comparator must land within 1 m."""
    seq = iovnbd.load_s_sequence(s_csv_straight)
    true_e, true_n = geo.lla_to_enu(
        seq.df["gps_lat_deg"].to_numpy(), seq.df["gps_lon_deg"].to_numpy()
    )
    start, end = 20, 220
    psi0 = math.radians(float(seq.df["gps_orientation_deg"].iloc[start]))
    v0 = float(seq.df["gps_speed_ms"].iloc[start])
    out = constant_velocity.dead_reckon(seq, start, end, init_speed_ms=v0, init_heading_rad=psi0)
    err = math.hypot(
        out.east_m[-1] - (true_e[end] - true_e[start]),
        out.north_m[-1] - (true_n[end] - true_n[start]),
    )
    assert err < 1.0
    assert out.speed_ms[-1] == pytest.approx(v0)
    assert out.heading_rad[-1] == pytest.approx(psi0)


def test_constant_velocity_cannot_follow_a_turn(s_csv_turning):
    """On a 6 deg/s turn the straight-line comparator must miss by metres.

    If it did not, the gyro-heading comparator would have nothing to add and
    the comparison between them would be meaningless.
    """
    seq = iovnbd.load_s_sequence(s_csv_turning)
    true_e, true_n = geo.lla_to_enu(
        seq.df["gps_lat_deg"].to_numpy(), seq.df["gps_lon_deg"].to_numpy()
    )
    start, end = 20, 220
    psi0 = math.radians(float(seq.df["gps_orientation_deg"].iloc[start]))
    v0 = float(seq.df["gps_speed_ms"].iloc[start])
    out = constant_velocity.dead_reckon(seq, start, end, init_speed_ms=v0, init_heading_rad=psi0)
    err = math.hypot(
        out.east_m[-1] - (true_e[end] - true_e[start]),
        out.north_m[-1] - (true_n[end] - true_n[start]),
    )
    assert err > 20.0


def test_gyro_heading_follows_a_turn_with_speed_held(s_csv_turning):
    """Speed held, heading from the gyroscope alone: within 5% on a clean turn.

    The sign convention is the one the kinematic EKF uses -- heading rate is
    minus the gyro rate about the vehicle's up axis -- so a sign error here
    would mirror the arc and fail by the full chord.
    """
    seq = iovnbd.load_s_sequence(s_csv_turning)
    true_e, true_n = geo.lla_to_enu(
        seq.df["gps_lat_deg"].to_numpy(), seq.df["gps_lon_deg"].to_numpy()
    )
    start, end = 20, 220
    psi0 = math.radians(float(seq.df["gps_orientation_deg"].iloc[start]))
    v0 = float(seq.df["gps_speed_ms"].iloc[start])
    out = gyro_heading.dead_reckon(seq, start, end, init_speed_ms=v0, init_heading_rad=psi0)
    err = math.hypot(
        out.east_m[-1] - (true_e[end] - true_e[start]),
        out.north_m[-1] - (true_n[end] - true_n[start]),
    )
    travelled = v0 * float(seq.time_s[end] - seq.time_s[start])
    assert err < 0.05 * travelled, f"{err:.1f} m over {travelled:.0f} m"
    # 20 s at 6 deg/s is 120 deg of heading change.
    turned = math.degrees(geo.wrap_angle(out.heading_rad[-1] - psi0))
    assert turned == pytest.approx(120.0, abs=3.0)


def test_gyro_heading_equals_constant_velocity_on_a_straight(s_csv_straight):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    start, end = 20, 220
    psi0 = math.radians(float(seq.df["gps_orientation_deg"].iloc[start]))
    v0 = float(seq.df["gps_speed_ms"].iloc[start])
    a = constant_velocity.dead_reckon(seq, start, end, init_speed_ms=v0, init_heading_rad=psi0)
    b = gyro_heading.dead_reckon(seq, start, end, init_speed_ms=v0, init_heading_rad=psi0)
    assert math.hypot(a.east_m[-1] - b.east_m[-1], a.north_m[-1] - b.north_m[-1]) < 1.0


# --------------------------------------------------------------------------
# transition metrics
# --------------------------------------------------------------------------

def _synthetic_transition(snap_at_fix: bool):
    """Ten seconds at 10 Hz, straight north at 10 m/s.

    Mask from row 20 to row 50; a real fix lands at row 60; the estimator is
    30 m east of truth by then. The display reacts one sample after the fix,
    as the real pipeline does through its re-acquisition dwell: if
    ``snap_at_fix`` it jumps onto the fix track at row 61, otherwise it slides
    3 m per sample over ten samples.
    """
    n = 100
    t = np.arange(n) * 0.1
    true_e = np.zeros(n)
    true_n = 10.0 * t
    est_e = np.zeros(n)
    est_n = true_n.copy()
    est_e[20:61] = np.linspace(0.0, 30.0, 41)
    if snap_at_fix:
        est_e[61:] = 0.0
    else:
        est_e[61:71] = np.linspace(30.0, 0.0, 10, endpoint=False) - 3.0
        est_e[71:] = 0.0
    speed = np.full(n, 10.0)
    mode = np.array(["GNSS_AIDED"] * n, dtype=object)
    mode[23:60] = "DEAD_RECKONING"          # 0.3 s after the mask starts
    mode[60:70] = "REACQUIRING"
    fix_rows = np.array([0, 10, 60, 70, 80, 90])
    return t, mode, est_e, est_n, speed, true_e, true_n, fix_rows


def test_transition_metrics_measure_latency_snap_and_step():
    t, mode, est_e, est_n, speed, true_e, true_n, fix_rows = _synthetic_transition(True)
    m = metrics.transition_metrics(
        time_s=t, mode=mode, est_e=est_e, est_n=est_n, speed_ms=speed,
        true_e=true_e, true_n=true_n, fix_rows=fix_rows,
        start_row=20, mask_end_row=50, window_s=3.0,
    )
    assert m.detection_latency_s == pytest.approx(0.3)
    assert m.reacq_snap_m == pytest.approx(30.0)
    # The display jumps 30 m east while the vehicle moves 1 m north: the
    # excess step is hypot(30, 1) - 1.
    assert m.reacq_max_step_m == pytest.approx(math.hypot(30.0, 1.0) - 1.0, abs=1e-6)
    assert m.reacq_settle_s == pytest.approx(1.0)
    assert m.reacq_residual_m == pytest.approx(0.0)


def test_transition_metrics_reward_a_slide_over_a_snap():
    t, mode, est_e, est_n, speed, true_e, true_n, fix_rows = _synthetic_transition(False)
    m = metrics.transition_metrics(
        time_s=t, mode=mode, est_e=est_e, est_n=est_n, speed_ms=speed,
        true_e=true_e, true_n=true_n, fix_rows=fix_rows,
        start_row=20, mask_end_row=50, window_s=3.0,
    )
    assert m.reacq_snap_m == pytest.approx(30.0)
    assert m.reacq_max_step_m < 3.5
    assert m.reacq_residual_m == pytest.approx(0.0)


def test_transition_metrics_report_nan_when_dr_never_entered():
    t, mode, est_e, est_n, speed, true_e, true_n, fix_rows = _synthetic_transition(True)
    mode = np.array(["GNSS_AIDED"] * len(t), dtype=object)
    m = metrics.transition_metrics(
        time_s=t, mode=mode, est_e=est_e, est_n=est_n, speed_ms=speed,
        true_e=true_e, true_n=true_n, fix_rows=fix_rows,
        start_row=20, mask_end_row=50, window_s=3.0,
    )
    assert math.isnan(m.detection_latency_s)
    assert math.isnan(m.reacq_settle_s)


# --------------------------------------------------------------------------
# evaluation protocol
# --------------------------------------------------------------------------

def _shift_gnss_after(seq: iovnbd.Sequence, row: int, metres: float) -> iovnbd.Sequence:
    """Move the GNSS track north by ``metres`` from ``row`` on, truth included.

    The straight fixture drives due east at a constant latitude, so shifting
    latitude upward leaves ``nanmin`` -- and therefore the ENU origin -- exactly
    where it was. Without that the whole frame would translate and the
    comparison would be vacuous.
    """
    df = seq.df.copy()
    idx = df.index[row:]
    df.loc[idx, "gps_lat_deg"] = df.loc[idx, "gps_lat_deg"] + metres / 111_320.0
    return iovnbd.Sequence(seq.name, seq.path, df, seq.repair)


def test_the_scoring_instant_is_never_aided(s_csv_straight):
    """The fix used to score an outage must never reach the estimator.

    This is the protocol bug that hid behind the chi-square gate: metrics are
    read at the first real fix at or after the horizon, and with the mask
    ending at the horizon that same fix was offered to the filter in the same
    sample, before its position was recorded. A gate that usually rejects a
    large innovation is not a protocol, and the day the filter re-anchors on
    re-acquisition -- which is the right product behaviour -- the score becomes
    a measurement of how fast it snaps to the answer.

    Moving the entire post-outage GNSS track 500 m north must therefore change
    nothing about the estimate at the scoring instant.
    """
    seq = iovnbd.load_s_sequence(s_csv_straight)
    fix_rows = np.flatnonzero(seq.df["gps_fix_is_new"].to_numpy())
    window = masking.make_window(seq, start_s=float(seq.time_s[50]), duration_s=10.0)
    eval_row = metrics.evaluation_row(seq.time_s, fix_rows, window.start_row, 10.0)
    assert eval_row is not None

    scored = masking.extend_to_row(seq, window, eval_row)
    assert scored.end_row > eval_row, "the mask must cover the scoring row"

    def estimate_at_scoring_row(shift_m: float):
        source = seq if shift_m == 0.0 else _shift_gnss_after(seq, window.start_row, shift_m)
        traj = pipeline.run(
            masking.apply_mask(source, scored), start_row=0, end_row=eval_row + 20
        )
        return traj.east_m[eval_row], traj.north_m[eval_row], traj.mode[eval_row]

    east, north, mode = estimate_at_scoring_row(0.0)
    east_shifted, north_shifted, _ = estimate_at_scoring_row(500.0)

    assert mode == "DEAD_RECKONING", f"scored while {mode}, i.e. aided"
    assert east == pytest.approx(east_shifted, abs=1e-9)
    assert north == pytest.approx(north_shifted, abs=1e-9)


# --------------------------------------------------------------------------
# calibrated radius
# --------------------------------------------------------------------------

def test_calibrated_radius_is_lambda_times_the_gaussian_radius_on_the_major_axis():
    cov = np.diag([4.0, 1.0])
    r = metrics.calibrated_radius(cov, lam=2.0, level=0.9)
    assert r == pytest.approx(2.0 * conformal.chi2_radius(0.9) * 2.0)


def test_calibrated_radius_ignores_covariance_orientation():
    c, s = math.cos(0.7), math.sin(0.7)
    rot = np.array([[c, -s], [s, c]])
    cov = rot @ np.diag([9.0, 1.0]) @ rot.T
    assert metrics.calibrated_radius(cov, lam=1.0) == pytest.approx(
        metrics.calibrated_radius(np.diag([9.0, 1.0]), lam=1.0)
    )


# --------------------------------------------------------------------------
# summary helpers
# --------------------------------------------------------------------------

def _res(seq: str, h: float, t_eval: float, crse: float, drift: float) -> dict:
    return {"sequence": seq, "horizon_s": h, "t_eval_s": t_eval,
            "crse_m": crse, "drift_pct": drift, "distance_m": 100.0}


def test_share_under_target_counts_only_matching_horizons():
    rs = [_res("a", 10.0, 12.0, 5.0, 5.0), _res("b", 10.0, 12.0, 50.0, 50.0),
          _res("a", 30.0, 33.0, 8.0, 8.0)]
    out = compare.share_under_drift(rs, 10.0)
    assert out[10.0] == pytest.approx(0.5)
    assert out[30.0] == pytest.approx(1.0)


def test_share_beating_pairs_outages_by_sequence_horizon_and_time():
    ours = [_res("a", 10.0, 12.0, 5.0, 5.0), _res("b", 10.0, 12.0, 50.0, 50.0),
            _res("c", 10.0, 12.0, 5.0, 5.0)]
    theirs = [_res("b", 10.0, 12.0, 20.0, 20.0), _res("a", 10.0, 12.0, 10.0, 10.0)]
    out = compare.share_beating(ours, theirs)
    # 'c' has no partner and is not counted; 'a' wins, 'b' loses.
    assert out[10.0] == pytest.approx(0.5)
    assert compare.paired_count(ours, theirs)[10.0] == 2


def test_summarise_includes_transition_and_radius_medians():
    r = metrics.OutageResult(
        sequence="a", method="m", horizon_s=10.0, t_eval_s=12.0, distance_m=100.0,
        crse_m=5.0, cte_m=1.0, ate_m=3.0, drift_pct=5.0, n_fixes_suppressed=1,
        truth_gap_m=20.0, detection_latency_s=1.0, reacq_snap_m=5.0,
        reacq_max_step_m=4.0, reacq_settle_s=2.0, reacq_residual_m=0.5,
        radius90_raw_m=3.0, radius90_cal_m=45.0,
    )
    s = metrics.summarise([r])[10.0]
    assert s["share_under_10pct"] == pytest.approx(1.0)
    assert s["detection_latency_median_s"] == pytest.approx(1.0)
    assert s["reacq_max_step_median_m"] == pytest.approx(4.0)
    assert s["radius90_cal_median_m"] == pytest.approx(45.0)
