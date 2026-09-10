"""Heading-only map constraint: road bearing as a gated heading observation.

This is *map-aided odometry* in the form Fouque, Bonnifait and Bétaille
published at IEEE/ION PLANS 2008 -- the bearing of the matched road enters a
Kalman filter as a heading measurement with innovation gating and a
conservative fallback to pure dead reckoning. It is prior art and is cited as
such; nothing here claims novelty on tight coupling (research/
SIH26168-open-track-findings.md, Track C).

Why heading and never lateral position
--------------------------------------
On parallel service roads beside a carriageway -- the classic map-matching
ambiguity -- the *heading* is identical across every candidate while the
lateral position differs by a lane or a verge. A heading-only constraint is
therefore safe exactly where a lateral one is most dangerous. Position is
never touched: PLAN.md risk 3, "wrong map-match corrupts the filter".

The rules, per epoch
--------------------
1. Candidates: the nearest segment of every road within ``search_radius_m``.
   The default 30 m sits just above the 27 m median vehicle travel between
   consecutive IO-VNBD fixes, so an estimate that is one fix-period stale
   along-track still finds its own road rather than none.
2. Zero candidates within 200 m -> ``DISABLED`` (Newson & Krumm's no-candidate
   rule: the lattice breaks in tunnels, and multi-storey car parks have no
   road network at all). Zero within the search radius but some within 200 m
   -> ``NO_CANDIDATES``. Both reset the consistency counter.
3. Agreement: every candidate's travel bearing must agree within
   ``agreement_deg`` after folding modulo 180 deg (two-way roads carry both
   senses); a one-way road pointing the wrong way is a disagreement. Any
   disagreement -> ``REJECTED_DISAGREEMENT``.
4. Junction lookahead: a junction node within ``junction_lookahead_m`` ahead
   along any candidate -> ``REJECTED_JUNCTION``. The vehicle may be turning.
5. Chi-square gate on the innovation against the gyro-propagated heading.
   The pipeline hook carries no covariance, so the gate uses a *fixed* prior
   sigma (``gate_sigma_deg``) rather than the filter's live heading variance;
   this is stated here and in the README rather than hidden.
6. ``min_consistent_epochs`` consecutive epochs passing 1-5 before the first
   observation is released (``WARMING`` until then, ``APPLIED`` after).

The observation handed to the filter is the nearest candidate's travel
bearing with sigma ``sigma_deg``, applied through the filter's existing
``update_course`` -- the same measurement model GNSS course uses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from scipy.stats import chi2

from .index import Candidate, RoadIndex
from .osm import RoadNetwork, project_network


class Decision(str, Enum):
    APPLIED = "applied"
    WARMING = "warming"
    REJECTED_DISAGREEMENT = "rejected_disagreement"
    REJECTED_JUNCTION = "rejected_junction"
    REJECTED_GATE = "rejected_gate"
    NO_CANDIDATES = "no_candidates"
    DISABLED = "disabled"


@dataclass(frozen=True)
class HeadingConstraintConfig:
    search_radius_m: float = 30.0
    agreement_deg: float = 5.0
    min_consistent_epochs: int = 5
    junction_lookahead_m: float = 40.0
    gate_sigma_deg: float = 10.0
    gate_confidence: float = 0.997
    disable_radius_m: float = 200.0
    #: Which candidates take part in the agreement test. True: only those
    #: that individually pass the innovation gate ("surviving candidates" in
    #: Track C's wording) -- a road at right angles to a gyro-propagated
    #: heading that is 12-18 deg wrong at worst is not a plausible match and
    #: should not veto the road the vehicle is on. False: every candidate in
    #: the radius must agree, which in an urban grid rejects most epochs.
    gate_candidates: bool = True
    #: Measurement sigma handed to the filter. Road bearing differs from the
    #: vehicle's heading by lane changes and polyline discretisation; 5 deg
    #: is the same figure the filter uses for GNSS course.
    sigma_deg: float = 5.0


@dataclass(frozen=True)
class ConstraintState:
    consistent_epochs: int = 0


@dataclass(frozen=True)
class Epoch:
    row: int
    decision: Decision
    n_candidates: int
    bearing_rad: float | None
    innovation_rad: float | None
    sigma_rad: float


def wrap(a: float) -> float:
    return float((a + math.pi) % (2.0 * math.pi) - math.pi)


def fold_bearing(bearing_rad: float) -> float:
    """Axial bearing in ``[0, pi)``: a road's two senses fold onto one value."""
    return float(bearing_rad % math.pi)


def bearings_agree(bearings, window_rad: float) -> bool:
    """Do all bearings lie within ``window_rad`` of one another after folding?"""
    folded = [fold_bearing(b) for b in bearings]
    if not folded:
        return False
    ref = folded[0]
    diffs = [((b - ref + math.pi / 2.0) % math.pi) - math.pi / 2.0 for b in folded]
    return (max(diffs) - min(diffs)) <= window_rad


def travel_bearing(cand: Candidate, heading_rad: float) -> tuple[float, bool] | None:
    """The candidate's sense closest to the heading, and whether it is forward.

    None when no allowed sense is within a quarter turn -- a one-way road the
    vehicle would be driving the wrong way down.
    """
    options = list(zip(cand.bearings, (True, False) if cand.oneway == 0 else (cand.oneway == 1,)))
    bearing, forward = min(options, key=lambda o: abs(wrap(o[0] - heading_rad)))
    if abs(wrap(bearing - heading_rad)) > math.pi / 2.0:
        return None
    return bearing, forward


@dataclass(frozen=True)
class HeadingConstraint:
    index: RoadIndex
    config: HeadingConstraintConfig = field(default_factory=HeadingConstraintConfig)

    @classmethod
    def from_network(cls, network: RoadNetwork, ref_lat: float, ref_lon: float,
                     config: HeadingConstraintConfig | None = None) -> "HeadingConstraint":
        index = RoadIndex.build(project_network(network, ref_lat, ref_lon), network.junction_nodes)
        return cls(index, config or HeadingConstraintConfig())

    def _epoch(self, row: int, decision: Decision, n: int, bearing=None, innovation=None) -> Epoch:
        return Epoch(row, decision, n, bearing, innovation, math.radians(self.config.sigma_deg))

    def passes_gate(self, innovation_rad: float) -> bool:
        nis = (innovation_rad / math.radians(self.config.gate_sigma_deg)) ** 2
        return nis <= chi2.ppf(self.config.gate_confidence, df=1)

    def _survivors(self, cands: tuple[Candidate, ...], heading_rad: float) -> list[tuple[Candidate, float, bool]]:
        """(candidate, travel bearing, forward) for every candidate that may take part.

        With ``gate_candidates`` only those passing the innovation gate survive;
        otherwise all of them, with a wrong-way one-way road marked by None
        so the caller records a disagreement.
        """
        out = []
        for c in cands:
            sense = travel_bearing(c, heading_rad)
            if sense is None:
                if not self.config.gate_candidates:
                    return []
                continue
            if self.config.gate_candidates and not self.passes_gate(wrap(sense[0] - heading_rad)):
                continue
            out.append((c, sense[0], sense[1]))
        return out

    def step(self, state: ConstraintState, row: int, east: float, north: float,
             heading_rad: float) -> tuple[ConstraintState, Epoch]:
        """Evaluate one epoch. Pure: returns the successor state and its record."""
        cfg = self.config
        reset = ConstraintState()
        cands = self.index.candidates(east, north, cfg.search_radius_m)
        if not cands:
            far = self.index.candidates(east, north, cfg.disable_radius_m)
            return reset, self._epoch(row, Decision.DISABLED if not far else Decision.NO_CANDIDATES, 0)

        kept = self._survivors(cands, heading_rad)
        if not kept:
            rejected = Decision.REJECTED_GATE if cfg.gate_candidates else Decision.REJECTED_DISAGREEMENT
            return reset, self._epoch(row, rejected, len(cands))
        if not bearings_agree([b for _, b, _ in kept], math.radians(cfg.agreement_deg)):
            return reset, self._epoch(row, Decision.REJECTED_DISAGREEMENT, len(cands))

        if any(self.index.junction_ahead_m(c, fwd, cfg.junction_lookahead_m) <= cfg.junction_lookahead_m
               for c, _, fwd in kept):
            return reset, self._epoch(row, Decision.REJECTED_JUNCTION, len(cands))

        bearing = kept[0][1]
        innovation = wrap(bearing - heading_rad)
        if not self.passes_gate(innovation):
            return reset, self._epoch(row, Decision.REJECTED_GATE, len(cands), None, innovation)

        n = state.consistent_epochs + 1
        applied = n >= cfg.min_consistent_epochs
        decision = Decision.APPLIED if applied else Decision.WARMING
        return ConstraintState(n), self._epoch(row, decision, len(cands),
                                               bearing if applied else None, innovation)


class HeadingObserver:
    """Mutable adapter between the pure constraint and the pipeline's hook.

    ``pipeline_kinematic.run(heading_observer=...)`` wants a plain callable
    ``(row, east, north, heading_rad) -> (bearing_rad, sigma_rad) | None``.
    This holds the running :class:`ConstraintState` and the per-epoch record;
    the constraint itself never changes. Make a fresh one per run.
    """

    def __init__(self, constraint: HeadingConstraint) -> None:
        self.constraint = constraint
        self.state = ConstraintState()
        self.epochs: list[Epoch] = []

    @classmethod
    def from_network(cls, network: RoadNetwork, ref_lat: float, ref_lon: float,
                     config: HeadingConstraintConfig | None = None) -> "HeadingObserver":
        return cls(HeadingConstraint.from_network(network, ref_lat, ref_lon, config))

    def __call__(self, row: int, east: float, north: float, heading_rad: float) -> tuple[float, float] | None:
        self.state, epoch = self.constraint.step(self.state, row, east, north, heading_rad)
        self.epochs.append(epoch)
        if epoch.decision is Decision.APPLIED and epoch.bearing_rad is not None:
            return epoch.bearing_rad, epoch.sigma_rad
        return None

    def counts(self) -> dict[str, int]:
        out = {d.value: 0 for d in Decision}
        for epoch in self.epochs:
            out[epoch.decision.value] += 1
        return out
