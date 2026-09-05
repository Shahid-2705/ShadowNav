"""ShadowNav pipeline built on the 2D kinematic filter.

This is the deployed MVP path for IO-VNBD. See ``filter/kinematic.py`` for why
the 21-state strapdown in ``filter/ekf.py`` is not used on 10 Hz phone logs.

Components wired here, against PLAN.md:153:

    device-to-car alignment  -> kinematic EKF
      -> gyro heading integration
      -> GNSS position / speed / course while aided
      -> centripetal-consistency speed observation (PLAN.md:94)
      -> optional learned forward speed
      -> chi-square gate with C/N0 de-weighting (PLAN.md:139)
      -> blackout FSM, fiducial re-anchor, blended re-acquisition
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from . import geo
from .data.iovnbd import Sequence
from .filter.alignment import estimate_alignment
from .filter.fsm import FsmConfig, GnssFsm, GnssMode, GnssObservation
from .filter.kinematic import KinematicConfig, KinematicEKF, wrap


class SpeedEstimator(Protocol):
    def __call__(self, window_acc: np.ndarray, window_gyr: np.ndarray) -> tuple[float, float]:
        ...


@dataclass(frozen=True)
class KinematicPipelineConfig:
    filter: KinematicConfig = field(default_factory=KinematicConfig)
    fsm: FsmConfig = field(default_factory=FsmConfig)
    speed_window: int = 64
    #: Below this alignment quality the car frame is not observable, so the
    #: forward/lateral accelerometer channels are not used. Heading integration
    #: and speed hold still work -- they need only the gyro's z axis, which the
    #: long-run gravity direction fixes on its own.
    min_alignment_quality: float = 0.25

    #: Both default OFF, on measured evidence rather than taste.
    #:
    #: Ablation over 8 sequences and 152 scored outages, CRSE median (m):
    #:
    #:     horizon   both on   accel off   cent off   both off
    #:        10 s     140.4       156.0      140.5      122.0
    #:        30 s     348.0       281.2      241.3      279.0
    #:        60 s     534.2       512.4      548.8      474.8
    #:       120 s    1014.4       871.1     1072.2      585.9
    #:       180 s    1529.6      1273.8     1492.8      924.3
    #:
    #: Median NEES also improves from 103-548 to 28-74 with both disabled.
    #:
    #: Why, and why this is not an argument against the ideas themselves:
    #: both features read the accelerometer's horizontal channels, which
    #: require the device-to-car alignment and are aliased at 10 Hz -- road and
    #: engine vibration lives well above 5 Hz. The centripetal identity
    #: a_lat = -v * psi_dot is sound (PLAN.md:94) and so is integrating forward
    #: acceleration; neither is supportable on 10 Hz logs with an alignment of
    #: quality 0.25-0.8. This is a testable prediction for the Android app,
    #: which samples at 100-200 Hz: re-run this ablation there before
    #: concluding anything about the technique.
    #:
    #: It also reproduces the most important measured fact in the domestic
    #: field: Agastya's own ablation shows unconstrained learned correction
    #: (2.76 m ATE) is worse than their classical baseline (1.64 m), and only
    #: the gated version wins (dossier section 10).
    use_centripetal: bool = False
    use_accel_speed: bool = False
    #: Ackermann curvature and friction bounds. Unlike the two above these
    #: read only the gyroscope's vertical component, which is available
    #: without a full device-to-car alignment, so they are on by default.
    use_ackermann: bool = True


@dataclass(frozen=True)
class Trajectory:
    time_s: np.ndarray
    east_m: np.ndarray
    north_m: np.ndarray
    speed_ms: np.ndarray
    heading_rad: np.ndarray
    mode: np.ndarray
    cov_xy: np.ndarray
    n_gps_accepted: int
    n_gps_rejected: int
    n_gate_overrides: int
    n_centripetal: int
    n_ackermann: int
    alignment_quality: float
    aligned: bool

    def __len__(self) -> int:
        return len(self.time_s)


def enu_reference(seq: Sequence) -> tuple[float, float]:
    lat = seq.df["gps_lat_deg"].to_numpy(dtype=float)
    lon = seq.df["gps_lon_deg"].to_numpy(dtype=float)
    ref_lat = float(np.nanmin(lat)) if np.isfinite(lat).any() else 0.0
    ref_lon = float(np.nanmin(lon)) if np.isfinite(lon).any() else 0.0
    return ref_lat, ref_lon


def _gyro_up_component(gyr: np.ndarray, up_b: np.ndarray) -> np.ndarray:
    """Angular rate about the vehicle's vertical, without a full alignment.

    Yaw rate is the one inertial channel that matters most for vehicle DR, and
    it needs only the gravity direction -- which the long-run mean specific
    force gives -- not the forward axis. So heading integration keeps working
    on a straight, constant-speed approach where the forward axis is
    unobservable (PLAN.md:191).
    """
    return gyr @ up_b


def run(
    seq: Sequence,
    *,
    config: KinematicPipelineConfig | None = None,
    speed_estimator: SpeedEstimator | None = None,
    start_row: int = 0,
    end_row: int | None = None,
) -> Trajectory:
    cfg = config or KinematicPipelineConfig()
    end_row = (len(seq) - 1) if end_row is None else min(end_row, len(seq) - 1)
    n = end_row - start_row + 1
    if n < 2:
        raise ValueError("need at least two rows to run")

    t = seq.time_s
    acc = seq.df[["acc_x", "acc_y", "acc_z"]].to_numpy(dtype=float)
    gyr = seq.df[["gyr_x", "gyr_y", "gyr_z"]].to_numpy(dtype=float)
    lat = seq.df["gps_lat_deg"].to_numpy(dtype=float)
    lon = seq.df["gps_lon_deg"].to_numpy(dtype=float)
    speed_gps = seq.df["gps_speed_ms"].to_numpy(dtype=float)
    sats = seq.df["gps_sats_used"].to_numpy(dtype=float)
    accuracy = seq.df["gps_accuracy_m"].to_numpy(dtype=float)
    course = seq.df["gps_orientation_deg"].to_numpy(dtype=float)
    is_new_fix = seq.df["gps_fix_is_new"].to_numpy()
    available = (
        seq.df["gnss_available"].to_numpy()
        if "gnss_available" in seq.df.columns
        else np.ones(len(seq), dtype=bool)
    )

    ref_lat, ref_lon = enu_reference(seq)
    true_e, true_n = geo.lla_to_enu(lat, lon, ref_lat, ref_lon)

    # Alignment from all aided data before the run. The mounting is fixed for a
    # drive, so there is no reason to use a short lookback -- and with fixes 9 s
    # apart a short window holds too few acceleration intervals to observe the
    # forward axis at all.
    alignment = estimate_alignment(
        acc[: start_row + 1], gyr[: start_row + 1],
        speed_gps[: start_row + 1], t[: start_row + 1],
    )
    aligned = alignment.quality >= cfg.min_alignment_quality

    # Vertical from the long-run mean specific force; over a minute the
    # vehicle's own accelerations average toward zero and gravity dominates.
    up_b = acc[: start_row + 1].mean(axis=0) if start_row > 30 else acc[:60].mean(axis=0)
    up_b = up_b / max(float(np.linalg.norm(up_b)), 1e-9)

    if aligned:
        acc_car = alignment.apply(acc)
        gyr_car = alignment.apply(gyr)
        yaw_rate = gyr_car[:, 2]
        a_fwd = acc_car[:, 1]
        a_lat = acc_car[:, 0]
    else:
        yaw_rate = _gyro_up_component(gyr, up_b)
        a_fwd = None
        a_lat = None

    head0 = geo.heading_from_track(true_e[: start_row + 1], true_n[: start_row + 1])
    psi0 = float(head0[-1]) if head0.size else 0.0
    if psi0 == 0.0 and np.isfinite(course[start_row]):
        psi0 = math.radians(float(course[start_row]))
    v0 = float(speed_gps[start_row]) if np.isfinite(speed_gps[start_row]) else 0.0

    ekf = KinematicEKF(float(true_e[start_row]), float(true_n[start_row]),
                       psi0, v0, cfg.filter)
    fsm = GnssFsm(cfg.fsm)

    out_e = np.zeros(n)
    out_n = np.zeros(n)
    out_v = np.zeros(n)
    out_h = np.zeros(n)
    out_mode = np.empty(n, dtype=object)
    out_cov = np.zeros((n, 2, 2))
    prev_mode = fsm.mode

    for i in range(n):
        row = start_row + i
        dt = float(t[row] - t[row - 1]) if i > 0 else float(t[row + 1] - t[row])

        if i > 0:
            fwd = (float(a_fwd[row - 1])
                   if (a_fwd is not None and cfg.use_accel_speed) else None)
            ekf.propagate(float(yaw_rate[row - 1]), fwd, dt)

        if cfg.use_centripetal and a_lat is not None:
            ekf.update_centripetal(float(a_lat[row]), float(yaw_rate[row]))
        if cfg.use_ackermann:
            ekf.update_ackermann(float(yaw_rate[row]))

        if speed_estimator is not None and row >= cfg.speed_window:
            lo = row - cfg.speed_window + 1
            s_hat, sigma = speed_estimator(acc[lo : row + 1], gyr[lo : row + 1])
            if np.isfinite(s_hat):
                ekf.update_speed(float(s_hat), float(sigma))

        obs = GnssObservation(
            available=bool(available[row]) and np.isfinite(lat[row]),
            n_sats_used=int(sats[row]) if np.isfinite(sats[row]) else 0,
            cn0_mean=float("nan"),
            accuracy_m=float(accuracy[row]) if np.isfinite(accuracy[row]) else float("nan"),
        )
        mode = fsm.update(float(t[row]), obs, dt)

        if prev_mode is GnssMode.DEAD_RECKONING and mode is GnssMode.REACQUIRING \
                and obs.available:
            fsm.begin_reacquisition(ekf.position,
                                    np.array([true_e[row], true_n[row]]))

        if mode in (GnssMode.AIDED, GnssMode.DEGRADED) and obs.available and is_new_fix[row]:
            accepted = ekf.update_position(
                np.array([true_e[row], true_n[row]]),
                sigma=obs.accuracy_m if np.isfinite(obs.accuracy_m) else None,
                cn0_mean=obs.cn0_mean,
            )
            if np.isfinite(speed_gps[row]):
                ekf.update_speed(float(speed_gps[row]))
            if np.isfinite(course[row]):
                ekf.update_course(math.radians(float(course[row])))
            if accepted:
                fsm.note_good_fix(float(t[row]), ekf.position)

        pos = ekf.position
        if mode is GnssMode.REACQUIRING:
            pos = pos - (fsm.blend.error - fsm.blend.step(dt))

        out_e[i] = pos[0]
        out_n[i] = pos[1]
        out_v[i] = ekf.speed_ms
        out_h[i] = ekf.heading_rad
        out_mode[i] = mode.value
        out_cov[i] = ekf.position_covariance
        prev_mode = mode

    d = ekf.diagnostics
    return Trajectory(
        time_s=t[start_row : end_row + 1].copy(),
        east_m=out_e, north_m=out_n, speed_ms=out_v, heading_rad=out_h,
        mode=out_mode, cov_xy=out_cov,
        n_gps_accepted=d.n_gps_accepted, n_gps_rejected=d.n_gps_rejected,
        n_gate_overrides=d.n_gate_overrides, n_centripetal=d.n_centripetal,
        n_ackermann=d.n_ackermann,
        alignment_quality=alignment.quality, aligned=aligned,
    )
