"""Phase 2 components: Ackermann bounds, conformal calibration, speed net."""

from __future__ import annotations

import math

import numpy as np
import pytest
import torch

from shadownav.evaluation import conformal
from shadownav.filter.kinematic import KinematicEKF
from shadownav.models.features import N_CHANNELS, gravity_direction, invariant_features
from shadownav.models.speednet import SpeedNet, SpeedNetConfig, gaussian_nll
from shadownav.utils.seed import seed_everything


# --------------------------------------------------------------------------
# Ackermann curvature and friction bounds
# --------------------------------------------------------------------------

def test_curvature_bound_raises_an_impossibly_low_speed():
    """No car turns at 0.5 rad/s while crawling -- that is a 3.6 m radius."""
    f = KinematicEKF(0.0, 0.0, 0.0, 0.2)
    applied = f.update_ackermann(0.5)
    assert applied
    assert f.speed_ms > 0.2
    assert f.diagnostics.n_ackermann == 1


def test_friction_bound_lowers_an_impossibly_high_speed():
    """20 m/s at 0.5 rad/s needs 10 m/s^2 of grip; asphalt gives ~7.8."""
    f = KinematicEKF(0.0, 0.0, 0.0, 20.0)
    assert f.update_ackermann(0.5)
    assert f.speed_ms < 20.0


def test_friction_bound_is_not_gated_by_the_slip_test():
    """Regression guard for a circularity that made this bound dead code.

    The 0.5 g slip gate (4.9 m/s^2) is tighter than the friction bound itself
    (mu*g = 7.85 m/s^2), so gating the friction bound by slip means every
    violation is filtered out before the bound can fire. The friction bound is
    the physics that defines the slip limit, so it must apply unconditionally.
    """
    f = KinematicEKF(0.0, 0.0, 0.0, 40.0)   # 40 m/s at 0.5 rad/s = 20 m/s^2
    assert f.update_ackermann(0.5), "friction bound must fire past the slip gate"
    assert f.speed_ms < 40.0


def test_bounds_do_nothing_in_the_feasible_band():
    """They must cost nothing in normal driving, not bias toward a midpoint."""
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    before = f.speed_ms
    assert not f.update_ackermann(0.2)
    assert f.speed_ms == pytest.approx(before)
    assert f.diagnostics.n_ackermann == 0


def test_bounds_are_skipped_on_a_straight_road():
    f = KinematicEKF(0.0, 0.0, 0.0, 10.0)
    assert not f.update_ackermann(0.001)


def test_curvature_bound_switches_off_past_the_slip_limit():
    """Above ~0.5 g lateral the bicycle model no longer holds (PLAN.md:108).

    Only the curvature bound is gated this way. The friction bound is not --
    see test_friction_bound_is_not_gated_by_the_slip_test.
    """
    f = KinematicEKF(0.0, 0.0, 0.0, 2.0)
    # 2 m/s at 3.0 rad/s is 6 m/s^2 lateral, past the 4.9 m/s^2 gate, and the
    # speed sits below the curvature bound -- which must nonetheless not fire.
    before = f.speed_ms
    f.update_ackermann(3.0)
    assert f.speed_ms <= before, "curvature bound fired outside its validity"


def test_bounds_need_no_wheelbase():
    """The whole point: a smartphone cannot know the vehicle's wheelbase."""
    cfg_fields = KinematicEKF(0, 0, 0, 10).config.__dict__
    assert not any("wheelbase" in k or "length" in k for k in cfg_fields)


# --------------------------------------------------------------------------
# conformal calibration
# --------------------------------------------------------------------------

def test_chi2_radius_matches_the_rayleigh_quantile():
    r = conformal.chi2_radius(0.90)
    assert 1.0 - math.exp(-r * r / 2.0) == pytest.approx(0.90)


def test_a_well_calibrated_filter_needs_no_inflation():
    rng = np.random.default_rng(0)
    cov = np.eye(2)
    pairs = [(rng.multivariate_normal(np.zeros(2), cov), cov) for _ in range(4000)]
    cal = conformal.fit({30.0: pairs}, level=0.90)
    assert cal.factor_for(30.0) == pytest.approx(1.0, abs=0.06)


def test_an_overconfident_filter_is_inflated():
    """Errors three times larger than the covariance claims."""
    rng = np.random.default_rng(1)
    cov = np.eye(2)
    pairs = [(3.0 * rng.multivariate_normal(np.zeros(2), cov), cov) for _ in range(4000)]
    cal = conformal.fit({30.0: pairs}, level=0.90)
    assert cal.factor_for(30.0) == pytest.approx(3.0, rel=0.1)


def test_inflation_restores_nominal_coverage_on_held_out_data():
    """Fit on one sample, measure on another -- the property that matters."""
    rng = np.random.default_rng(2)
    cov = np.eye(2)
    fit_pairs = [(4.0 * rng.multivariate_normal(np.zeros(2), cov), cov) for _ in range(3000)]
    test_pairs = [(4.0 * rng.multivariate_normal(np.zeros(2), cov), cov) for _ in range(3000)]

    before = conformal.coverage(test_pairs, level=0.90)
    cal = conformal.fit({30.0: fit_pairs}, level=0.90)
    after = conformal.coverage(test_pairs, level=0.90, calibration=cal, horizon_s=30.0)

    assert before < 0.35, "an overconfident filter should under-cover badly"
    assert after == pytest.approx(0.90, abs=0.03)


def test_too_few_points_leaves_the_covariance_alone():
    """Better no calibration than one invented from four samples."""
    cal = conformal.fit({30.0: [(np.ones(2), np.eye(2))] * 3}, level=0.90)
    assert cal.factor_for(30.0) == 1.0


def test_unfitted_horizon_falls_back_to_the_nearest():
    cal = conformal.ConformalCalibration(0.9, {10.0: 2.0, 180.0: 5.0}, {10.0: 9, 180.0: 9})
    assert cal.factor_for(12.0) == 2.0
    assert cal.factor_for(200.0) == 5.0


def test_inflate_scales_by_lambda_squared():
    cal = conformal.ConformalCalibration(0.9, {30.0: 3.0}, {30.0: 100})
    out = cal.inflate(np.eye(2), 30.0)
    np.testing.assert_allclose(out, np.eye(2) * 9.0)


# --------------------------------------------------------------------------
# invariant features
# --------------------------------------------------------------------------

def test_features_are_invariant_to_rotation_about_the_vertical():
    """The property the whole feature design rests on."""
    rng = np.random.default_rng(3)
    acc = rng.normal(0, 1, (64, 3)) + np.array([0, 0, 9.81])
    gyr = rng.normal(0, 0.1, (64, 3))
    up = gravity_direction(acc)
    base = invariant_features(acc, gyr, up)

    theta = 1.1
    c, s = math.cos(theta), math.sin(theta)
    rz = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    rot_acc, rot_gyr = acc @ rz.T, gyr @ rz.T
    rotated = invariant_features(rot_acc, rot_gyr, gravity_direction(rot_acc))

    np.testing.assert_allclose(base, rotated, atol=1e-9)


def test_features_have_the_declared_channel_count():
    acc = np.tile([0.0, 0.0, 9.81], (32, 1))
    gyr = np.zeros((32, 3))
    out = invariant_features(acc, gyr, np.array([0.0, 0.0, 1.0]))
    assert out.shape == (32, N_CHANNELS)


def test_vertical_channel_reads_gravity_at_rest():
    acc = np.tile([0.0, 0.0, 9.81], (32, 1))
    out = invariant_features(acc, np.zeros((32, 3)), np.array([0.0, 0.0, 1.0]))
    assert out[:, 1].mean() == pytest.approx(9.81)
    assert out[:, 2].mean() == pytest.approx(0.0, abs=1e-9)


def test_yaw_channel_picks_up_rotation_about_the_vertical():
    gyr = np.tile([0.0, 0.0, 0.3], (32, 1))
    acc = np.tile([0.0, 0.0, 9.81], (32, 1))
    out = invariant_features(acc, gyr, np.array([0.0, 0.0, 1.0]))
    assert out[:, 4].mean() == pytest.approx(0.3)


# --------------------------------------------------------------------------
# speed network
# --------------------------------------------------------------------------

def test_model_fits_the_low_end_budget():
    """5 MB INT8 is a hard constraint from the target-hardware decision."""
    model = SpeedNet()
    assert model.n_parameters < 1_250_000, "would exceed ~5 MB INT8"


def test_forward_shapes():
    model = SpeedNet()
    speed, log_var = model(torch.zeros(4, 64, N_CHANNELS))
    assert speed.shape == (4,)
    assert log_var.shape == (4,)


def test_speed_output_is_non_negative():
    """Softplus magnitude times a [0,1] gate cannot go negative."""
    seed_everything(1)
    model = SpeedNet()
    speed, _ = model(torch.randn(64, 64, N_CHANNELS) * 3.0)
    assert bool((speed >= 0).all())


def test_gate_can_drive_the_output_to_zero():
    """The soft ZUPT property: a differentiable stop, not a hard threshold."""
    model = SpeedNet(SpeedNetConfig(gate_activation="sigmoid"))
    with torch.no_grad():
        model.gate.bias.fill_(-30.0)
        model.gate.weight.zero_()
    speed, _ = model(torch.randn(8, 64, N_CHANNELS))
    assert float(speed.abs().max()) < 1e-4


def test_motion_bank_changes_the_output():
    """Guards against the bank being wired up but not connected."""
    seed_everything(2)
    x = torch.randn(8, 64, N_CHANNELS)
    with_bank = SpeedNet(SpeedNetConfig(use_motion_bank=True))
    seed_everything(2)
    without = SpeedNet(SpeedNetConfig(use_motion_bank=False))
    assert not torch.allclose(with_bank(x)[0], without(x)[0])


def test_log_variance_is_bounded():
    """An unbounded sigma head can emit a value the filter blindly trusts."""
    seed_everything(3)
    model = SpeedNet()
    _, log_var = model(torch.randn(32, 64, N_CHANNELS) * 50.0)
    assert bool((log_var >= -6.0).all()) and bool((log_var <= 6.0).all())


def test_nll_prefers_a_large_sigma_when_wrong():
    """The mechanism that makes the filter widen its gate on a bad guess."""
    pred = torch.zeros(1)
    target = torch.tensor([10.0])
    confident = gaussian_nll(pred, torch.tensor([-2.0]), target)
    humble = gaussian_nll(pred, torch.tensor([4.0]), target)
    assert float(humble) < float(confident)


def test_model_is_causal_in_the_window():
    """Changing the last sample must change the output; the future is not used.

    A window that peeks forward scores well offline and cannot be deployed.
    """
    seed_everything(4)
    model = SpeedNet().eval()
    x = torch.randn(1, 64, N_CHANNELS)
    y = x.clone()
    y[0, -1, :] += 5.0
    with torch.no_grad():
        assert not torch.allclose(model(x)[0], model(y)[0])
