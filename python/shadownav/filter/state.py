"""21-state navigation state and SO(3) helpers.

State layout, matching the AVNet/AI-IMU-DR decomposition (PLAN.md:76):

    R      navigation rotation, body -> ENU            SO(3)
    v      velocity in ENU                             R^3
    p      position in ENU                             R^3
    b_g    gyroscope bias, body frame                   R^3
    b_a    accelerometer bias, body frame               R^3
    R_c    device -> car-body misalignment              SO(3)
    p_c    lever arm, device origin to car origin       R^3

The error state is 21-dimensional in the order

    [ dtheta | dv | dp | db_g | db_a | dtheta_c | dp_c ]
       0:3    3:6   6:9   9:12   12:15   15:18    18:21

with attitude errors defined on the *right*: ``R = R_hat Exp(dtheta)``, so
dtheta lives in the body frame. That convention is chosen because both
measurement models used here -- the nonholonomic constraint and the learned
forward-speed pseudo-measurement -- are expressed in the car frame, and a
body-frame error keeps their Jacobians free of the navigation rotation.

Learning the misalignment ``R_c`` rather than determining it by explicit axis
decomposition is deliberate: STMicroelectronics US11199410B2 is granted, in
force, explicitly names tunnels, and ties its claim to explicit axis
determination. See research/SIH26168-open-track-findings.md Track G.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

GRAVITY = np.array([0.0, 0.0, -9.80665])

DIM = 21
I_THETA = slice(0, 3)
I_V = slice(3, 6)
I_P = slice(6, 9)
I_BG = slice(9, 12)
I_BA = slice(12, 15)
I_THETA_C = slice(15, 18)
I_PC = slice(18, 21)


def skew(v: np.ndarray) -> np.ndarray:
    """Matrix form of the cross product: ``skew(a) @ b == cross(a, b)``."""
    x, y, z = v
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def exp_so3(phi: np.ndarray) -> np.ndarray:
    """Rodrigues exponential map, with a small-angle branch."""
    theta = float(np.linalg.norm(phi))
    k = skew(phi)
    if theta < 1e-8:
        return np.eye(3) + k + 0.5 * (k @ k)
    return (
        np.eye(3)
        + (np.sin(theta) / theta) * k
        + ((1.0 - np.cos(theta)) / (theta * theta)) * (k @ k)
    )


def log_so3(rot: np.ndarray) -> np.ndarray:
    """Inverse of :func:`exp_so3`."""
    cos_theta = (np.trace(rot) - 1.0) / 2.0
    cos_theta = float(np.clip(cos_theta, -1.0, 1.0))
    theta = float(np.arccos(cos_theta))
    if theta < 1e-8:
        return np.array([rot[2, 1] - rot[1, 2],
                         rot[0, 2] - rot[2, 0],
                         rot[1, 0] - rot[0, 1]]) / 2.0
    w = np.array([rot[2, 1] - rot[1, 2],
                  rot[0, 2] - rot[2, 0],
                  rot[1, 0] - rot[0, 1]])
    return w * (theta / (2.0 * np.sin(theta)))


def right_jacobian_so3(phi: np.ndarray) -> np.ndarray:
    """Right Jacobian of SO(3). Used for the gyro-bias coupling block."""
    theta = float(np.linalg.norm(phi))
    if theta < 1e-8:
        return np.eye(3) - 0.5 * skew(phi)
    k = skew(phi / theta)
    return (
        np.eye(3)
        - ((1.0 - np.cos(theta)) / theta) * k
        + ((theta - np.sin(theta)) / theta) * (k @ k)
    )


def orthonormalise(rot: np.ndarray) -> np.ndarray:
    """Project back onto SO(3). Repeated small updates drift off the manifold."""
    u, _, vt = np.linalg.svd(rot)
    out = u @ vt
    if np.linalg.det(out) < 0:
        u[:, -1] *= -1.0
        out = u @ vt
    return out


def heading_of(rot: np.ndarray) -> float:
    """Course of body-forward (+y) in radians clockwise from north."""
    fwd = rot @ np.array([0.0, 1.0, 0.0])
    return float(np.arctan2(fwd[0], fwd[1]))


@dataclass(frozen=True)
class NavState:
    """Immutable navigation state. Updates return a new instance."""

    rot: np.ndarray
    vel: np.ndarray
    pos: np.ndarray
    bias_gyro: np.ndarray
    bias_acc: np.ndarray
    rot_car: np.ndarray
    lever: np.ndarray

    @staticmethod
    def initial(
        rot: np.ndarray,
        vel: np.ndarray,
        pos: np.ndarray | None = None,
    ) -> "NavState":
        return NavState(
            rot=np.asarray(rot, dtype=float),
            vel=np.asarray(vel, dtype=float),
            pos=np.zeros(3) if pos is None else np.asarray(pos, dtype=float),
            bias_gyro=np.zeros(3),
            bias_acc=np.zeros(3),
            rot_car=np.eye(3),
            lever=np.zeros(3),
        )

    @property
    def heading_rad(self) -> float:
        return heading_of(self.rot)

    @property
    def speed_ms(self) -> float:
        return float(np.linalg.norm(self.vel[:2]))

    def car_velocity(self, gyro_corrected: np.ndarray) -> np.ndarray:
        """Velocity in the car frame: ``[lateral, forward, vertical]``.

        Includes the lever-arm term ``omega x p_c``: the device is not at the
        car's rotation centre, so during a turn it has a velocity component the
        car body does not, and the nonholonomic constraint is written on the
        car body.
        """
        body_v = self.rot.T @ self.vel + np.cross(gyro_corrected, self.lever)
        return self.rot_car.T @ body_v

    def inject(self, dx: np.ndarray) -> "NavState":
        """Apply a 21-vector error-state correction, returning a new state."""
        return NavState(
            rot=orthonormalise(self.rot @ exp_so3(dx[I_THETA])),
            vel=self.vel + dx[I_V],
            pos=self.pos + dx[I_P],
            bias_gyro=self.bias_gyro + dx[I_BG],
            bias_acc=self.bias_acc + dx[I_BA],
            rot_car=orthonormalise(self.rot_car @ exp_so3(dx[I_THETA_C])),
            lever=self.lever + dx[I_PC],
        )

    def replace(self, **kw) -> "NavState":
        return replace(self, **kw)
