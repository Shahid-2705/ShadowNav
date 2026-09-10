"""Confidence gate around a learned speed source: correct, never dominate.

Why a gate rather than more model
---------------------------------
Two independent measurements say an unconditional learned correction is worse
than no correction:

* Agastya's own ablation (research dossier section 10): ungated learned
  correction scored 2.76 m ATE against their classical 1.64 m baseline, and
  only the gated policy won.
* This project's 8-sequence control (python/README.md): the CNN+GRU speed net
  helps 9-13% at 30-120 s and hurts 19% at 180 s, carrying a +1.08 m/s bias
  on test whose sign flips on val, so it cannot be de-biased from held-out
  data.

GNIO (dossier section 1.2) reaches the same conclusion from the other side:
its learned gate alone is worth 23.3% of its total gain. So the model is
allowed to *move* the filter's speed, within limits set by its own calibrated
confidence, and is refused the moment it stops being plausible.

What the gate can and cannot see
--------------------------------
``pipeline_kinematic.run`` hands a ``SpeedEstimator`` only the raw IMU window
(``(window_acc, window_gyr) -> (speed_ms, sigma_ms)``). It does not pass the
filter's own speed, its covariance, the GNSS mode, or the time step. Changing
that protocol means editing the pipeline, which this module deliberately does
not do. Consequences:

* the gate keeps **its own prior**: the last speed it emitted. Rule (b) and
  rule (c) work against that prior, not against the filter's state;
* the rate limit (rule e) uses a nominal ``dt_s`` per call rather than the
  true sample interval. The pipeline calls once per sample, so at 10 Hz with
  ``speed_stride = 1`` that is 0.1 s;
* a NaN speed is the protocol's "no opinion" and makes the pipeline skip the
  update, so a rejection is simply a NaN.

The rules, in the order they are applied
----------------------------------------
(d) plausibility: reject a model speed outside ``[v_min, v_max]``;
(a) confidence:   reject when the calibrated sigma exceeds ``sigma_max``;
(b) innovation:   reject when ``|model - prior| > k_innovation * sigma``;
                  after ``max_consecutive_rejections`` of these in a row the
                  prior is stale by definition and the gate re-seeds from the
                  model (the GNSS FSM's gate escape, applied to speed);
(c) shrinkage:    emit ``prior + w * (model - prior)`` with ``w = weight(sigma)``
                  falling linearly from ``w_max`` at ``sigma_full_trust`` to 0
                  at ``sigma_zero_trust``;
(e) rate limit:   the emitted speed moves at most ``a_max * dt_s`` per call.

Everything is a frozen dataclass and ``gate_step`` is a pure function of
``(config, state, model_speed, model_sigma)``. ``GatedSpeed`` is the thin
stateful shell the pipeline's callable protocol requires; it rebinds its state
to the new object each call and never mutates one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from ..pipeline_kinematic import SpeedEstimator

#: A car cannot exceed this and a phone cannot measure it; 216 km/h.
MAX_PLAUSIBLE_SPEED_MS = 60.0


@dataclass(frozen=True)
class GateConfig:
    """Every rule's parameter. Defaults are the val-tuned values documented in
    python/README.md ("Gated speed filter"); change them there, not here."""

    sigma_max: float = 3.0                 # rule (a), m/s, after sigma_scale
    k_innovation: float = 3.0              # rule (b), in sigmas
    max_consecutive_rejections: int = 30   # rule (b) escape, in calls (3 s at 10 Hz)
    w_max: float = 0.5                     # rule (c), upper weight in [0, 1]
    sigma_full_trust: float = 0.6          # rule (c), sigma at which w = w_max
    sigma_zero_trust: float = 3.0          # rule (c), sigma at which w = 0
    v_min: float = 0.0                     # rule (d), m/s
    v_max: float = MAX_PLAUSIBLE_SPEED_MS  # rule (d), m/s
    a_max: float = 3.0                     # rule (e), m/s^2
    dt_s: float = 0.1                      # rule (e), nominal seconds per call

    def __post_init__(self) -> None:
        if not 0.0 <= self.w_max <= 1.0:
            raise ValueError(f"w_max must be in [0, 1], got {self.w_max}")
        if self.a_max <= 0.0 or self.dt_s <= 0.0:
            raise ValueError("a_max and dt_s must be positive")
        if self.sigma_zero_trust <= self.sigma_full_trust:
            raise ValueError("sigma_zero_trust must exceed sigma_full_trust")
        if self.v_max <= self.v_min:
            raise ValueError("v_max must exceed v_min")
        if self.sigma_max <= 0.0 or self.k_innovation <= 0.0:
            raise ValueError("sigma_max and k_innovation must be positive")
        if self.max_consecutive_rejections < 1:
            raise ValueError("max_consecutive_rejections must be >= 1")

    def weight(self, sigma: float) -> float:
        """Rule (c): trust falls linearly with the calibrated sigma."""
        span = self.sigma_zero_trust - self.sigma_full_trust
        ramp = (self.sigma_zero_trust - sigma) / span
        return self.w_max * float(np.clip(ramp, 0.0, 1.0))

    @property
    def max_step_ms(self) -> float:
        """Rule (e): largest change the emitted speed may make per call."""
        return self.a_max * self.dt_s


@dataclass(frozen=True)
class GateCounts:
    accepted: int = 0
    rejected_sigma: int = 0
    rejected_innovation: int = 0
    rejected_bound: int = 0
    shrunk: int = 0
    rate_limited: int = 0
    rebootstrapped: int = 0
    no_opinion: int = 0

    @property
    def rejected_total(self) -> int:
        return self.rejected_sigma + self.rejected_innovation + self.rejected_bound

    def bump(self, **fields: int) -> "GateCounts":
        return replace(self, **{k: getattr(self, k) + v for k, v in fields.items()})

    def merged(self, other: "GateCounts") -> "GateCounts":
        return GateCounts(**{
            k: getattr(self, k) + getattr(other, k) for k in self.__dataclass_fields__
        })

    def as_dict(self) -> dict[str, int]:
        return {
            **{k: getattr(self, k) for k in self.__dataclass_fields__},
            "rejected": self.rejected_total,
        }


@dataclass(frozen=True)
class GateState:
    prior_ms: float = math.nan
    consecutive_rejections: int = 0
    counts: GateCounts = field(default_factory=GateCounts)

    @classmethod
    def initial(cls) -> "GateState":
        return cls()

    @property
    def has_prior(self) -> bool:
        return math.isfinite(self.prior_ms)


@dataclass(frozen=True)
class GateDecision:
    speed_ms: float          # NaN when rejected
    sigma_ms: float          # the model's calibrated sigma, passed through
    reason: str
    state: GateState


def _reject(state: GateState, sigma: float, reason: str, counter: str,
            innovation: bool = False) -> GateDecision:
    consecutive = state.consecutive_rejections + 1 if innovation else 0
    new = replace(state, counts=state.counts.bump(**{counter: 1}),
                  consecutive_rejections=consecutive)
    return GateDecision(math.nan, sigma, reason, new)


def _accept(state: GateState, speed: float, sigma: float, reason: str,
            **extra: int) -> GateDecision:
    new = GateState(prior_ms=speed, consecutive_rejections=0,
                    counts=state.counts.bump(accepted=1, **extra))
    return GateDecision(speed, sigma, reason, new)


def gate_step(cfg: GateConfig, state: GateState,
              model_speed: float, model_sigma: float) -> GateDecision:
    """Apply every rule once. Pure: returns a new state, touches nothing."""
    if not (math.isfinite(model_speed) and math.isfinite(model_sigma)):
        return GateDecision(math.nan, math.nan, "no_opinion",
                            replace(state, counts=state.counts.bump(no_opinion=1)))
    if not cfg.v_min <= model_speed <= cfg.v_max:                    # rule (d)
        return _reject(state, model_sigma, "bound", "rejected_bound")
    if model_sigma > cfg.sigma_max:                                  # rule (a)
        return _reject(state, model_sigma, "sigma", "rejected_sigma")
    if not state.has_prior:
        return _accept(state, model_speed, model_sigma, "bootstrap")

    innovation = model_speed - state.prior_ms
    if abs(innovation) > cfg.k_innovation * model_sigma:             # rule (b)
        if state.consecutive_rejections >= cfg.max_consecutive_rejections:
            return _accept(state, model_speed, model_sigma, "rebootstrap",
                           rebootstrapped=1)
        return _reject(state, model_sigma, "innovation",
                       "rejected_innovation", innovation=True)

    w = cfg.weight(model_sigma)                                      # rule (c)
    target = state.prior_ms + w * innovation
    step = float(np.clip(target - state.prior_ms,                    # rule (e)
                         -cfg.max_step_ms, cfg.max_step_ms))
    emitted = float(np.clip(state.prior_ms + step, cfg.v_min, cfg.v_max))
    return _accept(
        state, emitted, model_sigma, "accept",
        shrunk=int(abs(emitted - model_speed) > 1e-12),
        rate_limited=int(abs(step) < abs(target - state.prior_ms) - 1e-12),
    )


class GatedSpeed:
    """``SpeedEstimator`` shell: runs the wrapped estimator, then ``gate_step``.

    Holds the current ``GateState`` and rebinds it every call; the state
    objects themselves are never mutated. ``reset`` starts a fresh prior for a
    new drive and folds the run's counts into ``totals``.
    """

    def __init__(self, estimator: SpeedEstimator, config: GateConfig | None = None) -> None:
        self.estimator = estimator
        self.config = config or GateConfig()
        self.state = GateState.initial()
        self.totals = GateCounts()
        self.last = GateDecision(math.nan, math.nan, "none", self.state)

    @property
    def counts(self) -> GateCounts:
        return self.state.counts

    def reset(self) -> None:
        self.totals = self.totals.merged(self.state.counts)
        self.state = GateState.initial()

    def __call__(self, window_acc: np.ndarray, window_gyr: np.ndarray) -> tuple[float, float]:
        speed, sigma = self.estimator(window_acc, window_gyr)
        decision = gate_step(self.config, self.state, float(speed), float(sigma))
        self.state = decision.state
        self.last = decision
        return decision.speed_ms, decision.sigma_ms
