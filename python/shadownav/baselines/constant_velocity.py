"""Constant-velocity comparator.

Hold the last GNSS speed and course and extrapolate in a straight line. This
is what a map application effectively does for the first seconds of a tunnel,
and it uses no inertial sensor at all. Everything the gyroscope contributes
is the gap between this comparator and :mod:`gyro_heading`.
"""

from __future__ import annotations

import numpy as np

from ..data.iovnbd import Sequence
from .naive import DeadReckonResult


def dead_reckon(
    seq: Sequence,
    start_row: int,
    end_row: int,
    *,
    init_speed_ms: float,
    init_heading_rad: float,
) -> DeadReckonResult:
    """Straight-line extrapolation at the initial speed and heading."""
    t = seq.time_s
    elapsed = t[start_row : end_row + 1] - t[start_row]
    along = float(init_speed_ms) * elapsed
    n = elapsed.size
    return DeadReckonResult(
        east_m=along * np.sin(init_heading_rad),
        north_m=along * np.cos(init_heading_rad),
        speed_ms=np.full(n, float(init_speed_ms)),
        heading_rad=np.full(n, float(init_heading_rad)),
    )
