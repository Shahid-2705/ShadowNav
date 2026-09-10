"""Error metrics for GNSS-outage dead reckoning.

Definitions follow WhONet's naming so the shape of the numbers is comparable,
but they are *our* definitions and are stated explicitly here, because the
WhONet benchmark itself cannot be reproduced smartphone-only (PLAN.md:151) and
its published figures use wheel-speed sensors.

  CRSE  cumulative resultant system error -- Euclidean position error at the
        moment of evaluation, in metres
  CTE   cross-track error -- the component of that error perpendicular to the
        ground-truth course, in metres
  ATE   RMS of the resultant error over the whole outage, in metres
  drift CRSE as a percentage of ground distance travelled during the outage;
        this is the AVNet convention and the only one directly comparable to
        its 0.64% over a 578 m tunnel

The truth-interpolation problem
-------------------------------
Ground truth comes from GPS, which the audit measured at a median period of
9.0 s -- roughly 27 m of travel between consecutive fixes. Interpolating truth
to 10 Hz and scoring against it would report interpolation error as if it were
estimator error, and on a curve that is metres.

So the primary metric is evaluated **only at instants where a real GPS fix
exists**. :func:`evaluate_window` reports the actual evaluation time, which may
exceed the requested horizon by up to one fix period, and reports the truth gap
so the reader can judge how much of the number is interpolation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .. import geo


@dataclass(frozen=True)
class OutageResult:
    """Metrics for one estimator over one outage window."""

    sequence: str
    method: str
    horizon_s: float
    t_eval_s: float
    distance_m: float          # truth path length over the scored span
    crse_m: float
    cte_m: float
    ate_m: float
    drift_pct: float
    n_fixes_suppressed: int
    truth_gap_m: float
    nees: float | None = None
    # Transition metrics (see :func:`transition_metrics`); None for methods
    # that have no mode machine, e.g. the comparators.
    detection_latency_s: float | None = None
    reacq_snap_m: float | None = None
    reacq_max_step_m: float | None = None
    reacq_settle_s: float | None = None
    reacq_residual_m: float | None = None
    # The 90% ring the app would draw at the evaluation instant, in metres,
    # from the raw filter covariance and after conformal inflation.
    radius90_raw_m: float | None = None
    radius90_cal_m: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TransitionMetrics:
    """What the PS grades as "seamless": entering and leaving dead reckoning.

    detection_latency_s  mask start -> first sample in DEAD_RECKONING
    reacq_snap_m         displacement between the estimate and truth at the
                         first real fix after the mask -- the error a naive
                         re-anchor would jump by
    reacq_max_step_m     the largest single-sample movement of the displayed
                         position, in excess of the vehicle's own motion,
                         within ``window_s`` of that fix. A snap shows up here
                         as a step of about ``reacq_snap_m``; a blend shows up
                         as a small number
    reacq_settle_s       time from that fix until the mode machine is back in
                         an aided state
    reacq_residual_m     error against truth at the next real fix after the
                         one that ended the outage -- whether the display has
                         actually converged onto the fix track
    """

    detection_latency_s: float
    reacq_snap_m: float
    reacq_max_step_m: float
    reacq_settle_s: float
    reacq_residual_m: float

    def as_dict(self) -> dict:
        return asdict(self)


def resultant_error(
    est_e: np.ndarray, est_n: np.ndarray, true_e: np.ndarray, true_n: np.ndarray
) -> np.ndarray:
    """Euclidean position error per sample, in metres."""
    return np.hypot(est_e - true_e, est_n - true_n)


def cross_track_error(
    est_e: float, est_n: float, true_e: float, true_n: float, course_rad: float
) -> float:
    """Signed-magnitude error perpendicular to the ground-truth course.

    Course is measured clockwise from north, so the unit along-track vector is
    ``(sin, cos)`` in (east, north) and the perpendicular is ``(cos, -sin)``.
    """
    de = est_e - true_e
    dn = est_n - true_n
    return float(abs(de * np.cos(course_rad) - dn * np.sin(course_rad)))


def nees(error_xy: np.ndarray, cov_xy: np.ndarray) -> float:
    """Normalised estimation error squared, averaged over samples.

    For a 2D position estimate a consistent filter averages 2.0. Above that the
    filter is overconfident, which the literature reports as the normal state of
    affairs in dead reckoning (PLAN.md:140) -- so this is reported, never tuned
    away.
    """
    out = []
    for e, p in zip(np.atleast_2d(error_xy), np.atleast_3d(cov_xy.T).T):
        try:
            out.append(float(e @ np.linalg.solve(p, e)))
        except np.linalg.LinAlgError:  # pragma: no cover - singular covariance
            continue
    return float(np.mean(out)) if out else float("nan")


def truth_fix_rows(seq_df, start_row: int, end_row: int) -> np.ndarray:
    """Row indices at or after ``start_row`` where a real GPS fix lands."""
    is_new = seq_df["gps_fix_is_new"].to_numpy()
    rows = np.flatnonzero(is_new)
    return rows[(rows >= start_row) & (rows <= end_row)]


def evaluation_row(
    time_s: np.ndarray, fix_rows: np.ndarray, start_row: int, horizon_s: float
) -> int | None:
    """The first real fix at or after ``start_row + horizon_s``, or None."""
    target_t = time_s[start_row] + horizon_s
    later = fix_rows[time_s[fix_rows] >= target_t]
    return int(later[0]) if later.size else None


def evaluate_window(
    *,
    sequence: str,
    method: str,
    horizon_s: float,
    time_s: np.ndarray,
    est_e: np.ndarray,
    est_n: np.ndarray,
    true_e: np.ndarray,
    true_n: np.ndarray,
    fix_rows: np.ndarray,
    start_row: int,
    distance_m: float,
    n_fixes_suppressed: int,
    cov_xy: np.ndarray | None = None,
) -> OutageResult | None:
    """Score one outage at the first real GPS fix at or after the horizon.

    Returns ``None`` when no real fix exists at or after the horizon, which is a
    genuine outcome given the 9 s fix period rather than an error: it means the
    dataset simply cannot answer the question at that horizon on that sequence.
    """
    eval_row = evaluation_row(time_s, fix_rows, start_row, horizon_s)
    if eval_row is None:
        return None

    err = resultant_error(est_e, est_n, true_e, true_n)
    crse = float(err[eval_row])

    course = geo.heading_from_track(true_e, true_n)
    cte = cross_track_error(
        float(est_e[eval_row]), float(est_n[eval_row]),
        float(true_e[eval_row]), float(true_n[eval_row]),
        float(course[eval_row]),
    )

    span = slice(start_row, eval_row + 1)
    ate = float(np.sqrt(np.mean(err[span] ** 2)))

    # Distance must be measured over the span actually scored, not over the
    # requested window. Because the next real fix can be up to one 9 s fix
    # period past the horizon, those two spans differ by up to 50% and dividing
    # the error at t_eval by the distance over the horizon overstates drift.
    # Measured along the truth path through the real fixes, which is the AVNet
    # "% of distance travelled" convention.
    scored_fixes = fix_rows[(fix_rows >= start_row) & (fix_rows <= eval_row)]
    if scored_fixes.size >= 2:
        travelled = geo.path_length(true_e[scored_fixes], true_n[scored_fixes])
    else:
        travelled = distance_m

    # How far apart the bracketing real fixes are: the scale of any
    # interpolation the reader should mentally subtract.
    prior = fix_rows[fix_rows <= eval_row]
    if prior.size >= 2:
        a, b = int(prior[-2]), int(prior[-1])
        truth_gap = float(np.hypot(true_e[b] - true_e[a], true_n[b] - true_n[a]))
    else:
        truth_gap = float("nan")

    value = None
    if cov_xy is not None:
        e_vec = np.stack(
            [est_e[span] - true_e[span], est_n[span] - true_n[span]], axis=1
        )
        value = nees(e_vec, cov_xy[span])

    return OutageResult(
        sequence=sequence,
        method=method,
        horizon_s=horizon_s,
        t_eval_s=float(time_s[eval_row] - time_s[start_row]),
        distance_m=travelled,
        crse_m=crse,
        cte_m=cte,
        ate_m=ate,
        drift_pct=100.0 * crse / travelled if travelled > 0 else float("nan"),
        n_fixes_suppressed=n_fixes_suppressed,
        truth_gap_m=truth_gap,
        nees=value,
    )


#: The PS's own target: "dead reckoning drift restricted to less than 10% of
#: the total distance travelled".
PS_DRIFT_TARGET_PCT = 10.0

AIDED_MODES = ("GNSS_AIDED", "DEGRADED")


def transition_metrics(
    *,
    time_s: np.ndarray,
    mode: np.ndarray,
    est_e: np.ndarray,
    est_n: np.ndarray,
    speed_ms: np.ndarray,
    true_e: np.ndarray,
    true_n: np.ndarray,
    fix_rows: np.ndarray,
    start_row: int,
    mask_end_row: int,
    window_s: float = 30.0,
) -> TransitionMetrics:
    """Score the two transitions of one outage. See :class:`TransitionMetrics`.

    All arrays are full-length (one entry per sequence row); ``mode`` holds the
    :class:`GnssMode` values as strings. Rows outside the estimator's run are
    NaN in ``est_*`` and are simply not scored.
    """
    nan = float("nan")
    t = np.asarray(time_s, dtype=float)
    modes = np.asarray(mode, dtype=object)

    dr = np.flatnonzero(modes[start_row:] == "DEAD_RECKONING")
    latency = float(t[start_row + dr[0]] - t[start_row]) if dr.size else nan

    after = fix_rows[fix_rows >= mask_end_row]
    if after.size == 0:
        return TransitionMetrics(latency, nan, nan, nan, nan)
    k0 = int(after[0])
    snap = float(np.hypot(est_e[k0] - true_e[k0], est_n[k0] - true_n[k0]))

    k_end = int(np.searchsorted(t, t[k0] + window_s, side="right"))
    k_end = min(k_end, len(t))
    excess = nan
    if k_end > k0 + 1:
        de = np.diff(est_e[k0:k_end])
        dn = np.diff(est_n[k0:k_end])
        dt = np.diff(t[k0:k_end])
        own = np.asarray(speed_ms, dtype=float)[k0 + 1 : k_end] * dt
        steps = np.hypot(de, dn) - own
        steps = steps[np.isfinite(steps)]
        if steps.size:
            excess = float(max(0.0, np.max(steps)))

    # Settling only means something if dead reckoning was entered at all.
    back = np.flatnonzero(np.isin(modes[k0 + 1 : k_end], AIDED_MODES))
    settle = float(t[k0 + 1 + back[0]] - t[k0]) if (back.size and dr.size) else nan

    residual = nan
    if after.size >= 2:
        k1 = int(after[1])
        if k1 < len(est_e) and np.isfinite(est_e[k1]):
            residual = float(np.hypot(est_e[k1] - true_e[k1], est_n[k1] - true_n[k1]))

    return TransitionMetrics(latency, snap, excess, settle, residual)


def calibrated_radius(cov_xy: np.ndarray, lam: float, level: float = 0.90) -> float:
    """Radius of the circle the app draws, in metres.

    The ellipse at ``level`` has semi-axes ``lam * r(level) * sqrt(eig)``; the
    displayed ring is the circle circumscribing it, so the major axis is used.
    ``lam`` is the conformal inflation factor (1.0 for the raw covariance).
    """
    # Rayleigh quantile, as in evaluation.conformal.chi2_radius.
    nominal = float(np.sqrt(-2.0 * np.log(1.0 - level)))
    eig = np.linalg.eigvalsh(np.asarray(cov_xy, dtype=float))
    return float(lam * nominal * np.sqrt(max(float(eig[-1]), 0.0)))


def _nanmedian(values: list[float | None]) -> float:
    vals = [v for v in values if v is not None and np.isfinite(v)]
    return float(np.median(vals)) if vals else float("nan")


def summarise(results: list[OutageResult]) -> dict[float, dict[str, float]]:
    """Aggregate per horizon. Median is the headline; these are heavy-tailed."""
    out: dict[float, dict[str, float]] = {}
    for horizon in sorted({r.horizon_s for r in results}):
        rs = [r for r in results if r.horizon_s == horizon]
        crse = np.array([r.crse_m for r in rs])
        cte = np.array([r.cte_m for r in rs])
        drift = np.array([r.drift_pct for r in rs])
        finite_drift = drift[np.isfinite(drift)]
        out[horizon] = {
            "n": len(rs),
            "crse_median_m": float(np.median(crse)),
            "crse_p90_m": float(np.percentile(crse, 90)),
            "crse_mean_m": float(np.mean(crse)),
            "cte_median_m": float(np.median(cte)),
            "drift_median_pct": float(np.median(drift)),
            "share_under_10pct": (
                float(np.mean(finite_drift < PS_DRIFT_TARGET_PCT))
                if finite_drift.size else float("nan")
            ),
            "t_eval_median_s": float(np.median([r.t_eval_s for r in rs])),
            "truth_gap_median_m": float(np.nanmedian([r.truth_gap_m for r in rs])),
            "detection_latency_median_s": _nanmedian([r.detection_latency_s for r in rs]),
            "reacq_snap_median_m": _nanmedian([r.reacq_snap_m for r in rs]),
            "reacq_max_step_median_m": _nanmedian([r.reacq_max_step_m for r in rs]),
            "reacq_settle_median_s": _nanmedian([r.reacq_settle_s for r in rs]),
            "reacq_residual_median_m": _nanmedian([r.reacq_residual_m for r in rs]),
            "radius90_raw_median_m": _nanmedian([r.radius90_raw_m for r in rs]),
            "radius90_cal_median_m": _nanmedian([r.radius90_cal_m for r in rs]),
        }
    return out
