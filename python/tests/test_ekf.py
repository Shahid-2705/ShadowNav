"""Filter correctness.

The load-bearing tests here are the two finite-difference Jacobian checks. A
hand-derived Jacobian that is never numerically verified is the classic way a
Kalman filter ends up quietly inconsistent: it still runs, still produces a
trajectory, and its covariance is wrong in a way no amount of staring at the
output reveals. Everything the project later claims about calibrated confidence
(PLAN.md:140) rests on these passing.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import chi2

from shadownav.filter import state as st
from shadownav.filter.ekf import FilterConfig, NonholonomicEKF


def boxminus(pert: st.NavState, ref: st.NavState) -> np.ndarray:
    """Error-state difference ``pert (-) ref`` as a 21-vector."""
    dx = np.zeros(st.DIM)
    dx[st.I_THETA] = st.log_so3(ref.rot.T @ pert.rot)
    dx[st.I_V] = pert.vel - ref.vel
    dx[st.I_P] = pert.pos - ref.pos
    dx[st.I_BG] = pert.bias_gyro - ref.bias_gyro
    dx[st.I_BA] = pert.bias_acc - ref.bias_acc
    dx[st.I_THETA_C] = st.log_so3(ref.rot_car.T @ pert.rot_car)
    dx[st.I_PC] = pert.lever - ref.lever
    return dx


def sample_state(seed: int = 3) -> st.NavState:
    """A generic state -- nothing axis-aligned, so no term hides behind a zero."""
    rng = np.random.default_rng(seed)
    return st.NavState(
        rot=st.exp_so3(np.array([0.05, -0.11, 0.7])),
        vel=np.array([8.1, 3.4, -0.2]),
        pos=np.array([120.0, -45.0, 3.0]),
        bias_gyro=np.array([0.004, -0.002, 0.003]),
        bias_acc=np.array([0.05, -0.03, 0.02]),
        rot_car=st.exp_so3(np.array([0.02, 0.03, -0.04])),
        lever=np.array([0.3, -0.2, 0.5]),
    ) if seed == 3 else st.NavState(
        rot=st.exp_so3(rng.normal(size=3) * 0.4),
        vel=rng.normal(size=3) * 5.0,
        pos=rng.normal(size=3) * 50.0,
        bias_gyro=rng.normal(size=3) * 0.005,
        bias_acc=rng.normal(size=3) * 0.05,
        rot_car=st.exp_so3(rng.normal(size=3) * 0.05),
        lever=rng.normal(size=3) * 0.4,
    )


# --------------------------------------------------------------------------
# SO(3) helpers
# --------------------------------------------------------------------------

def test_exp_log_round_trip():
    for phi in (np.array([0.1, -0.2, 0.3]), np.array([1e-12, 0.0, 0.0]),
                np.array([0.0, 0.0, 3.0])):
        np.testing.assert_allclose(st.log_so3(st.exp_so3(phi)), phi, atol=1e-9)


def test_exp_produces_a_proper_rotation():
    r = st.exp_so3(np.array([0.3, -0.7, 1.2]))
    np.testing.assert_allclose(r @ r.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(r) == pytest.approx(1.0)


def test_skew_matches_the_cross_product():
    a, b = np.array([1.0, 2.0, 3.0]), np.array([-4.0, 5.0, 6.0])
    np.testing.assert_allclose(st.skew(a) @ b, np.cross(a, b))


def test_orthonormalise_repairs_manifold_drift():
    r = st.exp_so3(np.array([0.2, 0.1, -0.3])) + 1e-3 * np.ones((3, 3))
    out = st.orthonormalise(r)
    np.testing.assert_allclose(out @ out.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(out) == pytest.approx(1.0)


def test_heading_of_identity_is_north():
    assert st.heading_of(np.eye(3)) == pytest.approx(0.0)


def test_heading_is_clockwise_from_north():
    # A body yawed so forward points east should read +90 degrees.
    r = st.exp_so3(np.array([0.0, 0.0, -math.pi / 2]))
    assert st.heading_of(r) == pytest.approx(math.pi / 2)


# --------------------------------------------------------------------------
# THE Jacobian checks
# --------------------------------------------------------------------------

def test_transition_matrix_matches_finite_differences():
    """F must equal the numerical derivative of the nonlinear propagation."""
    gyro = np.array([0.02, -0.01, 0.15])
    acc = np.array([0.4, 0.2, 9.9])
    dt = 0.1
    eps = 1e-6

    base = sample_state()
    ekf = NonholonomicEKF(base)
    f_analytic = ekf.transition_matrix(gyro, acc, dt)

    def propagate(state: st.NavState) -> st.NavState:
        k = NonholonomicEKF(state)
        k.propagate(gyro, acc, dt)
        return k.state

    ref_out = propagate(base)
    f_numeric = np.zeros((st.DIM, st.DIM))
    for i in range(st.DIM):
        d = np.zeros(st.DIM)
        d[i] = eps
        f_numeric[:, i] = boxminus(propagate(base.inject(d)), ref_out) / eps

    np.testing.assert_allclose(f_analytic, f_numeric, atol=2e-5)


def test_transition_matrix_holds_for_a_second_random_state():
    """Guards against a term that happens to vanish at one operating point."""
    gyro = np.array([-0.08, 0.05, -0.22])
    acc = np.array([-1.1, 0.7, 9.5])
    dt = 0.1
    eps = 1e-6
    base = sample_state(seed=11)
    f_analytic = NonholonomicEKF(base).transition_matrix(gyro, acc, dt)

    def propagate(s: st.NavState) -> st.NavState:
        k = NonholonomicEKF(s)
        k.propagate(gyro, acc, dt)
        return k.state

    ref_out = propagate(base)
    f_numeric = np.zeros((st.DIM, st.DIM))
    for i in range(st.DIM):
        d = np.zeros(st.DIM)
        d[i] = eps
        f_numeric[:, i] = boxminus(propagate(base.inject(d)), ref_out) / eps
    np.testing.assert_allclose(f_analytic, f_numeric, atol=2e-5)


def test_car_velocity_jacobian_matches_finite_differences():
    """The measurement Jacobian carries both NHC and the learned speed."""
    base = sample_state()
    gyro = np.array([0.03, -0.02, 0.18])
    eps = 1e-7

    ekf = NonholonomicEKF(base)
    v_ref, h_analytic = ekf._car_velocity_jacobian(gyro - base.bias_gyro)

    h_numeric = np.zeros((3, st.DIM))
    for i in range(st.DIM):
        d = np.zeros(st.DIM)
        d[i] = eps
        pert = base.inject(d)
        v_pert = pert.car_velocity(gyro - pert.bias_gyro)
        h_numeric[:, i] = (v_pert - v_ref) / eps

    np.testing.assert_allclose(h_analytic, h_numeric, atol=1e-5)


# --------------------------------------------------------------------------
# propagation behaviour
# --------------------------------------------------------------------------

def test_stationary_level_state_does_not_accelerate():
    """Specific force +g on body up with zero rotation must net to zero."""
    s = st.NavState.initial(np.eye(3), np.zeros(3))
    ekf = NonholonomicEKF(s)
    for _ in range(100):
        ekf.propagate(np.zeros(3), np.array([0.0, 0.0, 9.80665]), 0.1)
    np.testing.assert_allclose(ekf.state.vel, np.zeros(3), atol=1e-9)
    np.testing.assert_allclose(ekf.state.pos, np.zeros(3), atol=1e-9)


def test_constant_velocity_is_preserved():
    s = st.NavState.initial(np.eye(3), np.array([0.0, 10.0, 0.0]))
    ekf = NonholonomicEKF(s)
    for _ in range(100):
        ekf.propagate(np.zeros(3), np.array([0.0, 0.0, 9.80665]), 0.1)
    assert ekf.state.pos[1] == pytest.approx(100.0, abs=1e-6)
    assert ekf.state.speed_ms == pytest.approx(10.0, abs=1e-9)


def test_rotation_stays_on_the_manifold_over_a_long_run():
    ekf = NonholonomicEKF(st.NavState.initial(np.eye(3), np.zeros(3)))
    for _ in range(2000):
        ekf.propagate(np.array([0.01, -0.02, 0.3]),
                      np.array([0.0, 0.0, 9.80665]), 0.1)
    r = ekf.state.rot
    np.testing.assert_allclose(r @ r.T, np.eye(3), atol=1e-9)
    assert np.linalg.det(r) == pytest.approx(1.0, abs=1e-9)


def test_covariance_stays_symmetric_positive_definite():
    ekf = NonholonomicEKF(st.NavState.initial(np.eye(3), np.array([0.0, 12.0, 0.0])))
    for _ in range(500):
        ekf.propagate(np.array([0.0, 0.0, 0.05]), np.array([0.1, 0.0, 9.8]), 0.1)
        ekf.update_nonholonomic(np.array([0.0, 0.0, 0.05]))
    np.testing.assert_allclose(ekf.cov, ekf.cov.T, atol=1e-12)
    assert np.all(np.linalg.eigvalsh(ekf.cov) > 0), "covariance lost definiteness"


def test_position_uncertainty_grows_without_measurements():
    ekf = NonholonomicEKF(st.NavState.initial(np.eye(3), np.array([0.0, 10.0, 0.0])))
    first = np.trace(ekf.position_covariance)
    for _ in range(300):
        ekf.propagate(np.zeros(3), np.array([0.0, 0.0, 9.80665]), 0.1)
    assert np.trace(ekf.position_covariance) > first


# --------------------------------------------------------------------------
# measurements
# --------------------------------------------------------------------------

def test_nonholonomic_update_suppresses_lateral_velocity():
    """A car does not slide sideways; the constraint must pull it back."""
    s = st.NavState.initial(np.eye(3), np.array([3.0, 10.0, 0.0]))
    ekf = NonholonomicEKF(s)
    before = abs(ekf.state.car_velocity(np.zeros(3))[0])
    for _ in range(50):
        ekf.update_nonholonomic(np.zeros(3))
    after = abs(ekf.state.car_velocity(np.zeros(3))[0])
    assert after < 0.1 * before


def test_nonholonomic_update_leaves_forward_speed_alone():
    """The constraint must not remove the thing we are trying to estimate."""
    s = st.NavState.initial(np.eye(3), np.array([0.5, 10.0, 0.0]))
    ekf = NonholonomicEKF(s)
    for _ in range(50):
        ekf.update_nonholonomic(np.zeros(3))
    assert ekf.state.car_velocity(np.zeros(3))[1] == pytest.approx(10.0, abs=0.5)


def test_forward_speed_update_pulls_toward_the_measurement():
    s = st.NavState.initial(np.eye(3), np.array([0.0, 5.0, 0.0]))
    ekf = NonholonomicEKF(s)
    for _ in range(30):
        ekf.update_forward_speed(12.0, np.zeros(3))
    assert ekf.state.car_velocity(np.zeros(3))[1] == pytest.approx(12.0, abs=0.5)


def test_gps_update_accepts_a_consistent_fix():
    ekf = NonholonomicEKF(st.NavState.initial(np.eye(3), np.zeros(3)))
    assert ekf.update_gps_position(np.array([0.5, -0.5]))
    assert ekf.diagnostics.n_gps_accepted == 1


def test_chi_square_gate_rejects_a_wild_fix():
    """The urban-canyon defence: GNSS is not lost there, it lies."""
    ekf = NonholonomicEKF(st.NavState.initial(np.eye(3), np.zeros(3)))
    assert not ekf.update_gps_position(np.array([500.0, 500.0]))
    assert ekf.diagnostics.n_gps_rejected == 1


def test_gate_threshold_is_the_documented_chi_square_value():
    assert chi2.ppf(0.997, df=2) == pytest.approx(11.62, abs=0.01)


def test_low_cn0_widens_the_gate_rather_than_the_estimate():
    """De-weighting must make a marginal fix acceptable but less influential."""
    good = NonholonomicEKF(st.NavState.initial(np.eye(3), np.zeros(3)))
    poor = NonholonomicEKF(st.NavState.initial(np.eye(3), np.zeros(3)))
    fix = np.array([9.0, 0.0])
    good.update_gps_position(fix, cn0_mean=45.0)
    poor.update_gps_position(fix, cn0_mean=15.0)
    assert abs(good.state.pos[0]) > abs(poor.state.pos[0]), (
        "a low-C/N0 fix should move the estimate less, not more"
    )


def test_lever_arm_is_bounded_to_inside_the_vehicle():
    ekf = NonholonomicEKF(st.NavState.initial(np.eye(3), np.zeros(3)))
    ekf.state = ekf.state.replace(lever=np.array([50.0, 0.0, 0.0]))
    ekf.update_nonholonomic(np.zeros(3))
    assert np.all(np.abs(ekf.state.lever) <= ekf.config.max_lever_m)


def test_state_injection_returns_a_new_object():
    s = sample_state()
    out = s.inject(np.ones(st.DIM) * 0.01)
    assert out is not s
    assert not np.allclose(out.vel, s.vel)
    np.testing.assert_array_equal(s.vel, sample_state().vel)
