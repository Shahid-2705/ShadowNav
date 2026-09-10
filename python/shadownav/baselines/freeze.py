"""Freeze-the-last-fix comparator.

The comparator a judge thinks of first: when GNSS goes, leave the dot where
the last fix put it. Its error at the first fix back is exactly the vehicle's
displacement during the outage, so any estimator whose error exceeds the
distance driven is doing worse than nothing.

It is scored through the same masking harness and the same metric as every
other method, so the comparison is like-for-like.
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
    """Zero displacement from ``start_row`` to ``end_row``."""
    n = end_row - start_row + 1
    zeros = np.zeros(n)
    return DeadReckonResult(
        east_m=zeros,
        north_m=zeros.copy(),
        speed_ms=zeros.copy(),
        heading_rad=np.full(n, float(init_heading_rad)),
    )
