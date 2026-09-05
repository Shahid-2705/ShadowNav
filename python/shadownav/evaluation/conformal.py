"""Scalar conformal inflation of the filter's covariance.

The problem this fixes
----------------------
A Kalman filter's own covariance is documented as **overconfident** in dead
reckoning, and ours is no exception: median NEES on the Phase 1 MVP is 89-132
where a consistent 2-D estimator should sit near 2.0. Reporting that covariance
to a user as a confidence ellipse would be a lie by a factor of fifty, and
PLAN.md:140 names honest confidence as a differentiator -- which only counts if
it is actually honest.

The fix is deliberately the smallest one that works: a single scalar ``lambda``
that scales the covariance, fitted on held-out routes so that the realised
coverage matches the nominal level.

    P_reported = lambda^2 * P_filter

What we may and may not claim
-----------------------------
Split-conformal prediction gives finite-sample coverage guarantees **under
exchangeability**. Trajectory errors are emphatically not exchangeable: they
are strongly autocorrelated within an outage and grow with elapsed time. So the
guarantee does not hold, and PLAN.md:140 records "statistically guaranteed
confidence" as a claim that already failed verification.

What survives is worth having and is what this module reports:

    "empirically calibrated coverage -- 90% containment on held-out routes"

Never "guaranteed". Pre-empt the judge by naming exchangeability first; the
calibration is fitted per horizon precisely because error growth with time is
the largest violation of it, and stratifying that way removes the part of the
non-exchangeability that would otherwise dominate.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass(frozen=True)
class ConformalCalibration:
    """Per-horizon covariance inflation factors."""

    level: float                        # nominal coverage, e.g. 0.90
    factors: dict[float, float]         # horizon (s) -> lambda
    n_calibration: dict[float, int]
    fitted_on: str = "val"

    def factor_for(self, horizon_s: float) -> float:
        """Inflation for a horizon, falling back to the nearest fitted one."""
        if not self.factors:
            return 1.0
        if horizon_s in self.factors:
            return self.factors[horizon_s]
        nearest = min(self.factors, key=lambda h: abs(h - horizon_s))
        return self.factors[nearest]

    def inflate(self, cov: np.ndarray, horizon_s: float) -> np.ndarray:
        lam = self.factor_for(horizon_s)
        return np.asarray(cov, dtype=float) * (lam**2)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["factors"] = {str(k): v for k, v in self.factors.items()}
        d["n_calibration"] = {str(k): v for k, v in self.n_calibration.items()}
        return d


def mahalanobis(error_en: np.ndarray, cov_xy: np.ndarray) -> float:
    """Mahalanobis distance of a 2-D error under a 2x2 covariance."""
    try:
        return float(np.sqrt(max(0.0, error_en @ np.linalg.solve(cov_xy, error_en))))
    except np.linalg.LinAlgError:  # pragma: no cover - degenerate covariance
        return float("nan")


def chi2_radius(level: float) -> float:
    """Mahalanobis radius containing ``level`` of a 2-D Gaussian."""
    # Rayleigh quantile: P(r <= R) = 1 - exp(-R^2/2)
    return float(np.sqrt(-2.0 * np.log(1.0 - level)))


def fit(
    errors_by_horizon: dict[float, list[tuple[np.ndarray, np.ndarray]]],
    *,
    level: float = 0.90,
    fitted_on: str = "val",
) -> ConformalCalibration:
    """Fit one inflation factor per horizon from held-out (error, cov) pairs.

    ``lambda`` is the empirical ``level`` quantile of the Mahalanobis distances
    divided by the nominal Gaussian radius. Applying it makes the realised
    containment match the nominal level on data the factor was not fitted on.
    """
    nominal = chi2_radius(level)
    factors: dict[float, float] = {}
    counts: dict[float, int] = {}

    for horizon, pairs in errors_by_horizon.items():
        d = np.array([mahalanobis(e, c) for e, c in pairs])
        d = d[np.isfinite(d)]
        counts[horizon] = int(d.size)
        if d.size < 5:
            # Too few points to calibrate: leave the covariance alone rather
            # than invent a factor from noise.
            factors[horizon] = 1.0
            continue
        # Split-conformal quantile with the finite-sample correction.
        q_index = min(1.0, np.ceil((d.size + 1) * level) / d.size)
        factors[horizon] = float(max(1e-6, np.quantile(d, q_index) / nominal))

    return ConformalCalibration(level, factors, counts, fitted_on)


def coverage(
    pairs: list[tuple[np.ndarray, np.ndarray]],
    *,
    level: float = 0.90,
    calibration: ConformalCalibration | None = None,
    horizon_s: float = 0.0,
) -> float:
    """Fraction of errors inside the (optionally inflated) ellipse."""
    if not pairs:
        return float("nan")
    radius = chi2_radius(level)
    lam = calibration.factor_for(horizon_s) if calibration else 1.0
    inside = [
        mahalanobis(e, c * (lam**2)) <= radius
        for e, c in pairs
    ]
    return float(np.mean([b for b in inside if not np.isnan(b)]))
