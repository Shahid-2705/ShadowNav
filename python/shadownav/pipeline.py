"""End-to-end ShadowNav pipeline: sequence in, trajectory out.

Wires the Phase 1 MVP components together (PLAN.md:153):

    gravity alignment -> error-state EKF -> nonholonomic constraint
        -> optional learned forward speed -> chi-square gated GNSS
        -> blackout FSM with fiducial re-anchor and blended re-acquisition

Runs at the sequence's native rate. Every step emits position, heading, speed,
mode and the 2x2 position covariance, so NEES and calibrated confidence can be
computed downstream without re-running anything.

PS scope is enforced here, not by convention: the only sensor columns read are
``acc_*`` and ``gyr_*`` plus GNSS. The dataset's ``grav_*``, ``mag_*`` and
``ori_*`` columns are fused outputs of the phone's own stack and reading them
would import a magnetometer into a system that claims not to have one
(PLAN.md:13).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from . import geo
from .baselines.naive import select_alignment_window
from .data.iovnbd import Sequence
from .filter.alignment import Alignment, estimate_alignment
from .filter.ekf import FilterConfig, NonholonomicEKF
from .filter.fsm import FsmConfig, GnssFsm, GnssMode, GnssObservation
from .filter.state import NavState, exp_so3


class SpeedEstimator(Protocol):
    """A learned forward-speed front end.

    Returns ``(speed_ms, sigma_ms)``. Returning a NaN speed means "no opinion
    at this step", which the filter treats as no measurement rather than as
    zero -- a network that silently reports 0 m/s during a tunnel would look
    superb on lateral error and be catastrophically wrong on position.
    """

    def __call__(self, window_acc: np.ndarray, window_gyr: np.ndarray) -> tuple[float, float]:
        ...


@dataclass(frozen=True)
class PipelineConfig:
    filter: FilterConfig = FilterConfig()
    fsm: FsmConfig = FsmConfig()
    #: IMU samples fed to the speed network. 64 at 10 Hz is 6.4 s, long enough
    #: to see a full acceleration event and short enough to stay causal.
    speed_window: int = 64
    align_rows: int = 50
    use_nonholonomic: bool = True
    #: Rows of aided driving used to estimate the device-to-car rotation.
    #: 600 at 10 Hz is a minute, long enough for gravity to dominate the mean
    #: specific force and for several acceleration events to appear.
    alignment_rows: int = 600
    #: Below this correlation quality the misalignment is not observable, so
    #: NHC is disabled rather than applied in a wrong frame. A straight,
    #: constant-speed approach is exactly this case (PLAN.md:191).
    min_alignment_quality: float = 0.35


@dataclass(frozen=True)
class Trajectory:
    """Per-sample estimator output."""

    time_s: np.ndarray
    east_m: np.ndarray
    north_m: np.ndarray
    speed_ms: np.ndarray
    heading_rad: np.ndarray
    mode: np.ndarray            # GnssMode values as strings
    cov_xy: np.ndarray          # (N, 2, 2)
    n_gps_accepted: int
    n_gps_rejected: int
    alignment_quality: float = 0.0
    nonholonomic_applied: bool = False

    def __len__(self) -> int:
        return len(self.time_s)


def _initial_state(acc_car: np.ndarray, gyr_car: np.ndarray, row: int,
                   heading_rad: float, speed_ms: float,
                   align_rows: int, up_b: np.ndarray | None = None) -> NavState:
    """Level on the quietest nearby window, then seed heading from GNSS.

    Inputs are already in the car frame, so body +y really is vehicle forward
    and the resulting rotation carries no misalignment.
    """
    if up_b is None:
        # Fall back to the quietest short window only when no long-window
        # vertical is supplied. Levelling on a 5 s window of a moving vehicle
        # reintroduces the 6 deg centripetal tilt documented in
        # baselines/naive.py, which is 206 m of error over 20 s.
        lo = max(0, row - align_rows)
        sl = select_alignment_window(acc_car, gyr_car, lo, row + 1)
        f = acc_car[sl].mean(axis=0)
        norm = float(np.linalg.norm(f))
        up_b = f / norm if norm > 1e-6 else np.array([0.0, 0.0, 1.0])
    up_b = np.asarray(up_b, dtype=float)
    up_b = up_b / max(float(np.linalg.norm(up_b)), 1e-9)

    fwd_b = np.array([0.0, 1.0, 0.0])
    if abs(float(fwd_b @ up_b)) > 0.99:
        fwd_b = np.array([1.0, 0.0, 0.0])
    fwd_b = fwd_b - (fwd_b @ up_b) * up_b
    fwd_b /= np.linalg.norm(fwd_b)
    east_b = np.cross(fwd_b, up_b)
    east_b /= np.linalg.norm(east_b)

    r_level = np.stack([east_b, fwd_b, up_b], axis=0)
    c, s = math.cos(heading_rad), math.sin(heading_rad)
    rot = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]]) @ r_level

    vel = np.array([speed_ms * math.sin(heading_rad),
                    speed_ms * math.cos(heading_rad), 0.0])
    return NavState.initial(rot, vel, np.zeros(3))


def _initial_heading(true_e: np.ndarray, true_n: np.ndarray,
                     course_deg: np.ndarray, row: int) -> float:
    """Course at ``row``, preferring the track over the receiver's own field.

    ``gps_orientation_deg`` is held between fixes for a median of 9 s, so on a
    turn it can be tens of degrees stale -- and a heading error at the start of
    a blackout integrates straight into cross-track error. The track between
    the two most recent distinct fixes is fresher.
    """
    track = geo.heading_from_track(true_e[: row + 1], true_n[: row + 1])
    if track.size and np.isfinite(track[-1]) and abs(track[-1]) > 0:
        return float(track[-1])
    if np.isfinite(course_deg[row]):
        return math.radians(float(course_deg[row]))
    return 0.0


def run(
    seq: Sequence,
    *,
    config: PipelineConfig | None = None,
    speed_estimator: SpeedEstimator | None = None,
    start_row: int = 0,
    end_row: int | None = None,
) -> Trajectory:
    """Run the estimator over ``seq`` between two rows."""
    cfg = config or PipelineConfig()
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

    # ENU referenced to the first row of the whole sequence, so estimator and
    # truth share one frame regardless of where the run starts.
    ref_lat = float(np.nanmin(lat)) if np.isfinite(lat).any() else 0.0
    ref_lon = float(np.nanmin(lon)) if np.isfinite(lon).any() else 0.0
    true_e, true_n = geo.lla_to_enu(lat, lon, ref_lat, ref_lon)

    # Estimate the device-to-car rotation on aided data before the run, then
    # work entirely in the car frame. Without this the nonholonomic constraint
    # is applied in the phone's frame, which is not the car's.
    # The mounting does not change during a drive, so use every aided sample
    # available before the run rather than a fixed lookback -- with GNSS fixes
    # 9 s apart, a 600-row window contains only a handful of usable
    # acceleration intervals, and the estimate silently falls back to identity.
    a_lo = max(0, start_row - cfg.alignment_rows)
    alignment = estimate_alignment(
        acc[: start_row + 1], gyr[: start_row + 1],
        speed_gps[: start_row + 1], t[: start_row + 1],
    )
    if alignment.quality < cfg.min_alignment_quality and start_row > a_lo:
        alignment = estimate_alignment(
            acc[a_lo : start_row + 1], gyr[a_lo : start_row + 1],
            speed_gps[a_lo : start_row + 1], t[a_lo : start_row + 1],
        )
    aligned = alignment.quality >= cfg.min_alignment_quality
    acc = alignment.apply(acc)
    gyr = alignment.apply(gyr)
    use_nhc = cfg.use_nonholonomic and aligned

    head0 = _initial_heading(true_e, true_n, course, start_row)
    speed0 = speed_gps[start_row]
    if not np.isfinite(speed0):
        speed0 = 0.0

    # Vertical from the long-run mean specific force: over a minute or more the
    # vehicle's own accelerations average toward zero and gravity dominates.
    lvl_lo = max(0, start_row - cfg.alignment_rows)
    long_mean = acc[lvl_lo : start_row + 1].mean(axis=0) if start_row > lvl_lo else None
    state = _initial_state(acc, gyr, start_row, float(head0),
                           float(speed0), cfg.align_rows, up_b=long_mean)
    state = state.replace(pos=np.array([true_e[start_row], true_n[start_row], 0.0]))
    ekf = NonholonomicEKF(state, cfg.filter)
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
            ekf.propagate(gyr[row - 1], acc[row - 1], dt)

        # Always available: needs no alignment, only that roads are near-level.
        ekf.update_flat_earth()
        if use_nhc:
            ekf.update_nonholonomic(gyr[row])

        if speed_estimator is not None and row >= cfg.speed_window:
            lo = row - cfg.speed_window + 1
            s_hat, sigma = speed_estimator(acc[lo : row + 1], gyr[lo : row + 1])
            if np.isfinite(s_hat):
                ekf.update_forward_speed(float(s_hat), gyr[row], float(sigma))

        obs = GnssObservation(
            available=bool(available[row]) and np.isfinite(lat[row]),
            n_sats_used=int(sats[row]) if np.isfinite(sats[row]) else 0,
            cn0_mean=float("nan"),   # S-side carries no C/N0; Android will
            accuracy_m=float(accuracy[row]) if np.isfinite(accuracy[row]) else float("nan"),
        )
        mode = fsm.update(float(t[row]), obs, dt)

        just_reacquired = (
            prev_mode is GnssMode.DEAD_RECKONING and mode is GnssMode.REACQUIRING
        )
        if just_reacquired and obs.available:
            fsm.begin_reacquisition(ekf.state.pos[:2],
                                    np.array([true_e[row], true_n[row]]))

        if mode in (GnssMode.AIDED, GnssMode.DEGRADED) and obs.available and is_new_fix[row]:
            accepted = ekf.update_gps_position(
                np.array([true_e[row], true_n[row]]),
                accuracy_m=obs.accuracy_m,
                cn0_mean=obs.cn0_mean,
            )
            # Velocity from GNSS speed and course. Doppler speed is accurate,
            # and this is what stops the aided phase diverging across the 9 s
            # gaps between position fixes.
            if np.isfinite(speed_gps[row]):
                crs = course[row]
                psi = (math.radians(float(crs)) if np.isfinite(crs)
                       else _initial_heading(true_e, true_n, course, row))
                ekf.update_gps_velocity(
                    np.array([speed_gps[row] * math.sin(psi),
                              speed_gps[row] * math.cos(psi)]))
            if accepted:
                fsm.note_good_fix(float(t[row]), ekf.state.pos[:2])

        pos = ekf.state.pos[:2].copy()
        if mode is GnssMode.REACQUIRING:
            # Subtract the residual displacement still being absorbed, so the
            # reported track is continuous while the filter converges.
            pos = pos - (fsm.blend.error - fsm.blend.step(dt))

        out_e[i] = pos[0]
        out_n[i] = pos[1]
        out_v[i] = ekf.state.speed_ms
        out_h[i] = ekf.state.heading_rad
        out_mode[i] = mode.value
        out_cov[i] = ekf.position_covariance
        prev_mode = mode

    return Trajectory(
        time_s=t[start_row : end_row + 1].copy(),
        east_m=out_e, north_m=out_n, speed_ms=out_v, heading_rad=out_h,
        mode=out_mode, cov_xy=out_cov,
        n_gps_accepted=ekf.diagnostics.n_gps_accepted,
        n_gps_rejected=ekf.diagnostics.n_gps_rejected,
        alignment_quality=alignment.quality,
        nonholonomic_applied=use_nhc,
    )


def enu_reference(seq: Sequence) -> tuple[float, float]:
    """The ENU origin :func:`run` uses, so callers can match frames."""
    lat = seq.df["gps_lat_deg"].to_numpy(dtype=float)
    lon = seq.df["gps_lon_deg"].to_numpy(dtype=float)
    ref_lat = float(np.nanmin(lat)) if np.isfinite(lat).any() else 0.0
    ref_lon = float(np.nanmin(lon)) if np.isfinite(lon).any() else 0.0
    return ref_lat, ref_lon
