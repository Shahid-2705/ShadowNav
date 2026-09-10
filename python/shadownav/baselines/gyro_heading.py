"""Speed-hold plus gyroscope heading comparator.

The last GNSS speed is held; heading is integrated from the gyroscope's
component about the vehicle's vertical, with no bias state, no nonholonomic
constraint, no Ackermann bound and no filter. It is the simplest thing that
uses the gyroscope, and the difference between it and the full kinematic EKF
is what the EKF's extra machinery is actually worth.

Conventions match :class:`shadownav.filter.kinematic.KinematicEKF`: heading is
clockwise from north and its rate is *minus* the gyro rate about up, because
ENU is right-handed about up. The vertical comes from the long-run mean
specific force before the outage, exactly as the deployed pipeline does when
no device-to-car alignment is available.
"""

from __future__ import annotations

import numpy as np

from ..data.iovnbd import Sequence
from .naive import DeadReckonResult


def vertical_from_specific_force(acc: np.ndarray) -> np.ndarray:
    """Unit body-frame up vector from the mean specific force."""
    up = np.mean(np.asarray(acc, dtype=float), axis=0)
    norm = float(np.linalg.norm(up))
    if norm < 1e-9:
        return np.array([0.0, 0.0, 1.0])
    return up / norm


def dead_reckon(
    seq: Sequence,
    start_row: int,
    end_row: int,
    *,
    init_speed_ms: float,
    init_heading_rad: float,
    level_rows: int = 600,
) -> DeadReckonResult:
    """Integrate heading from the gyroscope, hold speed, from ``start_row``."""
    t = seq.time_s
    acc = seq.df[["acc_x", "acc_y", "acc_z"]].to_numpy(dtype=float)
    gyr = seq.df[["gyr_x", "gyr_y", "gyr_z"]].to_numpy(dtype=float)

    lo = max(0, start_row - level_rows)
    up_b = vertical_from_specific_force(acc[lo : start_row + 1])
    yaw_rate = gyr @ up_b

    n = end_row - start_row + 1
    east = np.zeros(n)
    north = np.zeros(n)
    heading = np.zeros(n)
    heading[0] = float(init_heading_rad)
    v = float(init_speed_ms)

    for i in range(1, n):
        row = start_row + i
        dt = float(t[row] - t[row - 1])
        psi = heading[i - 1]
        east[i] = east[i - 1] + v * np.sin(psi) * dt
        north[i] = north[i - 1] + v * np.cos(psi) * dt
        heading[i] = psi - float(yaw_rate[row - 1]) * dt

    return DeadReckonResult(
        east_m=east,
        north_m=north,
        speed_ms=np.full(n, v),
        heading_rad=heading,
    )
