"""The confidence gate around the learned speed front end.

The field's evidence (dossier section 10, Agastya's ablation; section 1.2,
GNIO's gate) says an ungated learned correction can be worse than the classical
baseline and only a gated one wins. Each rule below is tested on its own with a
scripted stand-in for the network, so a change to any one of them fails here
rather than surfacing as a shifted 180 s median three runs later.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from shadownav.models.gate import (
    GateConfig,
    GateCounts,
    GatedSpeed,
    GateState,
    gate_step,
)


class Scripted:
    """A SpeedEstimator that replays a fixed list of (speed, sigma)."""

    def __init__(self, outputs: list[tuple[float, float]]) -> None:
        self.outputs = list(outputs)
        self.calls = 0

    def __call__(self, window_acc: np.ndarray, window_gyr: np.ndarray) -> tuple[float, float]:
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return out


WIN = np.zeros((64, 3))


def run_gate(outputs: list[tuple[float, float]], **overrides) -> tuple[list[float], GatedSpeed]:
    g = GatedSpeed(Scripted(outputs), GateConfig(**overrides))
    emitted = [g(WIN, WIN)[0] for _ in outputs]
    return emitted, g


# --------------------------------------------------------------------------
# rule (a): calibrated sigma too large -> reject
# --------------------------------------------------------------------------

def test_rejects_when_sigma_exceeds_threshold():
    emitted, g = run_gate([(10.0, 0.5), (10.0, 9.0)], sigma_max=4.0)
    assert np.isfinite(emitted[0])
    assert np.isnan(emitted[1])
    assert g.counts.rejected_sigma == 1
    assert g.counts.accepted == 1


def test_sigma_threshold_is_configurable():
    emitted, _ = run_gate([(10.0, 0.5), (10.0, 3.0)], sigma_max=10.0)
    assert all(np.isfinite(v) for v in emitted)


# --------------------------------------------------------------------------
# rule (b): innovation gate against the wrapper's own prior
# --------------------------------------------------------------------------

def test_innovation_gate_rejects_a_jump_beyond_k_sigma():
    # Prior settles at 10; a jump to 20 with sigma 1 is 10 sigma away.
    emitted, g = run_gate([(10.0, 1.0), (20.0, 1.0)], k_innovation=3.0, w_max=1.0)
    assert emitted[0] == pytest.approx(10.0)
    assert np.isnan(emitted[1])
    assert g.counts.rejected_innovation == 1


def test_innovation_gate_scales_with_sigma():
    # Same jump, but the model admits sigma 5: 10/5 = 2 sigma < k -> accepted.
    emitted, g = run_gate([(10.0, 1.0), (20.0, 5.0)], k_innovation=3.0,
                          w_max=1.0, sigma_max=8.0, a_max=1e9)
    assert np.isfinite(emitted[1])
    assert g.counts.rejected_innovation == 0


def test_rejection_leaves_the_prior_where_it_was():
    # Third output sits inside sigma_full_trust so w = w_max = 1 and the
    # emitted value equals the model's: the rejected 20 left no trace.
    outs = [(10.0, 1.0), (20.0, 1.0), (10.5, 0.5)]
    emitted, _ = run_gate(outs, k_innovation=3.0, w_max=1.0, a_max=1e9)
    assert emitted[2] == pytest.approx(10.5)


def test_sustained_disagreement_rebootstraps_rather_than_sticking():
    """A car that genuinely stops must not be gated out forever.

    After ``max_consecutive_rejections`` innovation rejections the prior is
    stale by definition, so the gate re-seeds from the model. This mirrors the
    GNSS FSM's own gate escape after three rejected fixes.
    """
    outs = [(15.0, 0.5)] + [(0.0, 0.5)] * 6
    emitted, g = run_gate(outs, k_innovation=3.0, w_max=1.0,
                          max_consecutive_rejections=3, a_max=1e9)
    assert np.isnan(emitted[1]) and np.isnan(emitted[2]) and np.isnan(emitted[3])
    assert emitted[4] == pytest.approx(0.0)
    assert g.counts.rebootstrapped == 1


# --------------------------------------------------------------------------
# rule (c): shrink toward the prior, never replace it
# --------------------------------------------------------------------------

def test_shrinks_toward_prior_with_w_max():
    emitted, g = run_gate([(10.0, 0.1), (12.0, 0.1)], w_max=0.5,
                          k_innovation=100.0, a_max=1e9,
                          sigma_full_trust=0.5, sigma_zero_trust=4.0)
    assert emitted[1] == pytest.approx(10.0 + 0.5 * 2.0)
    assert g.counts.shrunk == 1


def test_weight_falls_as_sigma_rises():
    cfg = GateConfig(w_max=1.0, sigma_full_trust=0.5, sigma_zero_trust=2.5,
                     sigma_max=8.0, k_innovation=100.0, a_max=1e9)
    w_low = cfg.weight(0.5)
    w_mid = cfg.weight(1.5)
    w_high = cfg.weight(2.5)
    assert w_low == pytest.approx(1.0)
    assert w_mid == pytest.approx(0.5)
    assert w_high == pytest.approx(0.0)
    assert 0.0 <= w_high <= w_mid <= w_low <= cfg.w_max


def test_weight_never_exceeds_w_max():
    cfg = GateConfig(w_max=0.3)
    for s in (0.0, 0.4, 1.0, 3.0, 8.0):
        assert 0.0 <= cfg.weight(s) <= 0.3


# --------------------------------------------------------------------------
# rule (d): plausibility bound
# --------------------------------------------------------------------------

def test_rejects_negative_or_supersonic_speeds():
    emitted, g = run_gate([(-1.0, 0.5), (70.0, 0.5), (10.0, 0.5)])
    assert np.isnan(emitted[0]) and np.isnan(emitted[1])
    assert emitted[2] == pytest.approx(10.0)
    assert g.counts.rejected_bound == 2


def test_emitted_speed_stays_inside_the_bounds():
    outs = [(10.0, 0.1)] + [(59.9, 0.1)] * 400
    emitted, _ = run_gate(outs, w_max=1.0, k_innovation=1e9, a_max=1e9)
    assert all(0.0 <= v <= 60.0 for v in emitted if np.isfinite(v))


# --------------------------------------------------------------------------
# rule (e): rate limit
# --------------------------------------------------------------------------

def test_emitted_speed_cannot_change_faster_than_a_max_dt():
    emitted, g = run_gate([(10.0, 0.1), (10.9, 0.1)], w_max=1.0,
                          k_innovation=100.0, a_max=2.0, dt_s=0.1)
    assert emitted[1] == pytest.approx(10.2)
    assert g.counts.rate_limited == 1


def test_rate_limit_applies_symmetrically():
    emitted, _ = run_gate([(10.0, 0.1), (5.0, 0.1)], w_max=1.0,
                          k_innovation=100.0, a_max=2.0, dt_s=0.1)
    assert emitted[1] == pytest.approx(9.8)


# --------------------------------------------------------------------------
# bookkeeping and contract
# --------------------------------------------------------------------------

def test_first_opinion_bootstraps_the_prior():
    emitted, g = run_gate([(12.3, 0.5)])
    assert emitted[0] == pytest.approx(12.3)
    assert g.counts.accepted == 1


def test_no_opinion_from_the_model_passes_through_untouched():
    emitted, g = run_gate([(10.0, 0.5), (float("nan"), float("nan")), (10.0, 0.5)])
    assert np.isnan(emitted[1])
    assert g.counts.no_opinion == 1
    assert g.counts.accepted == 2
    assert g.state.prior_ms == pytest.approx(10.0)


def test_counts_add_up():
    rng = np.random.default_rng(20260905)
    outs = [(float(v), float(s)) for v, s in
            zip(rng.uniform(-2, 70, 300), rng.uniform(0.1, 9.0, 300))]
    emitted, g = run_gate(outs)
    c = g.counts
    n_rejected = c.rejected_sigma + c.rejected_bound + c.rejected_innovation
    assert c.accepted + n_rejected + c.no_opinion == len(outs)
    assert sum(np.isnan(emitted)) == n_rejected
    assert c.shrunk <= c.accepted and c.rate_limited <= c.accepted


def test_gate_step_is_pure_and_state_is_frozen():
    cfg = GateConfig()
    s0 = GateState.initial()
    d1 = gate_step(cfg, s0, 10.0, 0.5)
    d2 = gate_step(cfg, s0, 10.0, 0.5)
    assert d1 == d2
    assert s0 == GateState.initial(), "the input state must not be mutated"
    with pytest.raises(dataclasses.FrozenInstanceError):
        s0.prior_ms = 1.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        GateCounts().accepted = 1  # type: ignore[misc]


def test_sigma_is_passed_through_calibrated():
    """The gate decides and shrinks; it does not re-invent the model's sigma."""
    emitted, g = run_gate([(10.0, 0.7)])
    assert g.last.sigma_ms == pytest.approx(0.7)


def test_config_rejects_nonsense():
    with pytest.raises(ValueError):
        GateConfig(a_max=-1.0)
    with pytest.raises(ValueError):
        GateConfig(w_max=1.5)
    with pytest.raises(ValueError):
        GateConfig(sigma_full_trust=3.0, sigma_zero_trust=1.0)
    with pytest.raises(ValueError):
        GateConfig(v_min=10.0, v_max=5.0)


def test_reset_folds_counts_into_totals_and_clears_the_prior():
    _, g = run_gate([(10.0, 0.5), (10.1, 0.5)])
    g.reset()
    assert np.isnan(g.state.prior_ms)
    assert g.counts.accepted == 0
    assert g.totals.accepted == 2


# --------------------------------------------------------------------------
# the composed estimator around the shipped checkpoint
# --------------------------------------------------------------------------

def _shipped():
    from shadownav.models.inference import DEFAULT_MODEL

    if not Path(DEFAULT_MODEL).exists():
        pytest.skip("no trained model; run scripts/train_speednet.py")


def test_gated_estimator_composes_the_shipped_model():
    _shipped()
    from shadownav.models.inference import GatedSpeedNetEstimator, SpeedNetEstimator

    g = GatedSpeedNetEstimator()
    plain = SpeedNetEstimator()
    assert g.window == plain.window
    assert g.variant == plain.variant
    assert g.sigma_scale == pytest.approx(plain.sigma_scale)
    assert g.sigma_scale > 1.0, "the val-fitted scale must reach the gate"


def test_gated_estimator_obeys_the_protocol_and_the_bounds():
    _shipped()
    from shadownav.models.inference import GatedSpeedNetEstimator

    g = GatedSpeedNetEstimator()
    rng = np.random.default_rng(20260905)
    acc = rng.normal(0, 0.3, (200, 3)) + np.array([0.0, 0.0, 9.81])
    gyr = rng.normal(0, 0.05, (200, 3))
    g.set_gravity(acc)
    for i in range(g.window, 200):
        v, s = g(acc[i - g.window + 1: i + 1], gyr[i - g.window + 1: i + 1])
        assert np.isnan(v) or 0.0 <= v <= 60.0
        assert np.isnan(v) or np.isfinite(s)
    d = g.diagnostics()
    assert d["accepted"] + d["rejected"] + d["no_opinion"] == 200 - g.window
    assert np.isnan(g(np.zeros((8, 3)), np.zeros((8, 3)))[0])


def test_set_gravity_starts_a_fresh_prior():
    """A new drive must not inherit the previous drive's speed."""
    _shipped()
    from shadownav.models.inference import GatedSpeedNetEstimator

    g = GatedSpeedNetEstimator()
    rng = np.random.default_rng(3)
    acc = rng.normal(0, 0.3, (64, 3)) + np.array([0.0, 0.0, 9.81])
    gyr = rng.normal(0, 0.05, (64, 3))
    g.set_gravity(acc)
    g(acc, gyr)
    g.set_gravity(acc)
    assert np.isnan(g.gate.state.prior_ms)
    assert g.gate.totals.accepted + g.gate.totals.rejected_total >= 1
