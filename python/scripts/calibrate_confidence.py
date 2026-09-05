"""Fit and validate the conformal covariance inflation.

Fits one scalar per horizon on the **val** fold, then measures containment on
the **test** fold, which the factors never saw. That separation is the whole
point: a calibration measured on its own fitting data is not a calibration.

Reports NEES and 90% containment before and after, so the improvement is
visible rather than asserted.

Run:  PYTHONPATH=. python scripts/calibrate_confidence.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav import geo  # noqa: E402
from shadownav import pipeline_kinematic as pipeline  # noqa: E402
from shadownav.data import fetch, iovnbd  # noqa: E402
from shadownav.evaluation import conformal, masking, splits  # noqa: E402
from shadownav.utils.seed import seed_everything  # noqa: E402

Pair = tuple[np.ndarray, np.ndarray]


def collect(fold: str, split: splits.Split, cfg: pipeline.KinematicPipelineConfig,
            limit: int | None = None) -> dict[float, list[Pair]]:
    """Gather (position error, filter covariance) at each outage evaluation point."""
    data_dir = fetch.default_data_dir() / "iovnbd" / "S"
    out: dict[float, list[Pair]] = defaultdict(list)
    n_seq = 0

    for path in sorted(data_dir.glob("S-*.csv")):
        try:
            sessions = iovnbd.load_s_sessions(path)
        except iovnbd.IOVNBDError:
            continue
        for seq in sessions:
            if split.fold_of(seq.name) != fold:
                continue
            if limit is not None and n_seq >= limit:
                break
            n_seq += 1

            ref_lat, ref_lon = pipeline.enu_reference(seq)
            true_e, true_n = geo.lla_to_enu(
                seq.df["gps_lat_deg"].to_numpy(),
                seq.df["gps_lon_deg"].to_numpy(), ref_lat, ref_lon,
            )
            fix_rows = np.flatnonzero(seq.df["gps_fix_is_new"].to_numpy())

            for horizon in split.horizons_s:
                for w in masking.plan_outages(
                    seq, horizon, n=split.outages_per_sequence, seed=split.seed,
                    min_speed_ms=split.min_speed_ms, guard_s=split.guard_s,
                ):
                    if not w.informative:
                        continue
                    end_row = min(len(seq) - 1, w.start_row + int(horizon * 10) + 150)
                    if end_row <= w.start_row + 2:
                        continue
                    later = fix_rows[
                        (fix_rows >= w.start_row) & (fix_rows <= end_row)
                        & (seq.time_s[fix_rows] >= seq.time_s[w.start_row] + horizon)
                    ]
                    if later.size == 0:
                        continue
                    eval_row = int(later[0])

                    warm = max(0, w.start_row - 300)
                    try:
                        traj = pipeline.run(
                            masking.apply_mask(seq, w), config=cfg,
                            start_row=warm, end_row=end_row,
                        )
                    except (ValueError, np.linalg.LinAlgError):
                        continue

                    k = eval_row - warm
                    if k < 0 or k >= len(traj):
                        continue
                    err = np.array([
                        traj.east_m[k] - true_e[eval_row],
                        traj.north_m[k] - true_n[eval_row],
                    ])
                    cov = traj.cov_xy[k]
                    if np.all(np.isfinite(err)) and np.all(np.isfinite(cov)):
                        out[horizon].append((err, cov))
    return dict(out)


def nees_stats(pairs: list[Pair]) -> float:
    vals = []
    for e, c in pairs:
        try:
            vals.append(float(e @ np.linalg.solve(c, e)))
        except np.linalg.LinAlgError:
            continue
    return float(np.median(vals)) if vals else float("nan")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--level", type=float, default=0.90)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    seed_everything()
    split = splits.load_split()
    cfg = pipeline.KinematicPipelineConfig()

    print("collecting val fold (fitting set) ...")
    val = collect("val", split, cfg, args.limit)
    print("collecting test fold (held out) ...")
    test = collect("test", split, cfg, args.limit)
    if not val or not test:
        print("no data collected")
        return 1

    cal = conformal.fit(val, level=args.level, fitted_on="val")

    print(f"\nconformal inflation, nominal level {args.level:.0%}")
    print(f"{'horizon':>8} {'n_fit':>6} {'lambda':>8} "
          f"{'NEES med':>9} {'cover raw':>10} {'cover cal':>10} {'n_test':>7}")
    rows = []
    for horizon in sorted(test):
        pairs = test[horizon]
        raw = conformal.coverage(pairs, level=args.level)
        adj = conformal.coverage(pairs, level=args.level,
                                 calibration=cal, horizon_s=horizon)
        lam = cal.factor_for(horizon)
        nees = nees_stats(pairs)
        print(f"{horizon:>8.0f} {cal.n_calibration.get(horizon, 0):>6d} "
              f"{lam:>8.2f} {nees:>9.1f} {raw:>10.2f} {adj:>10.2f} {len(pairs):>7d}")
        rows.append({
            "horizon_s": horizon, "lambda": lam, "nees_median": nees,
            "coverage_raw": raw, "coverage_calibrated": adj,
            "n_test": len(pairs),
            "n_fit": cal.n_calibration.get(horizon, 0),
        })

    mean_raw = float(np.mean([r["coverage_raw"] for r in rows]))
    mean_adj = float(np.mean([r["coverage_calibrated"] for r in rows]))
    print(f"\nmean containment: raw {mean_raw:.2f} -> calibrated {mean_adj:.2f} "
          f"(nominal {args.level:.2f})")
    print("Report as: empirically calibrated coverage on held-out routes.")
    print("Never as guaranteed -- trajectory errors are not exchangeable.")

    out_dir = Path(__file__).resolve().parents[2] / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "conformal_calibration.json").write_text(
        json.dumps(
            {
                "level": args.level,
                "fitted_on": "val",
                "evaluated_on": "test",
                "calibration": cal.as_dict(),
                "per_horizon": rows,
                "mean_coverage_raw": mean_raw,
                "mean_coverage_calibrated": mean_adj,
                "claim": (
                    "empirically calibrated coverage on held-out routes; not a "
                    "guarantee -- trajectory errors are not exchangeable"
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (Path(__file__).resolve().parents[2] / "shared" / "conformal.json").parent.mkdir(
        parents=True, exist_ok=True
    )
    (Path(__file__).resolve().parents[2] / "shared" / "conformal.json").write_text(
        json.dumps(cal.as_dict(), indent=2), encoding="utf-8"
    )
    print(f"\nwrote {out_dir / 'conformal_calibration.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
