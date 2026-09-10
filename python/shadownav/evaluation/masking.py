"""Synthetic GNSS outage masking.

All evaluation uses synthetic masking. IO-VNBD's real receiver dropouts are
documented only as row-index exclusions inside the zip archives, have no valid
ground truth while they last, and Onyekpe's own code slices around them as
corrupt (Track H). There is nothing to score against during a real dropout, so
they are excluded rather than used.

The measured GPS fix period is a median of 9.0 s across the dataset, not the
1 Hz Track H states (see ``scripts/audit_gps_rate.py``). That has a direct
consequence for masking: a 10 s outage removes roughly one real fix and a 30 s
outage roughly three. :class:`OutageWindow` therefore records how many real
fixes it actually suppressed, so a result computed over an outage that hid
almost no information cannot be mistaken for a hard one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..data.iovnbd import Sequence
from ..utils.seed import rng

#: WhONet's outage horizons, kept for comparability of shape even though the
#: benchmark itself is not reproducible smartphone-only (PLAN.md:151).
STANDARD_HORIZONS_S: tuple[float, ...] = (10.0, 30.0, 60.0, 120.0, 180.0)


@dataclass(frozen=True)
class OutageWindow:
    """One synthetic GNSS outage over a sequence."""

    sequence: str
    start_s: float
    duration_s: float
    start_row: int
    end_row: int
    n_fixes_suppressed: int
    distance_m: float

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s

    @property
    def informative(self) -> bool:
        """Did this outage actually hide any GNSS information?

        An outage spanning zero real fixes is not a test of dead reckoning, it
        is a test of interpolation. Given the 9 s fix period, short horizons
        produce these routinely, and they must not be averaged in silently.
        """
        return self.n_fixes_suppressed >= 1


def _distance_between_rows(seq: Sequence, a: int, b: int) -> float:
    speed = seq.df["gps_speed_ms"].to_numpy()[a:b]
    dt = np.diff(seq.time_s[a : b + 1]) if b + 1 <= len(seq) else np.diff(seq.time_s[a:b])
    n = min(len(speed), len(dt))
    return float(np.sum(speed[:n] * dt[:n]))


def make_window(seq: Sequence, start_s: float, duration_s: float) -> OutageWindow:
    """Build one outage window, measuring what it actually suppresses."""
    t = seq.time_s
    start_row = int(np.searchsorted(t, start_s, side="left"))
    end_row = int(np.searchsorted(t, start_s + duration_s, side="left"))
    end_row = min(end_row, len(seq) - 1)

    is_new = seq.df["gps_fix_is_new"].to_numpy()
    n_fixes = int(is_new[start_row:end_row].sum())

    return OutageWindow(
        sequence=seq.name,
        start_s=float(t[start_row]),
        duration_s=duration_s,
        start_row=start_row,
        end_row=end_row,
        n_fixes_suppressed=n_fixes,
        distance_m=_distance_between_rows(seq, start_row, end_row),
    )


def plan_outages(
    seq: Sequence,
    duration_s: float,
    *,
    n: int = 5,
    seed: int | None = None,
    min_speed_ms: float = 1.0,
    guard_s: float = 5.0,
) -> list[OutageWindow]:
    """Place ``n`` outages of ``duration_s`` at deterministic random starts.

    Windows are placed only where the vehicle is actually moving: an outage
    while parked is trivially survivable and would flatter every metric.
    ``guard_s`` keeps a margin at both ends so there is pre-outage context to
    initialise from and post-outage data to measure re-acquisition against.
    """
    t = seq.time_s
    speed = seq.df["gps_speed_ms"].to_numpy()
    latest_start = float(t[-1]) - duration_s - guard_s
    if latest_start <= guard_s:
        return []

    generator = rng(seed)
    candidates: list[OutageWindow] = []
    # Deterministic scan over a fixed grid, shuffled by the seeded generator --
    # avoids rejection-sampling loops whose iteration count depends on the data.
    grid = np.arange(guard_s, latest_start, max(duration_s / 2.0, 1.0))
    if grid.size == 0:
        return []
    order = generator.permutation(grid.size)

    for idx in order:
        start = float(grid[idx])
        w = make_window(seq, start, duration_s)
        if w.end_row <= w.start_row:
            continue
        if float(np.mean(speed[w.start_row : w.end_row])) < min_speed_ms:
            continue
        if any(abs(w.start_s - c.start_s) < duration_s for c in candidates):
            continue
        candidates.append(w)
        if len(candidates) >= n:
            break

    return sorted(candidates, key=lambda w: w.start_s)


def extend_to_row(seq: Sequence, window: OutageWindow, end_row: int) -> OutageWindow:
    """Return the window stretched so the mask covers ``end_row`` inclusive.

    Why this exists. Metrics are scored at the first *real* GPS fix at or after
    the horizon, because that is the earliest instant ground truth exists. With
    the mask ending exactly at the horizon, that fix is also the first fix the
    estimator is allowed to see -- so the estimator would be corrected by the
    very observation used to score it, in the same sample, before its position
    is recorded. The chi-square gate hid most of that (a large innovation is
    rejected), but "the metric is safe because the gate usually fires" is not a
    protocol. Stretching the outage to the scoring instant makes the estimate
    at that instant unconditionally unaided.

    The cost is that the scored outage is longer than the requested horizon by
    up to one fix period. That was already true of the reported metric --
    ``t_eval_s`` records it -- and it is now true of the estimator's experience
    as well, which is the consistent choice.
    """
    end = max(window.end_row, int(end_row) + 1)
    is_new = seq.df["gps_fix_is_new"].to_numpy()
    return OutageWindow(
        sequence=window.sequence,
        start_s=window.start_s,
        duration_s=window.duration_s,
        start_row=window.start_row,
        end_row=end,
        n_fixes_suppressed=int(is_new[window.start_row : end].sum()),
        distance_m=_distance_between_rows(seq, window.start_row, end),
    )


def apply_mask(seq: Sequence, window: OutageWindow) -> Sequence:
    """Return a new Sequence with GNSS suppressed inside the window.

    Never mutates the input. GNSS columns are set to NaN rather than dropped so
    row indices, IMU data and timestamps stay aligned with the original -- the
    estimator must keep running at 10 Hz through the outage, which is the whole
    point.
    """
    df = seq.df.copy()
    mask = np.zeros(len(df), dtype=bool)
    mask[window.start_row : window.end_row] = True

    for col in (
        "gps_lat_deg", "gps_lon_deg", "gps_alt_m",
        "gps_speed_kmh", "gps_speed_ms",
        "gps_accuracy_m", "gps_orientation_deg",
    ):
        if col in df.columns:
            df.loc[mask, col] = np.nan
    df.loc[mask, "gps_sats_used"] = 0
    df.loc[mask, "gps_fix_is_new"] = False
    df["gnss_available"] = ~mask

    return Sequence(seq.name, seq.path, df, seq.repair)
