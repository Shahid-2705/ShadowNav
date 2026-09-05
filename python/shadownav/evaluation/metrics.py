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
    target_t = time_s[start_row] + horizon_s
    later = fix_rows[time_s[fix_rows] >= target_t]
    if later.size == 0:
        return None
    eval_row = int(later[0])

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


def summarise(results: list[OutageResult]) -> dict[float, dict[str, float]]:
    """Aggregate per horizon. Median is the headline; these are heavy-tailed."""
    out: dict[float, dict[str, float]] = {}
    for horizon in sorted({r.horizon_s for r in results}):
        rs = [r for r in results if r.horizon_s == horizon]
        crse = np.array([r.crse_m for r in rs])
        cte = np.array([r.cte_m for r in rs])
        drift = np.array([r.drift_pct for r in rs])
        out[horizon] = {
            "n": len(rs),
            "crse_median_m": float(np.median(crse)),
            "crse_p90_m": float(np.percentile(crse, 90)),
            "crse_mean_m": float(np.mean(crse)),
            "cte_median_m": float(np.median(cte)),
            "drift_median_pct": float(np.median(drift)),
            "t_eval_median_s": float(np.median([r.t_eval_s for r in rs])),
            "truth_gap_median_m": float(np.nanmedian([r.truth_gap_m for r in rs])),
        }
    return out
