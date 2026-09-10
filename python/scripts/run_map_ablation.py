"""Paired ablation of the heading-only map constraint (shadownav.map).

Replicates ``run_mvp.py``'s outage loop exactly -- same split, same seed, same
masking, same scoring rows -- and runs every outage twice on identical inputs,
with and without the constraint. Cross-track error is the primary metric: a
heading-only constraint can only touch the component of error perpendicular
to the road, so CRSE (dominated by along-track speed staleness) is reported
second. Every outage also carries the constraint's own decision counts, so a
"no effect" result can be told apart from "never applied".

Maps come from the ``data/osm/`` cache written by ``fetch_osm.py``; nothing is
fetched here. A route without a cached map runs with the constraint disabled
and is reported as such.

Tune on ``--fold val`` only. The test fold is run once, with the chosen config.

Run:  PYTHONPATH=. python scripts/run_map_ablation.py [--fold test] [--sigma-deg 5]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fetch_osm import OSM_DIR, cache_name, iter_fold_sequences, sequence_bbox  # noqa: E402
from shadownav import geo  # noqa: E402
from shadownav import pipeline_kinematic as pipeline  # noqa: E402
from shadownav.data import iovnbd  # noqa: E402
from shadownav.evaluation import masking, metrics, splits  # noqa: E402
from shadownav.map import osm  # noqa: E402
from shadownav.map.heading_constraint import (  # noqa: E402
    Decision, HeadingConstraint, HeadingConstraintConfig, HeadingObserver,
)
from shadownav.utils.seed import seed_everything  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REACQ_TAIL_ROWS = 400            # as run_mvp.py
WARM_ROWS = 300                  # as run_mvp.py
METHOD_ON = "kinematic_maphead"
METHOD_OFF = "kinematic_maphead_off"


@dataclasses.dataclass(frozen=True)
class MapStats:
    """What the constraint did inside one outage's masked window."""

    has_map: bool
    n_window_epochs: int
    counts_window: dict[str, int]
    counts_run: dict[str, int]

    @property
    def self_disabled(self) -> bool:
        return self.counts_window.get(Decision.DISABLED.value, 0) > 0

    @property
    def applied_share(self) -> float:
        n = self.counts_window.get(Decision.APPLIED.value, 0)
        return n / self.n_window_epochs if self.n_window_epochs else 0.0

    def as_dict(self) -> dict:
        return {
            "has_map": self.has_map, "n_window_epochs": self.n_window_epochs,
            "self_disabled": self.self_disabled, "applied_share": self.applied_share,
            "counts_window": self.counts_window, "counts_run": self.counts_run,
        }


def window_stats(observer: HeadingObserver | None, w: masking.OutageWindow) -> MapStats:
    if observer is None:
        return MapStats(False, 0, {}, {})
    inside = [e for e in observer.epochs if w.start_row <= e.row < w.end_row]
    counts = {d.value: 0 for d in Decision}
    for e in inside:
        counts[e.decision.value] += 1
    return MapStats(True, len(inside), counts, observer.counts())


def load_map(seq: iovnbd.Sequence, pad_m: float) -> osm.FetchResult:
    """Cache only: an absent map is a result, not a reason to go online."""
    return osm.fetch_highways(cache_name(seq.name), sequence_bbox(seq, pad_m), OSM_DIR,
                              endpoints=(), retry_wait_s=0.0)


def score(seq, w, horizon, traj, warm, run_end, true_e, true_n, usable, method):
    est_e = np.full(len(seq), np.nan)
    est_n = np.full(len(seq), np.nan)
    est_e[warm : run_end + 1] = traj.east_m
    est_n[warm : run_end + 1] = traj.north_m
    return metrics.evaluate_window(
        sequence=seq.name, method=method, horizon_s=horizon, time_s=seq.time_s,
        est_e=est_e, est_n=est_n, true_e=true_e, true_n=true_n, fix_rows=usable,
        start_row=w.start_row, distance_m=w.distance_m,
        n_fixes_suppressed=w.n_fixes_suppressed,
    )


def run_outage(seq, w, horizon, cfg, constraint, true_e, true_n, fix_rows):
    """One outage, both arms. Returns (off_result, on_result, stats) or None.

    Protocol as ``run_mvp.py``: the scoring fix is found first and the mask
    is stretched through it (``masking.extend_to_row``), so the scored
    estimate is unconditionally unaided in both arms.
    """
    end_row = min(len(seq) - 1, w.start_row + int(horizon * 10) + 150)
    if end_row <= w.start_row + 2:
        return None
    usable = fix_rows[(fix_rows >= w.start_row) & (fix_rows <= end_row)]
    eval_row = metrics.evaluation_row(seq.time_s, usable, w.start_row, horizon)
    if eval_row is None:
        return None
    scored = masking.extend_to_row(seq, w, eval_row)
    run_end = min(len(seq) - 1, eval_row + REACQ_TAIL_ROWS)
    warm = max(0, w.start_row - WARM_ROWS)
    masked = masking.apply_mask(seq, scored)
    observer = HeadingObserver(constraint) if constraint is not None else None
    try:
        off = pipeline.run(masked, config=cfg, start_row=warm, end_row=run_end)
        on = pipeline.run(masked, config=cfg, start_row=warm, end_row=run_end,
                          heading_observer=observer)
    except (ValueError, np.linalg.LinAlgError):
        return None
    r_off = score(seq, scored, horizon, off, warm, run_end, true_e, true_n, usable, METHOD_OFF)
    r_on = score(seq, scored, horizon, on, warm, run_end, true_e, true_n, usable, METHOD_ON)
    if r_off is None or r_on is None or not (np.isfinite(r_off.crse_m) and np.isfinite(r_on.crse_m)):
        return None
    return r_off, r_on, window_stats(observer, scored)


def evaluate_sequence(seq, split, cfg, constraint):
    ref_lat, ref_lon = pipeline.enu_reference(seq)
    true_e, true_n = geo.lla_to_enu(
        seq.df["gps_lat_deg"].to_numpy(), seq.df["gps_lon_deg"].to_numpy(), ref_lat, ref_lon,
    )
    fix_rows = np.flatnonzero(seq.df["gps_fix_is_new"].to_numpy())
    out = []
    for horizon in split.horizons_s:
        windows = masking.plan_outages(
            seq, horizon, n=split.outages_per_sequence, seed=split.seed,
            min_speed_ms=split.min_speed_ms, guard_s=split.guard_s,
        )
        for w in windows:
            if not w.informative:
                continue
            triple = run_outage(seq, w, horizon, cfg, constraint, true_e, true_n, fix_rows)
            if triple is not None:
                out.append(triple)
    return out


def build_constraint(seq, mcfg, pad_m):
    res = load_map(seq, pad_m)
    if res.network is None:
        return None, res
    ref_lat, ref_lon = pipeline.enu_reference(seq)
    return HeadingConstraint.from_network(res.network, ref_lat, ref_lon, mcfg), res


def paired_summary(rows: list[dict]) -> dict[str, dict]:
    """Per horizon: medians of both arms and the paired share improved."""
    out = {}
    for h in sorted({r["horizon_s"] for r in rows}):
        rs = [r for r in rows if r["horizon_s"] == h]
        cte_on = np.array([r["on"]["cte_m"] for r in rs])
        cte_off = np.array([r["off"]["cte_m"] for r in rs])
        crse_on = np.array([r["on"]["crse_m"] for r in rs])
        crse_off = np.array([r["off"]["crse_m"] for r in rs])
        st = [r["map"] for r in rs]
        out[str(h)] = {
            "n": len(rs),
            "cte_median_off_m": float(np.median(cte_off)),
            "cte_median_on_m": float(np.median(cte_on)),
            "crse_median_off_m": float(np.median(crse_off)),
            "crse_median_on_m": float(np.median(crse_on)),
            "cte_delta_median_m": float(np.median(cte_on - cte_off)),
            "crse_delta_median_m": float(np.median(crse_on - crse_off)),
            "share_cte_improved": float(np.mean(cte_on < cte_off)),
            "share_cte_worse": float(np.mean(cte_on > cte_off)),
            "share_crse_improved": float(np.mean(crse_on < crse_off)),
            "n_no_map": int(sum(not s["has_map"] for s in st)),
            "n_self_disabled": int(sum(s["self_disabled"] for s in st)),
            "n_never_applied": int(sum(s["has_map"] and s["counts_window"].get("applied", 0) == 0 for s in st)),
            "applied_share_median": float(np.median([s["applied_share"] for s in st])),
        }
    return out


def decision_totals(rows: list[dict]) -> dict[str, int]:
    tot: dict[str, int] = defaultdict(int)
    for r in rows:
        for k, v in r["map"]["counts_window"].items():
            tot[k] += v
    return dict(tot)


def print_report(paired: dict, totals: dict, coverage: list[dict]) -> None:
    print(f"\n{'horizon':>8} {'n':>4} {'CTE off':>8} {'CTE on':>8} {'CRSE off':>9} {'CRSE on':>8} "
          f"{'CTE<':>6} {'CTE>':>6} {'CRSE<':>6} {'nomap':>5} {'disab':>5} {'never':>5} {'appl%':>6}")
    for h, s in paired.items():
        print(f"{float(h):>8.0f} {s['n']:>4} {s['cte_median_off_m']:>8.1f} {s['cte_median_on_m']:>8.1f} "
              f"{s['crse_median_off_m']:>9.1f} {s['crse_median_on_m']:>8.1f} "
              f"{100 * s['share_cte_improved']:>5.0f}% {100 * s['share_cte_worse']:>5.0f}% "
              f"{100 * s['share_crse_improved']:>5.0f}% {s['n_no_map']:>5} {s['n_self_disabled']:>5} "
              f"{s['n_never_applied']:>5} {100 * s['applied_share_median']:>5.0f}%")
    n_ep = max(sum(totals.values()), 1)
    print("\ndecisions inside masked windows (all outages): "
          + ", ".join(f"{k}={v} ({100 * v / n_ep:.0f}%)" for k, v in sorted(totals.items(), key=lambda kv: -kv[1])))
    print("\nmap coverage: " + ", ".join(
        f"{c['sequence']}={'%d ways' % c['ways'] if c['has_map'] else 'NO MAP'}" for c in coverage))


def write_results(out_dir: Path, suffix: str, rows: list[dict], paired: dict, totals: dict,
                  coverage: list[dict], mcfg, split, fold: str, n_seq: int) -> tuple[Path, Path]:
    def blob(method: str, key: str) -> dict:
        results = [r[key] for r in rows]
        objs = [metrics.OutageResult(**r) for r in results]
        return {
            "method": method, "seed": split.seed, "fold": fold, "n_sequences": n_seq,
            "n_outages": len(results),
            "summary": {str(k): v for k, v in metrics.summarise(objs).items()},
            "per_fold": {fold: {str(k): v for k, v in metrics.summarise(objs).items()}},
            "results": results,
        }
    on = blob(METHOD_ON, "on") | {
        "constraint_config": dataclasses.asdict(mcfg),
        "paired": paired, "decision_totals_window": totals, "map_coverage": coverage,
        "per_outage_map": [r["map"] | {"sequence": r["on"]["sequence"], "horizon_s": r["horizon_s"]} for r in rows],
    }
    off = blob(METHOD_OFF, "off")
    p_on = out_dir / f"{METHOD_ON}{suffix}.json"
    p_off = out_dir / f"{METHOD_OFF}{suffix}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    p_on.write_text(json.dumps(on, indent=2), encoding="utf-8")
    p_off.write_text(json.dumps(off, indent=2), encoding="utf-8")
    return p_on, p_off


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fold", default="test", choices=["test", "val"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pad-m", type=float, default=300.0)
    ap.add_argument("--radius-m", type=float, default=30.0)
    ap.add_argument("--agreement-deg", type=float, default=5.0)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--lookahead-m", type=float, default=40.0)
    ap.add_argument("--gate-sigma-deg", type=float, default=10.0)
    ap.add_argument("--sigma-deg", type=float, default=5.0)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "eval" / "results")
    ap.add_argument("--suffix", default="", help="appended to both output file names")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    seed_everything()
    split = splits.load_split()
    cfg = pipeline.KinematicPipelineConfig()
    mcfg = HeadingConstraintConfig(
        search_radius_m=args.radius_m, agreement_deg=args.agreement_deg,
        min_consistent_epochs=args.epochs, junction_lookahead_m=args.lookahead_m,
        gate_sigma_deg=args.gate_sigma_deg, sigma_deg=args.sigma_deg,
    )
    print(f"fold: {args.fold}   constraint: {mcfg}")

    rows: list[dict] = []
    coverage: list[dict] = []
    n_seq = 0
    t0 = time.monotonic()
    for _, seq in iter_fold_sequences((args.fold,)):
        if args.limit is not None and n_seq >= args.limit:
            break
        n_seq += 1
        constraint, res = build_constraint(seq, mcfg, args.pad_m)
        ways = res.network.n_ways if res.network else 0
        coverage.append({"sequence": seq.name, "has_map": constraint is not None, "ways": ways,
                         "source": res.source, "note": "" if constraint else res.message[:100]})
        triples = evaluate_sequence(seq, split, cfg, constraint)
        rows.extend({"horizon_s": r_on.horizon_s, "off": r_off.as_dict(), "on": r_on.as_dict(),
                     "map": st.as_dict()} for r_off, r_on, st in triples)
        print(f"  {seq.name:<12} map={'%6d ways' % ways if constraint else 'NONE      '} "
              f"outages={len(triples):>3}  t={time.monotonic() - t0:6.0f}s")
        sys.stdout.flush()

    if not rows:
        print("no evaluable outages produced")
        return 1
    paired = paired_summary(rows)
    totals = decision_totals(rows)
    print_report(paired, totals, coverage)
    p_on, p_off = write_results(args.out_dir, args.suffix, rows, paired, totals, coverage,
                                mcfg, split, args.fold, n_seq)
    print(f"\nwrote {p_on}\nwrote {p_off}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
