"""Naive strapdown INS -- the drift floor, on purpose.

This is the number every later claim is measured against. It is deliberately
unaided: attitude propagated by integrating gyroscope only, gravity removed
analytically, acceleration double-integrated. No zero-velocity update, no
nonholonomic constraint, no learned correction, no map.

It is also strictly PS-scoped: accelerometer and gyroscope only. The dataset's
GRAVITY, MAGNETIC FIELD and ORIENTATION columns are fused outputs of the phone's
own sensor stack and using them would quietly import a magnetometer into a
system that claims not to have one (PLAN.md:13).

Expect this to fail badly. A competitor documents ">1000% error" for the same
construction (dossier section 10, tannaakshat447). That failure is the point:
it is the denominator for every improvement claimed later.

Initialisation
--------------
Attitude comes from the measured gravity direction over a pre-outage window,
which fixes roll and pitch but leaves heading unobservable from accelerometer
and gyroscope alone. Heading is therefore seeded from the last GNSS course
before the outage -- legitimate, since the outage is what we are simulating and
GNSS is present right up to its start.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..data.iovnbd import Sequence

GRAVITY_MS2 = 9.80665


@dataclass(frozen=True)
class DeadReckonResult:
    """Trajectory produced by an unaided strapdown integration."""

    east_m: np.ndarray
    north_m: np.ndarray
    speed_ms: np.ndarray
    heading_rad: np.ndarray


def _skew(v: np.ndarray) -> np.ndarray:
    return np.array(
        [[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]]
    )


def _exp_so3(omega: np.ndarray) -> np.ndarray:
    """Rodrigues exponential map. Small-angle branch avoids 0/0 at rest."""
    theta = float(np.linalg.norm(omega))
    k = _skew(omega)
    if theta < 1e-9:
        return np.eye(3) + k
    return (
        np.eye(3)
        + (np.sin(theta) / theta) * k
        + ((1.0 - np.cos(theta)) / theta**2) * (k @ k)
    )


def initial_attitude(acc: np.ndarray, heading_rad: float) -> np.ndarray:
    """Body-to-navigation rotation from mean specific force plus a heading.

    Roll and pitch come from where gravity points; heading is not observable
    from accelerometer and gyroscope alone and must be supplied.

    Conventions, stated because a sign error here is invisible downstream:
      body   x right, y forward, z up
      nav    ENU -- east, north, up
      heading  radians clockwise from north, so a vehicle on heading psi has
               forward = (sin psi, cos psi, 0) in ENU

    The frame is built so the result is a proper rotation (det +1). Building it
    from two cross products in the wrong order yields a reflection, which
    integrates into a mirrored trajectory that looks plausible until it is
    compared against truth.
    """
    f_body = np.mean(acc, axis=0)
    norm = float(np.linalg.norm(f_body))
    if norm < 1e-6:
        return np.eye(3)

    # At rest the accelerometer reads +g along body-up, so specific force
    # points along nav up expressed in body coordinates.
    up_b = f_body / norm

    # Body-frame direction of nav north: body forward, levelled against up_b.
    fwd_b = np.array([0.0, 1.0, 0.0])
    if abs(float(fwd_b @ up_b)) > 0.99:  # phone pointing straight up or down
        fwd_b = np.array([1.0, 0.0, 0.0])
    fwd_b = fwd_b - (fwd_b @ up_b) * up_b
    fwd_b /= np.linalg.norm(fwd_b)

    # ENU is right-handed: north x up = east.
    east_b = np.cross(fwd_b, up_b)
    east_b /= np.linalg.norm(east_b)

    # Rows are the nav axes in body coordinates, so R @ v_body = v_nav.
    r_level = np.stack([east_b, fwd_b, up_b], axis=0)

    # Rotate about nav up so body-forward maps to (sin psi, cos psi, 0).
    c, s = np.cos(heading_rad), np.sin(heading_rad)
    r_head = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    return r_head @ r_level


def select_alignment_window(
    acc: np.ndarray, gyr: np.ndarray, lo: int, hi: int, width: int = 10
) -> slice:
    """Pick the most static-looking sub-window for gravity levelling.

    Levelling on the mean specific force assumes the only acceleration is
    gravity. On a turning or braking vehicle it is not, and the error is
    vicious: a centripetal 1.04 m/s^2 tilts the estimated vertical by 6 deg,
    which mis-projects gravity by g*sin(6 deg) = 1.03 m/s^2 of pure horizontal
    error. Double-integrated over 20 s that is 206 m -- larger than the distance
    travelled. Measured on a synthetic 6 deg/s turn, so this is not a
    hypothetical.

    Scoring each candidate by how close its mean specific force is to g, plus
    its gyroscope energy, finds the quietest moment available. It does not make
    the baseline good -- it makes its failure attributable to integration drift
    rather than to a levelling blunder, which is what a floor has to be.
    """
    hi = max(hi, lo + width)
    best_score = np.inf
    best = slice(max(lo, hi - width), hi)
    for start in range(lo, hi - width + 1):
        sl = slice(start, start + width)
        f = acc[sl]
        mag_err = abs(float(np.linalg.norm(f.mean(axis=0))) - GRAVITY_MS2)
        spread = float(np.mean(np.std(f, axis=0)))
        rotation = float(np.mean(np.abs(gyr[sl])))
        score = mag_err + spread + 5.0 * rotation
        if score < best_score:
            best_score, best = score, sl
    return best


def dead_reckon(
    seq: Sequence,
    start_row: int,
    end_row: int,
    *,
    init_speed_ms: float,
    init_heading_rad: float,
    align_rows: int = 50,
    init_rotation: np.ndarray | None = None,
) -> DeadReckonResult:
    """Integrate accelerometer and gyroscope from ``start_row`` to ``end_row``.

    Returns east/north displacement in metres relative to ``start_row``.

    ``init_rotation`` overrides the gravity-levelling step. Phase 1 supplies
    attitude from the filter; the tests supply an exact rotation so that the
    integrator can be validated independently of the aligner.
    """
    t = seq.time_s
    acc = seq.df[["acc_x", "acc_y", "acc_z"]].to_numpy(dtype=float)
    gyr = seq.df[["gyr_x", "gyr_y", "gyr_z"]].to_numpy(dtype=float)

    if init_rotation is not None:
        rot = np.asarray(init_rotation, dtype=float)
    else:
        align_lo = max(0, start_row - align_rows)
        sl = select_alignment_window(acc, gyr, align_lo, start_row + 1)
        rot = initial_attitude(acc[sl], init_heading_rad)

    n = end_row - start_row + 1
    east = np.zeros(n)
    north = np.zeros(n)
    speed = np.zeros(n)
    heading = np.zeros(n)

    # Initial velocity along the seeded heading, in the navigation frame.
    vel = np.array(
        [
            init_speed_ms * np.sin(init_heading_rad),
            init_speed_ms * np.cos(init_heading_rad),
            0.0,
        ]
    )
    gravity = np.array([0.0, 0.0, -GRAVITY_MS2])
    pos = np.zeros(3)
    speed[0] = init_speed_ms
    heading[0] = init_heading_rad

    for i in range(1, n):
        row = start_row + i
        dt = float(t[row] - t[row - 1])

        rot = rot @ _exp_so3(gyr[row - 1] * dt)
        a_nav = rot @ acc[row - 1] + gravity

        # Trapezoidal position update: the velocity at both ends of the step.
        vel_next = vel + a_nav * dt
        pos = pos + 0.5 * (vel + vel_next) * dt
        vel = vel_next

        east[i] = pos[0]
        north[i] = pos[1]
        speed[i] = float(np.linalg.norm(vel[:2]))
        heading[i] = float(np.arctan2(vel[0], vel[1]))

    return DeadReckonResult(east, north, speed, heading)
