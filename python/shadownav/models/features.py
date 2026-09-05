"""Rotation-invariant IMU features for the learned speed front end.

Why invariant features rather than raw axes
-------------------------------------------
A phone sits at an arbitrary, unknown orientation in the vehicle. Feeding raw
device-frame accelerometer and gyroscope axes forces the network to learn that
invariance from data, and there are only ~14,000 speed labels in the whole
dataset (one per real GNSS fix -- see ``scripts/audit_gps_rate.py``). That is
far too few to learn a 3-D rotation group from scratch, and a network that
half-learns it generalises to a new mounting by chance.

So the six channels below are constructed to be invariant to rotation about the
vertical, and to depend on the device frame only through the gravity direction,
which the long-run mean specific force gives for free and reliably:

    |a|            specific-force magnitude
    a . up         vertical specific force (gravity plus climb/dip)
    |a_horiz|      horizontal specific-force magnitude
    |w|            angular-rate magnitude
    w . up         yaw rate -- the single most informative channel for a vehicle
    |w_horiz|      pitch/roll rate magnitude, i.e. road roughness and body motion

What is deliberately NOT an input
---------------------------------
The last known GNSS speed and its age are excluded. Feeding them lets the
network minimise its loss by echoing its input, which scores beautifully in
training and does nothing during the long blackout it exists to survive -- the
circularity PLAN.md:50 warns about for the speed router. The network must earn
its speed estimate from inertial data alone.
"""

from __future__ import annotations

import numpy as np

N_CHANNELS = 6
CHANNEL_NAMES = (
    "acc_mag", "acc_vertical", "acc_horizontal",
    "gyr_mag", "gyr_yaw", "gyr_horizontal",
)


def gravity_direction(acc: np.ndarray) -> np.ndarray:
    """Unit vertical in device coordinates, from the long-run mean.

    Over tens of seconds a vehicle's own accelerations average toward zero and
    gravity dominates. Short windows do not work: a centripetal 1.04 m/s^2
    tilts the estimate by 6 degrees (see ``baselines/naive.py``).
    """
    mean = np.asarray(acc, dtype=float).mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm < 1e-6:
        return np.array([0.0, 0.0, 1.0])
    return mean / norm


def invariant_features(acc: np.ndarray, gyr: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Build the ``(N, 6)`` feature block for one window."""
    acc = np.asarray(acc, dtype=float)
    gyr = np.asarray(gyr, dtype=float)
    up = np.asarray(up, dtype=float)
    up = up / max(float(np.linalg.norm(up)), 1e-9)

    a_vert = acc @ up
    g_vert = gyr @ up
    a_h = acc - np.outer(a_vert, up)
    g_h = gyr - np.outer(g_vert, up)

    return np.stack(
        [
            np.linalg.norm(acc, axis=1),
            a_vert,
            np.linalg.norm(a_h, axis=1),
            np.linalg.norm(gyr, axis=1),
            g_vert,
            np.linalg.norm(g_h, axis=1),
        ],
        axis=1,
    )
