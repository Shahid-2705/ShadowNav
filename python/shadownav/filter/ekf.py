"""Nonholonomic error-state EKF for smartphone vehicle dead reckoning.

What this is, stated precisely
------------------------------
An error-state EKF with the attitude error carried on the manifold
(``R = R_hat Exp(dtheta)``, body-frame error), 21 states, with nonholonomic
car-frame velocity constraints and an optional learned forward-speed
pseudo-measurement. This is the numerical structure of ``mbrossar/ai-imu-dr``
(MIT), which PLAN.md:115 names as the licensed base to build from.

It is **not** yet the fully invariant filter (Barrau & Bonnabel) whose
propagation Jacobian is state-independent. That upgrade buys consistency, not
accuracy, and is a Phase 2 item. Calling this an InEKF today would overclaim,
which PLAN.md:196 lists as a top project risk -- so it is called what it is.

Measurements
------------
* **Nonholonomic constraint (always on).** A car does not slide sideways and
  does not leave the road surface, so lateral and vertical velocity in the car
  frame are zero. Two constraints per step, free, no extra sensor, and
  wheelbase-free (PLAN.md:104).
* **Forward speed (optional).** The learned pseudo-measurement from the CNN+GRU
  front end. Without it the filter has no speed observability during a blackout
  beyond integrating the accelerometer, which is exactly the case GNIO
  identifies as the hard one for vehicles.
* **GNSS position (when available).** Gated by a chi-square test on the
  normalised innovation, plus C/N0-based de-weighting.

The chi-square gate is the MVP-scoped answer to the urban canyon (PLAN.md:139):
GNSS there is never *lost*, it lies, so an outage FSM never fires and a filter
that trusts every fix inherits >50 m NLOS errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import chi2

from .state import (
    DIM, GRAVITY, I_BA, I_BG, I_P, I_PC, I_THETA, I_THETA_C, I_V,
    NavState, exp_so3, right_jacobian_so3, skew,
)


@dataclass(frozen=True)
class FilterConfig:
    """Noise parameters. Defaults are smartphone-MEMS order-of-magnitude."""

    # Process noise, continuous-time densities.
    sigma_gyro: float = 2.0e-3          # rad/s/sqrt(Hz)
    sigma_acc: float = 2.0e-2           # m/s^2/sqrt(Hz)
    sigma_bias_gyro: float = 1.0e-5     # rad/s^2/sqrt(Hz)
    sigma_bias_acc: float = 1.0e-4      # m/s^3/sqrt(Hz)
    sigma_rot_car: float = 1.0e-6       # misalignment random walk
    sigma_lever: float = 1.0e-6

    # Measurement noise.
    sigma_nhc: float = 0.15             # m/s, lateral and vertical
    sigma_flat: float = 0.30            # m/s, nav-frame vertical velocity
    sigma_speed: float = 0.6            # m/s, learned forward speed
    sigma_gps_pos: float = 3.0          # m, scaled by reported accuracy
    sigma_gps_vel: float = 0.5          # m/s, Doppler speed is good

    # Initial uncertainty.
    p0_theta: float = 0.05
    p0_vel: float = 0.5
    p0_pos: float = 1.0
    p0_bias_gyro: float = 0.02
    p0_bias_acc: float = 0.2
    p0_rot_car: float = 0.05
    p0_lever: float = 0.3

    # Innovation gating.
    gate_confidence: float = 0.997      # chi-square tail for GNSS rejection
    max_lever_m: float = 3.0            # a phone is inside the car, not outside
    #: Consecutive rejections after which the gate is overridden and the
    #: state re-anchored. Without this a diverged filter rejects every fix
    #: forever and can never recover -- a real field bug, documented in
    #: dossier section 10 where a competitor hardcoded accuracy gate
    #: trapped their engine in DR mode for 2h13m.
    max_consecutive_rejections: int = 3

    def initial_covariance(self) -> np.ndarray:
        d = np.concatenate([
            np.full(3, self.p0_theta**2),
            np.full(3, self.p0_vel**2),
            np.full(3, self.p0_pos**2),
            np.full(3, self.p0_bias_gyro**2),
            np.full(3, self.p0_bias_acc**2),
            np.full(3, self.p0_rot_car**2),
            np.full(3, self.p0_lever**2),
        ])
        return np.diag(d)


@dataclass
class FilterDiagnostics:
    """Per-step record. Everything a claim might later rest on."""

    n_gps_accepted: int = 0
    n_gps_rejected: int = 0
    n_gate_overrides: int = 0
    consecutive_rejections: int = 0
    nis_history: list[float] = field(default_factory=list)
    speed_used: int = 0


class NonholonomicEKF:
    """Error-state EKF. ``state`` and ``cov`` are the filter's only mutables."""

    def __init__(self, state: NavState, config: FilterConfig | None = None,
                 cov: np.ndarray | None = None) -> None:
        self.config = config or FilterConfig()
        self.state = state
        self.cov = self.config.initial_covariance() if cov is None else cov.copy()
        self.diagnostics = FilterDiagnostics()

    # -- propagation ----------------------------------------------------

    def _process_noise(self, dt: float) -> np.ndarray:
        c = self.config
        q = np.zeros(DIM)
        q[I_THETA] = c.sigma_gyro**2 * dt
        q[I_V] = c.sigma_acc**2 * dt
        q[I_P] = c.sigma_acc**2 * dt**3 / 3.0
        q[I_BG] = c.sigma_bias_gyro**2 * dt
        q[I_BA] = c.sigma_bias_acc**2 * dt
        q[I_THETA_C] = c.sigma_rot_car**2 * dt
        q[I_PC] = c.sigma_lever**2 * dt
        return np.diag(q)

    def transition_matrix(self, gyro: np.ndarray, acc: np.ndarray, dt: float) -> np.ndarray:
        """Discrete error-state transition.

        Derived from the standard error dynamics for a body-frame attitude
        error. Verified numerically against a finite difference of the
        nonlinear propagation in ``test_ekf.py`` -- a hand-derived Jacobian
        that is never checked is the classic way a filter ends up quietly
        inconsistent.
        """
        omega = gyro - self.state.bias_gyro
        a_body = acc - self.state.bias_acc
        rot = self.state.rot

        f = np.eye(DIM)
        f[I_THETA, I_THETA] = exp_so3(-omega * dt)
        f[I_THETA, I_BG] = -right_jacobian_so3(omega * dt) * dt

        ra_skew = rot @ skew(a_body)
        f[I_V, I_THETA] = -ra_skew * dt
        f[I_V, I_BA] = -rot * dt

        f[I_P, I_V] = np.eye(3) * dt
        f[I_P, I_THETA] = -0.5 * ra_skew * dt**2
        f[I_P, I_BA] = -0.5 * rot * dt**2
        return f

    def propagate(self, gyro: np.ndarray, acc: np.ndarray, dt: float) -> None:
        """One IMU step. Mutates ``state`` and ``cov``."""
        if dt <= 0:
            return
        omega = gyro - self.state.bias_gyro
        a_body = acc - self.state.bias_acc
        rot = self.state.rot
        a_nav = rot @ a_body + GRAVITY

        new = self.state.replace(
            rot=self.state.rot @ exp_so3(omega * dt),
            vel=self.state.vel + a_nav * dt,
            pos=self.state.pos + self.state.vel * dt + 0.5 * a_nav * dt**2,
        )
        f = self.transition_matrix(gyro, acc, dt)
        self.state = new.replace(rot=_renorm(new.rot))
        self.cov = f @ self.cov @ f.T + self._process_noise(dt)
        self.cov = 0.5 * (self.cov + self.cov.T)

    # -- generic update -------------------------------------------------

    def _update(self, innovation: np.ndarray, h: np.ndarray, r: np.ndarray) -> float:
        """Joseph-form update. Returns the normalised innovation squared."""
        s = h @ self.cov @ h.T + r
        try:
            s_inv = np.linalg.inv(s)
        except np.linalg.LinAlgError:  # pragma: no cover - degenerate
            return float("nan")
        nis = float(innovation @ s_inv @ innovation)

        k = self.cov @ h.T @ s_inv
        dx = k @ innovation
        self.state = self.state.inject(dx)

        # Joseph form: stays positive-definite under the repeated small updates
        # a 10 Hz filter applies over a three-minute outage, where the simple
        # (I - KH)P form does not.
        a = np.eye(DIM) - k @ h
        self.cov = a @ self.cov @ a.T + k @ r @ k.T
        self.cov = 0.5 * (self.cov + self.cov.T)
        self._constrain()
        return nis

    def _constrain(self) -> None:
        """Keep the lever arm physically possible.

        The lever arm is weakly observable and will wander into nonsense on a
        straight road. A phone sits inside the car, so bound it.
        """
        m = self.config.max_lever_m
        if np.any(np.abs(self.state.lever) > m):
            self.state = self.state.replace(
                lever=np.clip(self.state.lever, -m, m)
            )

    # -- measurements ---------------------------------------------------

    def _car_velocity_jacobian(self, omega: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """``(v_car, H)`` for the 3-vector car-frame velocity."""
        st = self.state
        body_v = st.rot.T @ st.vel + np.cross(omega, st.lever)
        v_car = st.rot_car.T @ body_v

        h = np.zeros((3, DIM))
        h[:, I_THETA] = st.rot_car.T @ skew(st.rot.T @ st.vel)
        h[:, I_V] = st.rot_car.T @ st.rot.T
        h[:, I_THETA_C] = skew(v_car)
        h[:, I_PC] = st.rot_car.T @ skew(omega)
        h[:, I_BG] = st.rot_car.T @ skew(st.lever)
        return v_car, h

    def update_nonholonomic(self, gyro: np.ndarray) -> None:
        """Lateral and vertical car-frame velocity are zero."""
        omega = gyro - self.state.bias_gyro
        v_car, h_full = self._car_velocity_jacobian(omega)
        rows = [0, 2]  # lateral, vertical
        h = h_full[rows]
        innovation = -v_car[rows]
        r = np.eye(2) * self.config.sigma_nhc**2
        self._update(innovation, h, r)

    def update_forward_speed(self, speed_ms: float, gyro: np.ndarray,
                             sigma: float | None = None) -> None:
        """Learned forward-speed pseudo-measurement on the car-frame +y axis."""
        omega = gyro - self.state.bias_gyro
        v_car, h_full = self._car_velocity_jacobian(omega)
        h = h_full[[1]]
        innovation = np.array([speed_ms - v_car[1]])
        r = np.array([[(sigma if sigma is not None else self.config.sigma_speed) ** 2]])
        self._update(innovation, h, r)
        self.diagnostics.speed_used += 1

    def update_flat_earth(self, sigma: float | None = None) -> None:
        """Constrain navigation-frame vertical velocity toward zero.

        A road vehicle climbs and descends slowly: even a 10% gradient at
        30 m/s is only 3 m/s vertical, and most driving is far flatter. Unlike
        the nonholonomic constraint this is expressed in the *navigation*
        frame, so it needs no knowledge of how the phone is oriented in the car
        and is available immediately, before any alignment has converged.

        It matters more than it looks. With GNSS fixes a median of 9 s apart
        there are ~90 free-integration steps between corrections, and any
        attitude error leaks gravity into the vertical channel where nothing
        else observes it. Left unconstrained that error feeds back into
        horizontal position through the attitude coupling.
        """
        h = np.zeros((1, DIM))
        h[0, I_V] = np.array([0.0, 0.0, 1.0])
        innovation = np.array([-self.state.vel[2]])
        r = np.array([[(sigma if sigma is not None else self.config.sigma_flat) ** 2]])
        self._update(innovation, h, r)

    def update_gps_velocity(self, vel_en: np.ndarray, sigma: float | None = None) -> None:
        """Horizontal velocity from GNSS speed and course.

        This is the measurement that makes the aided phase work. With fixes a
        median of 9 s apart, position alone leaves ~90 free-integration steps
        between corrections, over which an unobserved attitude error lets
        gravity leak into horizontal acceleration and velocity runs away --
        measured at 607 m/s before this update existed. A velocity observation
        constrains that directly, and because it couples to attitude through
        the same Jacobian path it also keeps the gravity projection honest.
        """
        h = np.zeros((2, DIM))
        h[:, I_V] = np.eye(3)[:2]
        innovation = np.asarray(vel_en, dtype=float)[:2] - self.state.vel[:2]
        r = np.eye(2) * (sigma if sigma is not None else self.config.sigma_gps_vel) ** 2
        self._update(innovation, h, r)

    def reanchor(self, pos_en: np.ndarray, vel_en: np.ndarray | None = None) -> None:
        """Hard reset of position (and optionally velocity) to a trusted fix.

        Used when the gate has locked out, and by the FSM fiducial re-anchor.
        Covariance is reopened so the filter can move again rather than staying
        confidently wrong.
        """
        pos = self.state.pos.copy()
        pos[:2] = np.asarray(pos_en, dtype=float)[:2]
        new = self.state.replace(pos=pos)
        if vel_en is not None:
            vel = new.vel.copy()
            vel[:2] = np.asarray(vel_en, dtype=float)[:2]
            new = new.replace(vel=vel)
        self.state = new
        c = self.config
        self.cov[I_P, I_P] = np.eye(3) * c.p0_pos**2
        self.cov[I_V, I_V] = np.eye(3) * c.p0_vel**2
        self.cov = 0.5 * (self.cov + self.cov.T)

    def update_gps_position(self, pos_en: np.ndarray, accuracy_m: float | None = None,
                            cn0_mean: float | None = None) -> bool:
        """Gated horizontal position update. Returns True if accepted.

        Two defences against the urban canyon, where the receiver reports a fix
        while lying by tens of metres:

        * **C/N0 de-weighting** -- inflate R as mean carrier-to-noise falls,
          because low C/N0 is the observable signature of NLOS reception.
        * **Chi-square innovation gate** -- reject a fix whose normalised
          innovation squared exceeds the configured tail. With 2 degrees of
          freedom at 99.7% that threshold is 11.62.
        """
        sigma = self.config.sigma_gps_pos
        if accuracy_m is not None and np.isfinite(accuracy_m):
            sigma = max(sigma, float(accuracy_m))
        if cn0_mean is not None and np.isfinite(cn0_mean):
            # 35 dB-Hz is healthy open sky; below that, trust degrades fast.
            sigma *= float(np.clip(1.0 + (35.0 - cn0_mean) / 10.0, 1.0, 6.0))

        h = np.zeros((2, DIM))
        h[:, I_P] = np.eye(3)[:2]
        innovation = np.asarray(pos_en, dtype=float)[:2] - self.state.pos[:2]
        r = np.eye(2) * sigma**2

        s = h @ self.cov @ h.T + r
        nis = float(innovation @ np.linalg.solve(s, innovation))
        self.diagnostics.nis_history.append(nis)

        threshold = chi2.ppf(self.config.gate_confidence, df=2)
        if nis > threshold:
            self.diagnostics.n_gps_rejected += 1
            self.diagnostics.consecutive_rejections += 1
            if (self.diagnostics.consecutive_rejections
                    >= self.config.max_consecutive_rejections):
                # Repeated rejection means the filter is wrong, not the fix.
                self.reanchor(pos_en)
                self.diagnostics.n_gate_overrides += 1
                self.diagnostics.consecutive_rejections = 0
            return False

        self._update(innovation, h, r)
        self.diagnostics.n_gps_accepted += 1
        self.diagnostics.consecutive_rejections = 0
        return True

    # -- reporting ------------------------------------------------------

    @property
    def position_covariance(self) -> np.ndarray:
        return self.cov[I_P, I_P][:2, :2]


def _renorm(rot: np.ndarray) -> np.ndarray:
    u, _, vt = np.linalg.svd(rot)
    out = u @ vt
    if np.linalg.det(out) < 0:
        u[:, -1] *= -1.0
        out = u @ vt
    return out
