"""Kinematic filter, alignment estimator, and the GNSS state machine."""

from __future__ import annotations

import math

import numpy as np
import pytest

from shadownav.filter import alignment as al
from shadownav.filter.fsm import BlendState, FsmConfig, GnssFsm, GnssMode, GnssObservation
from shadownav.filter.kinematic import KinematicConfig, KinematicEKF, wrap


# --------------------------------------------------------------------------
# kinematic propagation
# --------------------------------------------------------------------------

def test_wrap_keeps_angles_in_range():
    for a in (0.0, 3.0, 4.0, -4.0, 100.0):
        assert -math.pi < wrap(a) <= math.pi


def test_straight_north_travel():
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    for _ in range(100):
        f.propagate(0.0, None, 0.1)
    assert f.position[1] == pytest.approx(100.0, abs=1e-6)
    assert f.position[0] == pytest.approx(0.0, abs=1e-9)


def test_straight_east_travel():
    f = KinematicEKF(0.0, 0.0, math.pi / 2, 10.0)
    for _ in range(100):
        f.propagate(0.0, None, 0.1)
    assert f.position[0] == pytest.approx(100.0, abs=1e-6)


def test_positive_gyro_z_decreases_clockwise_heading():
    """ENU is right-handed about up, so +omega_z is a LEFT turn.

    A sign error here mirrors every turn and is invisible on straight roads --
    which is most of any drive.
    """
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    for _ in range(10):
        f.propagate(0.1, None, 0.1)
    assert f.heading_rad < 0


def test_a_quarter_turn_integrates_to_ninety_degrees():
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    rate = -math.pi / 2 / 10.0  # right turn, 90 deg over 10 s
    for _ in range(100):
        f.propagate(rate, None, 0.1)
    assert math.degrees(f.heading_rad) == pytest.approx(90.0, abs=0.5)


def test_speed_is_held_when_no_acceleration_is_supplied():
    """Speed hold is the model during a blackout, not an accident."""
    f = KinematicEKF(0.0, 0.0, 0.0, 12.0)
    for _ in range(600):
        f.propagate(0.0, None, 0.1)
    assert f.speed_ms == pytest.approx(12.0, abs=1e-9)


def test_speed_never_goes_negative():
    f = KinematicEKF(0.0, 0.0, 0.0, 1.0)
    for _ in range(100):
        f.propagate(0.0, -5.0, 0.1)
    assert f.speed_ms >= 0.0


def test_uncertainty_grows_during_a_blackout():
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    start = np.trace(f.position_covariance)
    for _ in range(600):
        f.propagate(0.0, None, 0.1)
    assert np.trace(f.position_covariance) > start


def test_covariance_stays_symmetric_and_definite():
    f = KinematicEKF(0.0, 0.0, 0.3, 10.0)
    for i in range(400):
        f.propagate(0.02, None, 0.1)
        if i % 90 == 0:
            f.update_position(f.position + np.array([1.0, -1.0]))
            f.update_speed(10.0)
    np.testing.assert_allclose(f.cov, f.cov.T, atol=1e-12)
    assert np.all(np.linalg.eigvalsh(f.cov) > 0)


# --------------------------------------------------------------------------
# measurements
# --------------------------------------------------------------------------

def test_position_update_pulls_toward_the_fix():
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    f.update_position(np.array([3.0, 4.0]))
    assert 0.0 < f.position[0] <= 3.0


def test_chi_square_gate_rejects_a_wild_fix():
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    assert not f.update_position(np.array([5000.0, 5000.0]))
    assert f.diagnostics.n_gps_rejected == 1


def test_multipath_spike_rejection_and_recovery():
    """Multipath jump with degraded C/N0 is rejected, leaving the inertial trajectory intact."""
    f = KinematicEKF(0.0, 0.0, 0.0, 15.0)
    # Travel north for 1.0 s (10 steps @ 0.1 s) -> north should be ~15.0 m
    for _ in range(10):
        f.propagate(0.0, None, 0.1)
    assert f.position[1] == pytest.approx(15.0, abs=1e-5)

    # Good fix at t=1.0s with healthy C/N0=36 dB-Hz
    accepted = f.update_position(np.array([0.1, 15.1]), cn0_mean=36.0)
    assert accepted
    assert f.diagnostics.n_gps_accepted == 1

    # Travel north for another 1.0 s -> north ~30.0 m
    for _ in range(10):
        f.propagate(0.0, None, 0.1)

    # Multipath reflection jumps 40 m east into a building, C/N0 drops to 18 dB-Hz
    multipath_pos = np.array([40.0, 30.0])
    rejected = f.update_position(multipath_pos, cn0_mean=18.0)
    assert not rejected
    assert f.diagnostics.n_gps_rejected == 1
    # Filter position must not be pulled to the 40 m spike
    assert abs(f.position[0]) < 2.0
    assert f.position[1] == pytest.approx(30.0, abs=1.0)

    # Next clean fix arrives at t=3.0 s (north ~45 m, C/N0=35 dB-Hz)
    for _ in range(10):
        f.propagate(0.0, None, 0.1)
    clean_pos = np.array([0.0, 45.0])
    recovered = f.update_position(clean_pos, cn0_mean=35.0)
    assert recovered
    assert f.diagnostics.n_gps_accepted == 2
    assert f.diagnostics.consecutive_rejections == 0


def test_persistent_rejection_triggers_a_reanchor_rather_than_lockout():
    """A diverged filter must not reject every fix forever.

    A competitor shipped exactly that bug: a hardcoded accuracy gate trapped
    their engine in dead reckoning for 2h13m (dossier section 10).
    """
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    for _ in range(3):
        f.update_position(np.array([5000.0, 5000.0]))
    assert f.diagnostics.n_gate_overrides == 1
    assert f.position[0] == pytest.approx(5000.0)


def test_zero_angular_rate_update_estimates_gyro_bias_at_rest():
    """ZARU during stationary holds directly estimates and zeros gyro bias."""
    f = KinematicEKF(0.0, 0.0, 0.0, 0.0)
    assert f.x[4] == pytest.approx(0.0)  # I_BW initially 0
    # True gyro bias is +0.025 rad/s; sensor measures 0.025 at rest
    for _ in range(10):
        f.propagate(0.025, None, 0.1)
        f.update_zero_angular_rate(0.025, sigma=0.001)
    assert f.x[4] == pytest.approx(0.025, abs=1e-3)
    assert f.cov[4, 4] < 1e-4


def test_course_update_is_ignored_at_standstill():
    """A stationary receiver reports an essentially random course."""
    f = KinematicEKF(0.0, 0.0, 0.0, 0.0)
    f.update_course(math.pi / 2)
    assert f.heading_rad == pytest.approx(0.0)


def test_course_update_applies_when_moving():
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    for _ in range(20):
        f.update_course(0.5)
    assert f.heading_rad == pytest.approx(0.5, abs=0.05)


def test_course_update_takes_the_short_way_round():
    """Wrapping matters: 350 deg to 10 deg is +20, not -340."""
    f = KinematicEKF(0.0, 0.0, math.radians(350) - 2 * math.pi, 10.0)
    for _ in range(20):
        f.update_course(math.radians(10))
    assert math.degrees(f.heading_rad) == pytest.approx(10.0, abs=2.0)


def test_centripetal_observation_recovers_speed_during_a_turn():
    """a_lat = -v * psi_dot, so a turn observes speed (PLAN.md:94)."""
    true_v, gyro_z = 12.0, 0.2
    a_lat = -true_v * gyro_z
    f = KinematicEKF(0.0, 0.0, 0.0, 6.0)   # deliberately wrong speed
    for _ in range(60):
        f.update_centripetal(a_lat, gyro_z)
    assert f.speed_ms == pytest.approx(true_v, rel=0.15)


def test_centripetal_observation_is_skipped_on_a_straight_road():
    """With psi_dot ~ 0 the Jacobian vanishes and the update is pure noise."""
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    f.update_centripetal(0.0, 0.001)
    assert f.diagnostics.n_centripetal == 0


# --------------------------------------------------------------------------
# alignment
# --------------------------------------------------------------------------

def _synth_drive(n=2000, dt=0.1, rot=None, fix_every=90):
    """Accelerating drive, GPS speed held in blocks like the real data."""
    rng = np.random.default_rng(5)
    t = np.arange(n) * dt
    v = 10.0 + 4.0 * np.sin(2 * np.pi * t / 60.0)
    a = np.gradient(v, dt)
    acc = np.stack([np.zeros(n), a, np.full(n, 9.80665)], axis=1)
    acc += rng.normal(0, 0.05, acc.shape)
    gyr = rng.normal(0, 0.002, (n, 3))
    if rot is not None:
        acc = acc @ rot
        gyr = gyr @ rot
    held = v.copy()
    for i in range(0, n, fix_every):
        held[i : i + fix_every] = v[i]
    return acc, gyr, held, t


def test_alignment_recovers_a_known_rotation():
    from shadownav.filter.state import exp_so3
    r = exp_so3(np.array([0.0, 0.0, 0.9]))          # yaw the phone in the cradle
    acc, gyr, v, t = _synth_drive(rot=r.T)
    out = al.estimate_alignment(acc, gyr, v, t)
    assert out.quality > 0.5
    recovered_fwd = out.rot_device_to_car[1]
    # The fixture writes device = r . car, so car-forward in device
    # coordinates is r @ [0,1,0] -- not r.T @ [0,1,0].
    expected_fwd = r @ np.array([0.0, 1.0, 0.0])
    assert abs(float(recovered_fwd @ expected_fwd)) > 0.9


def test_alignment_reports_zero_quality_on_constant_speed():
    """The degenerate case: no longitudinal excitation, no forward axis."""
    n = 1200
    t = np.arange(n) * 0.1
    acc = np.tile([0.0, 0.0, 9.80665], (n, 1))
    gyr = np.zeros((n, 3))
    v = np.full(n, 12.0)
    out = al.estimate_alignment(acc, gyr, v, t)
    assert out.quality == 0.0
    np.testing.assert_allclose(out.rot_device_to_car, np.eye(3))


def test_alignment_output_is_a_proper_rotation():
    acc, gyr, v, t = _synth_drive()
    out = al.estimate_alignment(acc, gyr, v, t)
    r = out.rot_device_to_car
    np.testing.assert_allclose(r @ r.T, np.eye(3), atol=1e-9)
    assert np.linalg.det(r) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# FSM
# --------------------------------------------------------------------------

def test_blend_error_decays_to_zero():
    b = BlendState(2.3)
    b.start(np.array([20.0, -15.0]))
    for _ in range(200):
        b.step(0.02)
    assert np.linalg.norm(b.error) < 0.15
    assert b.settled


def test_blend_does_not_overshoot_wildly():
    """Critically damped, so it must not ring."""
    b = BlendState(2.3)
    b.start(np.array([10.0, 0.0]))
    seen = [abs(b.step(0.02)[0]) for _ in range(300)]
    assert max(seen) <= 10.0 + 1e-6


def test_fsm_enters_dead_reckoning_after_the_dwell():
    fsm = GnssFsm(FsmConfig(enter_dwell_s=1.0))
    lost = GnssObservation(available=False)
    assert fsm.update(0.0, lost, 0.1) is GnssMode.AIDED   # dwell not elapsed
    for k in range(1, 30):
        fsm.update(k * 0.1, lost, 0.1)
    assert fsm.mode is GnssMode.DEAD_RECKONING


def test_fsm_does_not_chatter_on_a_single_dropped_sample():
    fsm = GnssFsm(FsmConfig(enter_dwell_s=1.0))
    good = GnssObservation(available=True, n_sats_used=10, cn0_mean=40.0, accuracy_m=4.0)
    fsm.update(0.0, good, 0.1)
    fsm.update(0.1, GnssObservation(available=False), 0.1)
    fsm.update(0.2, good, 0.1)
    assert fsm.mode is GnssMode.AIDED


def test_reacquisition_is_never_skipped():
    """Going straight from blackout to aided is what causes a visible jump."""
    fsm = GnssFsm(FsmConfig(enter_dwell_s=0.5))
    lost = GnssObservation(available=False)
    for k in range(20):
        fsm.update(k * 0.1, lost, 0.1)
    assert fsm.mode is GnssMode.DEAD_RECKONING
    good = GnssObservation(available=True, n_sats_used=10, cn0_mean=40.0, accuracy_m=4.0)
    fsm.begin_reacquisition(np.array([10.0, 0.0]), np.array([0.0, 0.0]))
    for k in range(6):
        fsm.update(2.1 + k * 0.1, good, 0.1)
    assert fsm.mode is GnssMode.REACQUIRING, (
        "blackout must exit through REACQUIRING, and promptly -- a long dwell "
        "here delays the blend the PS grades on"
    )


def test_degraded_state_exists_for_the_urban_canyon():
    """GNSS is not lost in a canyon -- it lies. A two-state FSM never fires."""
    fsm = GnssFsm(FsmConfig(exit_dwell_s=0.5))
    poor = GnssObservation(available=True, n_sats_used=5, cn0_mean=20.0, accuracy_m=40.0)
    for k in range(20):
        fsm.update(k * 0.1, poor, 0.1)
    assert fsm.mode is GnssMode.DEGRADED
    assert not fsm.dead_reckoning, "a degraded fix is still a fix"


def test_fiducial_is_recorded_for_reanchoring():
    fsm = GnssFsm()
    fsm.note_good_fix(12.0, np.array([100.0, 200.0]))
    assert fsm.fiducial_time_s == 12.0
    np.testing.assert_allclose(fsm.fiducial_en, [100.0, 200.0])
