"""Estimate the device-to-car rotation from motion.

Why this is not optional
------------------------
The nonholonomic constraint says a car has no lateral or vertical velocity *in
the car frame*. A phone sits in a cradle, a pocket or a cup holder at an
arbitrary orientation, so the device frame is not the car frame. Applying NHC
with an unestimated misalignment constrains velocity in the wrong plane and is
worse than not applying it at all -- measured here as 1312 m median error at a
10 s horizon, against 310 m for an unaided strapdown.

Method
------
Two axes, each from the signal that observes it best:

* **Vehicle up** from the long-run mean specific force. Over tens of seconds the
  vehicle's own accelerations average toward zero and gravity dominates. This is
  the same idea as the baseline's levelling, but over a long enough window that
  the 6 deg centripetal tilt documented in ``baselines/naive.py`` averages out.
* **Vehicle forward** from the correlation between horizontal specific force and
  longitudinal acceleration. When the car speeds up, the horizontal component of
  measured specific force points along the vehicle's forward axis. Regressing
  horizontal specific force against GNSS-derived longitudinal acceleration
  recovers that axis without ever needing a wheel sensor.

Right is then ``forward x up``, which fixes a right-handed car frame.

Freedom to operate
------------------
STMicroelectronics US11199410B2 is granted, in force, covers phone-in-arbitrary-
orientation misalignment and explicitly names tunnels. Its claim is tied to
*explicit axis determination*. This implementation is a correlation-weighted
estimate rather than an explicit axis decomposition, and PLAN.md:26 records the
intended design-around as learning the misalignment rather than computing it.
Treat this module as the classical bootstrap the learned version replaces, and
do not describe it as novel.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Alignment:
    """Device-to-car rotation with a quality score in [0, 1]."""

    rot_device_to_car: np.ndarray
    quality: float
    n_samples: int

    @staticmethod
    def identity() -> "Alignment":
        return Alignment(np.eye(3), 0.0, 0)

    def apply(self, vectors: np.ndarray) -> np.ndarray:
        """Rotate device-frame rows into the car frame."""
        return vectors @ self.rot_device_to_car.T


def _orthonormal_frame(forward: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Right-handed car frame with rows [right, forward, up], in device coords."""
    up = up / np.linalg.norm(up)
    forward = forward - (forward @ up) * up
    norm = float(np.linalg.norm(forward))
    if norm < 1e-9:
        # Forward unobservable; pick any axis perpendicular to up.
        seed = np.array([1.0, 0.0, 0.0])
        if abs(float(seed @ up)) > 0.9:
            seed = np.array([0.0, 1.0, 0.0])
        forward = seed - (seed @ up) * up
        norm = float(np.linalg.norm(forward))
    forward = forward / norm
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    return np.stack([right, forward, up], axis=0)


def estimate_alignment(
    acc: np.ndarray,
    gyro: np.ndarray,
    speed_ms: np.ndarray,
    time_s: np.ndarray,
    *,
    min_accel_ms2: float = 0.12,
    min_samples: int = 20,
) -> Alignment:
    """Recover the device-to-car rotation from a window of aided driving.

    ``speed_ms`` is the GNSS speed, which is available before a blackout by
    construction. Returns :meth:`Alignment.identity` with quality 0 when the
    window contains too little longitudinal excitation to observe the forward
    axis -- a straight, constant-speed approach is the degenerate case
    PLAN.md:191 warns about, and reporting low quality is the honest response.
    """
    acc = np.asarray(acc, dtype=float)
    if len(acc) < min_samples or len(speed_ms) != len(acc):
        return Alignment.identity()

    up = acc.mean(axis=0)
    norm = float(np.linalg.norm(up))
    if norm < 1e-6:
        return Alignment.identity()
    up = up / norm

    # Longitudinal acceleration from GNSS speed. The speed column is held
    # between fixes, so difference it only where it actually changes -- a naive
    # gradient over held values yields a train of spikes separated by zeros.
    valid = np.isfinite(speed_ms)
    idx = np.flatnonzero(valid)
    if idx.size < 3:
        return Alignment.identity()
    changed = idx[np.r_[True, np.diff(speed_ms[idx]) != 0.0]]
    if changed.size < 3:
        return Alignment.identity()

    dv = np.diff(speed_ms[changed])
    dt = np.diff(time_s[changed])
    good = dt > 0
    if good.sum() < 2:
        return Alignment.identity()
    a_long = dv[good] / dt[good]

    # Pair each interval mean longitudinal acceleration with the *mean*
    # horizontal specific force over the same interval, not a single endpoint
    # sample. GNSS fixes are a median of 9 s apart, so dv/dt is already an
    # interval average; matching it against one instantaneous reading compares
    # a smoothed quantity to an unsmoothed one and the correlation collapses
    # into noise. Measured: endpoint pairing produced quality 0.0 on every
    # sequence tried, i.e. the alignment silently never worked.
    starts = changed[:-1][good]
    stops = changed[1:][good]
    horiz = np.empty((len(a_long), 3))
    for k, (a, b) in enumerate(zip(starts, stops)):
        mean_f = acc[a : b + 1].mean(axis=0)
        horiz[k] = mean_f - (mean_f @ up) * up

    strong = np.abs(a_long) >= min_accel_ms2
    if strong.sum() < 3:
        return Alignment.identity()
    horiz = horiz[strong]
    a_long = a_long[strong]

    # Direction whose horizontal specific force best tracks longitudinal
    # acceleration. Weighting by a_long makes braking and acceleration agree on
    # a sign instead of cancelling.
    forward = horiz.T @ a_long
    if float(np.linalg.norm(forward)) < 1e-9:
        return Alignment.identity()

    rot = _orthonormal_frame(forward, up)

    # Quality: how much of the horizontal signal the recovered axis explains.
    unit_forward = rot[1]
    projected = horiz @ unit_forward
    denom = float(np.sum(np.linalg.norm(horiz, axis=1) ** 2))
    quality = float(np.sum(projected**2) / denom) if denom > 1e-12 else 0.0
    return Alignment(rot, float(np.clip(quality, 0.0, 1.0)), int(strong.sum()))
