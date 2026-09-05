"""GNSS availability state machine with fiducial re-anchoring.

Four states with dwell hysteresis, per PLAN.md:78. Note that the four-mode FSM
itself is **not novel** -- ``algoarchemist/seamless-navigation`` shipped a
functionally equivalent one first (dossier section 10), and the external-review
response records that claim as retired. What is defensible here is the
*fiducial re-anchor* and the *degraded-but-present* path.

    GNSS_AIDED  --degrading-->  DEGRADED  --lost-->  DEAD_RECKONING
         ^                          |                      |
         |                          v                      v
         +------------------ REACQUIRING <-----------------+

DEGRADED is the urban-canyon state and the reason a plain two-state FSM is not
enough: in a canyon GNSS is never lost, so a lost/found machine never leaves
GNSS_AIDED while the receiver reports fixes that are tens of metres wrong
(PLAN.md:139). In DEGRADED the fix is kept but de-weighted and chi-square
gated.

Re-acquisition blending
-----------------------
On regaining GNSS the estimate is generally displaced from truth. Snapping to
the new fix produces the visible position jump that PLAN.md:169 names as the
PS's literal grading criterion. Instead the *error* is driven to zero by a
critically damped spring while riding on the moving estimate.

demo/README.md documents two formulations that were already tried and are
wrong: springing the position toward a moving target lags by 2v/omega, and
recomputing the error after the truth advances lags then snaps at lock. The
correct form treats the error as its own state, which is what is implemented
here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class GnssMode(str, Enum):
    AIDED = "GNSS_AIDED"
    DEGRADED = "DEGRADED"
    DEAD_RECKONING = "DEAD_RECKONING"
    REACQUIRING = "REACQUIRING"


@dataclass(frozen=True)
class FsmConfig:
    """Thresholds. Dwell times prevent chattering at a tunnel mouth."""

    min_sats_for_fix: int = 4
    degraded_sats: int = 6
    degraded_cn0: float = 28.0
    degraded_accuracy_m: float = 15.0

    enter_dwell_s: float = 1.0
    exit_dwell_s: float = 2.0
    #: Entering REACQUIRING is deliberately fast. It is a safe state -- the
    #: filter is still dead reckoning while the blend runs -- and making it wait
    #: the full exit dwell delays the blend-back, which is the behaviour
    #: PLAN.md:169 says the PS grades on.
    reacquire_dwell_s: float = 0.3

    #: Critically damped blend. omega = 2.3 rad/s settles in about 1.8 s,
    #: matching the presentation demo so the offline and live behaviour agree.
    blend_omega: float = 2.3
    blend_settle_m: float = 0.15


@dataclass(frozen=True)
class GnssObservation:
    """What the receiver reports at one instant."""

    available: bool
    n_sats_used: int = 0
    cn0_mean: float = float("nan")
    accuracy_m: float = float("nan")


class BlendState:
    """Position error driven to zero by a critically damped second-order spring.

    The error is the state, not the position. Riding the error to zero while it
    is added to a moving estimate is what removes the jump without lag.
    """

    def __init__(self, omega: float) -> None:
        self.omega = omega
        self.error = np.zeros(2)
        self.rate = np.zeros(2)

    def start(self, error_en: np.ndarray) -> None:
        self.error = np.asarray(error_en, dtype=float).copy()
        self.rate = np.zeros(2)

    def step(self, dt: float) -> np.ndarray:
        """Advance the spring and return the residual error still to absorb."""
        accel = -2.0 * self.omega * self.rate - self.omega**2 * self.error
        self.rate = self.rate + accel * dt
        self.error = self.error + self.rate * dt
        return self.error

    @property
    def settled(self) -> bool:
        return float(np.linalg.norm(self.error)) < 0.15


class GnssFsm:
    """Availability classifier plus re-acquisition blend."""

    def __init__(self, config: FsmConfig | None = None) -> None:
        self.config = config or FsmConfig()
        self.mode = GnssMode.AIDED
        self.blend = BlendState(self.config.blend_omega)
        self._pending: GnssMode | None = None
        self._pending_since = 0.0
        self.time_since_fix_s = 0.0
        #: Last position accepted while healthy -- the fiducial the estimate is
        #: re-anchored on when the blackout ends.
        self.fiducial_en: np.ndarray | None = None
        self.fiducial_time_s: float | None = None
        self.transitions: list[tuple[float, GnssMode]] = []

    def _classify(self, obs: GnssObservation) -> GnssMode:
        c = self.config
        if not obs.available or obs.n_sats_used < c.min_sats_for_fix:
            return GnssMode.DEAD_RECKONING
        degraded = (
            obs.n_sats_used < c.degraded_sats
            or (np.isfinite(obs.cn0_mean) and obs.cn0_mean < c.degraded_cn0)
            or (np.isfinite(obs.accuracy_m) and obs.accuracy_m > c.degraded_accuracy_m)
        )
        return GnssMode.DEGRADED if degraded else GnssMode.AIDED

    def update(self, t: float, obs: GnssObservation, dt: float) -> GnssMode:
        """Advance the machine. Returns the mode now in force."""
        target = self._classify(obs)

        if obs.available and obs.n_sats_used >= self.config.min_sats_for_fix:
            self.time_since_fix_s = 0.0
        else:
            self.time_since_fix_s += dt

        # Leaving a blackout goes through REACQUIRING, never straight to AIDED.
        if self.mode is GnssMode.DEAD_RECKONING and target in (
            GnssMode.AIDED, GnssMode.DEGRADED
        ):
            target = GnssMode.REACQUIRING

        if self.mode is GnssMode.REACQUIRING:
            if target is GnssMode.DEAD_RECKONING:
                self._commit(t, GnssMode.DEAD_RECKONING)
            elif self.blend.settled:
                self._commit(t, target if target is not GnssMode.REACQUIRING
                             else GnssMode.AIDED)
            return self.mode

        if target is self.mode:
            self._pending = None
            return self.mode

        if target is GnssMode.DEAD_RECKONING:
            dwell = self.config.enter_dwell_s
        elif target is GnssMode.REACQUIRING:
            dwell = self.config.reacquire_dwell_s
        else:
            dwell = self.config.exit_dwell_s
        if self._pending is not target:
            self._pending = target
            self._pending_since = t
        elif t - self._pending_since >= dwell:
            self._commit(t, target)
        return self.mode

    def _commit(self, t: float, mode: GnssMode) -> None:
        if mode is self.mode:
            return
        self.mode = mode
        self._pending = None
        self.transitions.append((t, mode))

    def note_good_fix(self, t: float, pos_en: np.ndarray) -> None:
        """Record the fiducial the blackout will be re-anchored against."""
        self.fiducial_en = np.asarray(pos_en, dtype=float)[:2].copy()
        self.fiducial_time_s = t

    def begin_reacquisition(self, estimate_en: np.ndarray, fix_en: np.ndarray) -> None:
        """Seed the blend with the displacement to absorb."""
        self.blend.start(np.asarray(estimate_en)[:2] - np.asarray(fix_en)[:2])

    @property
    def dead_reckoning(self) -> bool:
        return self.mode in (GnssMode.DEAD_RECKONING, GnssMode.REACQUIRING)
