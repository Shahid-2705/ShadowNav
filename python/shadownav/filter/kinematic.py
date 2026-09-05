"""2D kinematic vehicle dead-reckoning filter.

Why this exists alongside the 21-state strapdown EKF
----------------------------------------------------
``filter/ekf.py`` is a correct strapdown INS -- its Jacobians are verified
against finite differences -- and it is the right architecture for the 100-200 Hz
IMU a phone actually provides. It is the wrong architecture for the data we can
*train and validate on*, and that was established by measurement, not taste:

* IO-VNBD's smartphone side logs at **10 Hz**. Road and engine vibration lives
  well above 5 Hz, so the accelerometer is aliased, not merely coarse.
* GNSS fixes arrive a median of **9 s** apart, leaving ~90 free-integration
  steps between corrections.
* Double integration turns any attitude error into position error as
  ``0.5 * g * sin(tilt) * t^2``. At 9 s a 2 deg tilt is 14 m; a 20 deg tilt is
  140 m. Running the strapdown filter on this data produced velocities of
  5 x 10^4 m/s.

So this filter never double-integrates acceleration. It integrates **heading
from the gyroscope** and **holds speed**, which is the classical vehicle dead-
reckoning model:

    psi_dot = -(omega_z - b_omega)        gyro is reliable over minutes
    v_dot   = a_forward                   only when alignment is available
    e_dot   = v sin(psi)
    n_dot   = v cos(psi)

Holding speed through a blackout is not a weakness here -- it is close to
correct. Tunnel and underpass driving is near constant speed, which is exactly
why GNIO names constant-speed cruising as the case with no learnable signal. The
learned front end's job is to correct that assumption, not to replace it.

This also matches what the mature competitors converged on independently
(dossier section 10): physics baseline plus learned residual, a complementary
filter, or gated correction -- none of them a full strapdown INS on phone data.

Sign convention
---------------
ENU is right-handed about up, and ``psi`` is clockwise from north, so a positive
gyro z (counter-clockwise seen from above) *decreases* psi. Hence the minus
sign. This is the same convention as ``geo.heading_from_track`` and is checked
by a round-trip test.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import chi2

DIM = 5
I_E, I_N, I_PSI, I_V, I_BW = 0, 1, 2, 3, 4


def wrap(a: float) -> float:
    """Wrap radians to (-pi, pi]."""
    return float((a + np.pi) % (2.0 * np.pi) - np.pi)


@dataclass(frozen=True)
class KinematicConfig:
    # Process noise, per sqrt(second).
    sigma_gyro: float = 3.0e-3          # rad/s
    sigma_accel: float = 0.35           # m/s^2 driving the speed random walk
    sigma_bias_gyro: float = 2.0e-5     # rad/s^2
    sigma_pos: float = 0.05             # m/s, slack on the position integration

    # Measurements.
    sigma_gps_pos: float = 4.0          # m
    sigma_gps_speed: float = 0.5        # m/s
    sigma_gps_course: float = 0.09      # rad, ~5 deg
    sigma_learned_speed: float = 1.0    # m/s
    sigma_centripetal: float = 0.6      # m/s^2
    sigma_ackermann: float = 1.5        # m/s, soft bound on speed

    # Initial uncertainty.
    p0_pos: float = 5.0
    p0_psi: float = 0.15
    p0_speed: float = 1.5
    p0_bias_gyro: float = 0.01

    #: Ackermann bounds (PLAN.md:104). Both are parameter-free in the sense
    #: that neither needs a wheelbase, which a smartphone cannot know.
    #:   kappa_max  tightest curvature any road vehicle can achieve;
    #:              0.28 /m is a 3.6 m turning radius, which covers cars
    #:   mu         tyre-road friction coefficient; 0.8 is dry asphalt
    curvature_max: float = 0.28
    friction_mu: float = 0.8
    #: Above this lateral acceleration the bicycle model breaks down as the
    #: tyres begin to slip, so the bounds are switched off rather than
    #: enforced outside their domain of validity (PLAN.md:108).
    ackermann_max_lateral_g: float = 0.5

    gate_confidence: float = 0.997
    max_consecutive_rejections: int = 3
    #: Below this speed the course measurement is meaningless -- a stationary
    #: receiver reports an essentially random course.
    min_speed_for_course: float = 2.0


@dataclass
class KinematicDiagnostics:
    n_gps_accepted: int = 0
    n_gps_rejected: int = 0
    n_gate_overrides: int = 0
    consecutive_rejections: int = 0
    n_centripetal: int = 0
    n_ackermann: int = 0
    nis_history: list[float] = field(default_factory=list)


class KinematicEKF:
    """Five-state vehicle DR filter: east, north, heading, speed, gyro bias."""

    def __init__(self, east: float, north: float, heading_rad: float,
                 speed_ms: float, config: KinematicConfig | None = None) -> None:
        self.config = config or KinematicConfig()
        c = self.config
        self.x = np.array([east, north, wrap(heading_rad), speed_ms, 0.0])
        self.cov = np.diag([
            c.p0_pos**2, c.p0_pos**2, c.p0_psi**2, c.p0_speed**2, c.p0_bias_gyro**2
        ])
        self.diagnostics = KinematicDiagnostics()

    # -- accessors ------------------------------------------------------

    @property
    def position(self) -> np.ndarray:
        return self.x[:2].copy()

    @property
    def heading_rad(self) -> float:
        return float(self.x[I_PSI])

    @property
    def speed_ms(self) -> float:
        return float(self.x[I_V])

    @property
    def position_covariance(self) -> np.ndarray:
        return self.cov[:2, :2].copy()

    # -- propagation ----------------------------------------------------

    def propagate(self, gyro_z: float, accel_forward: float | None, dt: float) -> None:
        """Advance one step. ``accel_forward`` is None when unaligned."""
        if dt <= 0:
            return
        c = self.config
        psi = float(self.x[I_PSI])
        v = float(self.x[I_V])
        rate = -(gyro_z - self.x[I_BW])

        f = np.eye(DIM)
        f[I_E, I_PSI] = v * np.cos(psi) * dt
        f[I_E, I_V] = np.sin(psi) * dt
        f[I_N, I_PSI] = -v * np.sin(psi) * dt
        f[I_N, I_V] = np.cos(psi) * dt
        f[I_PSI, I_BW] = dt

        self.x[I_E] += v * np.sin(psi) * dt
        self.x[I_N] += v * np.cos(psi) * dt
        self.x[I_PSI] = wrap(psi + rate * dt)
        if accel_forward is not None and np.isfinite(accel_forward):
            self.x[I_V] = max(0.0, v + float(accel_forward) * dt)

        q = np.diag([
            c.sigma_pos**2 * dt,
            c.sigma_pos**2 * dt,
            c.sigma_gyro**2 * dt,
            c.sigma_accel**2 * dt,
            c.sigma_bias_gyro**2 * dt,
        ])
        self.cov = f @ self.cov @ f.T + q
        self.cov = 0.5 * (self.cov + self.cov.T)

    # -- updates --------------------------------------------------------

    def _update(self, innovation: np.ndarray, h: np.ndarray, r: np.ndarray) -> float:
        s = h @ self.cov @ h.T + r
        try:
            s_inv = np.linalg.inv(s)
        except np.linalg.LinAlgError:  # pragma: no cover
            return float("nan")
        nis = float(innovation @ s_inv @ innovation)
        k = self.cov @ h.T @ s_inv
        self.x = self.x + k @ innovation
        self.x[I_PSI] = wrap(float(self.x[I_PSI]))
        self.x[I_V] = max(0.0, float(self.x[I_V]))
        a = np.eye(DIM) - k @ h
        self.cov = a @ self.cov @ a.T + k @ r @ k.T
        self.cov = 0.5 * (self.cov + self.cov.T)
        return nis

    def update_speed(self, speed_ms: float, sigma: float | None = None) -> None:
        h = np.zeros((1, DIM))
        h[0, I_V] = 1.0
        r = np.array([[(sigma if sigma is not None else self.config.sigma_gps_speed) ** 2]])
        self._update(np.array([speed_ms - self.x[I_V]]), h, r)

    def update_course(self, course_rad: float, sigma: float | None = None) -> None:
        """Heading from GNSS course over ground. Ignored at low speed."""
        if self.x[I_V] < self.config.min_speed_for_course:
            return
        h = np.zeros((1, DIM))
        h[0, I_PSI] = 1.0
        r = np.array([[(sigma if sigma is not None else self.config.sigma_gps_course) ** 2]])
        self._update(np.array([wrap(course_rad - float(self.x[I_PSI]))]), h, r)

    def update_centripetal(self, accel_lateral: float, gyro_z: float,
                           sigma: float | None = None) -> None:
        """The ``L_cent`` observation, as a measurement rather than a loss.

        Measured lateral specific force equals ``v * psi_dot``, and
        ``psi_dot = -(omega_z - b_omega)``, so

            a_lat = -v * (omega_z - b_omega)

        Every turn therefore becomes an independent observation of speed that
        does not involve integrating accelerometer noise -- PLAN.md:94, and the
        highest value-per-line item in the plan. No wheelbase appears.

        It is skipped in near-straight driving, where the Jacobian with respect
        to speed vanishes and the update is pure noise.
        """
        rate = gyro_z - float(self.x[I_BW])
        if abs(rate) < 0.02:  # below ~1.1 deg/s speed is not observable here
            return
        v = float(self.x[I_V])
        h = np.zeros((1, DIM))
        h[0, I_V] = -rate
        h[0, I_BW] = v
        r = np.array([[(sigma if sigma is not None else self.config.sigma_centripetal) ** 2]])
        self._update(np.array([accel_lateral - (-v * rate)]), h, r)
        self.diagnostics.n_centripetal += 1

    def update_ackermann(self, gyro_z: float, sigma: float | None = None) -> bool:
        """Bound speed by what a road vehicle can physically do while turning.

        Two inequalities, from PLAN.md:104, neither of which needs a wheelbase:

          curvature   |omega| <= v * kappa_max   ->   v >= |omega| / kappa_max
          friction    |v * omega| <= mu * g      ->   v <= mu * g / |omega|

        The first says a vehicle turning quickly cannot be crawling: a yaw rate
        of 0.5 rad/s is impossible below about 1.8 m/s, because no car turns
        inside a 3.6 m radius. The second says it cannot be flying: the same
        yaw rate at 20 m/s would need 10 m/s^2 of lateral grip, past what dry
        asphalt provides.

        Enforced as a soft one-sided pseudo-measurement only when violated, so
        the bounds cost nothing in normal driving and cannot bias the estimate
        inward from the middle of the feasible band.

        Returns True if a bound was applied.
        """
        rate = abs(gyro_z - float(self.x[I_BW]))
        if rate < 0.05:               # nearly straight: bounds are vacuous
            return False
        v = float(self.x[I_V])
        c = self.config
        lateral = abs(v * rate)

        # The two bounds are gated differently, and conflating them makes one
        # of them dead code.
        #
        # PLAN.md:108 says to gate Ackermann terms off above ~0.5 g lateral,
        # where tyre slip breaks the bicycle model. That is correct for the
        # *curvature* bound, which is a steering-geometry statement.
        #
        # It is circular for the *friction* bound. That bound says lateral
        # acceleration cannot exceed mu*g = 7.85 m/s^2; the slip gate rejects
        # anything above 0.5 g = 4.9 m/s^2. Every violation of the friction
        # bound is therefore already gated out, so applying the same gate to it
        # means it can never fire -- gating a slip limit by a slip test. The
        # friction bound is the physics that *defines* the slip limit, so it is
        # applied unconditionally.
        target = None
        upper = c.friction_mu * 9.80665 / rate
        if v > upper:
            target = upper
        elif lateral <= c.ackermann_max_lateral_g * 9.80665:
            lower = rate / c.curvature_max
            if lower <= upper and v < lower:
                target = lower

        if target is None:
            return False

        h = np.zeros((1, DIM))
        h[0, I_V] = 1.0
        r = np.array([[(sigma if sigma is not None else c.sigma_ackermann) ** 2]])
        self._update(np.array([target - v]), h, r)
        self.diagnostics.n_ackermann += 1
        return True

    def update_position(self, pos_en: np.ndarray, sigma: float | None = None,
                        cn0_mean: float | None = None) -> bool:
        """Chi-square gated position update with C/N0 de-weighting."""
        s_pos = sigma if sigma is not None else self.config.sigma_gps_pos
        s_pos = max(s_pos, self.config.sigma_gps_pos)
        if cn0_mean is not None and np.isfinite(cn0_mean):
            s_pos *= float(np.clip(1.0 + (35.0 - cn0_mean) / 10.0, 1.0, 6.0))

        h = np.zeros((2, DIM))
        h[0, I_E] = 1.0
        h[1, I_N] = 1.0
        innovation = np.asarray(pos_en, dtype=float)[:2] - self.x[:2]
        r = np.eye(2) * s_pos**2

        s = h @ self.cov @ h.T + r
        nis = float(innovation @ np.linalg.solve(s, innovation))
        self.diagnostics.nis_history.append(nis)

        if nis > chi2.ppf(self.config.gate_confidence, df=2):
            self.diagnostics.n_gps_rejected += 1
            self.diagnostics.consecutive_rejections += 1
            if (self.diagnostics.consecutive_rejections
                    >= self.config.max_consecutive_rejections):
                # Persistent rejection means the filter is wrong, not the fix.
                # Without this escape a diverged filter rejects every fix
                # forever; a competitor shipped exactly that bug and their
                # engine sat in DR mode for 2h13m (dossier section 10).
                self.reanchor(pos_en)
                self.diagnostics.n_gate_overrides += 1
                self.diagnostics.consecutive_rejections = 0
            return False

        self._update(innovation, h, r)
        self.diagnostics.n_gps_accepted += 1
        self.diagnostics.consecutive_rejections = 0
        return True

    def reanchor(self, pos_en: np.ndarray) -> None:
        self.x[:2] = np.asarray(pos_en, dtype=float)[:2]
        c = self.config
        self.cov[:2, :2] = np.eye(2) * c.p0_pos**2
