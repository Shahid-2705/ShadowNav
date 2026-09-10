"""Cross-method comparisons over committed per-outage records.

Two comparisons a judge will ask for that a per-method summary cannot answer:

* what share of outages meet the problem statement's drift target
  (``< 10% of distance travelled``);
* what share of outages one method wins against another, **paired** on the
  identical outage -- same sequence, same horizon, same evaluation instant --
  because comparing medians across two different sets of outages is an
  artefact, not a result.

Records are the plain dicts stored in ``eval/results/*.json`` so this module
never needs to re-run anything.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from .metrics import PS_DRIFT_TARGET_PCT  # noqa: F401  (re-exported for callers)

Record = dict


def _key(r: Record) -> tuple[str, float, float]:
    return (str(r["sequence"]), float(r["horizon_s"]), round(float(r["t_eval_s"]), 3))


def share_under_drift(records: list[Record], target_pct: float) -> dict[float, float]:
    """Fraction of outages, per horizon, with drift strictly below ``target_pct``."""
    by_h: dict[float, list[bool]] = defaultdict(list)
    for r in records:
        d = float(r["drift_pct"])
        if np.isfinite(d):
            by_h[float(r["horizon_s"])].append(d < target_pct)
    return {h: float(np.mean(v)) for h, v in sorted(by_h.items())}


def _pairs(ours: list[Record], theirs: list[Record]) -> dict[float, list[tuple[float, float]]]:
    index = {_key(r): float(r["crse_m"]) for r in theirs}
    out: dict[float, list[tuple[float, float]]] = defaultdict(list)
    for r in ours:
        k = _key(r)
        if k in index:
            out[k[1]].append((float(r["crse_m"]), index[k]))
    return out


def share_beating(ours: list[Record], theirs: list[Record]) -> dict[float, float]:
    """Per horizon, fraction of paired outages where ``ours`` has the smaller CRSE."""
    return {
        h: float(np.mean([a < b for a, b in ps]))
        for h, ps in sorted(_pairs(ours, theirs).items())
    }


def paired_count(ours: list[Record], theirs: list[Record]) -> dict[float, int]:
    """How many outages were actually paired, per horizon."""
    return {h: len(ps) for h, ps in sorted(_pairs(ours, theirs).items())}


def paired_median_ratio(ours: list[Record], theirs: list[Record]) -> dict[float, float]:
    """Median of theirs/ours CRSE over paired outages (>1 means ours is closer)."""
    return {
        h: float(np.median([b / max(a, 1e-9) for a, b in ps]))
        for h, ps in sorted(_pairs(ours, theirs).items())
    }
