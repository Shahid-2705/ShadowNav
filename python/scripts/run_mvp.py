"""Evaluate the Phase 1 MVP against the Phase 0 drift floor.

Same split, same seed, same outage windows, same metric definitions as
``run_baseline.py`` -- the only thing that changes is the estimator, so the
comparison is like-for-like.

Run:  PYTHONPATH=. python scripts/run_mvp.py [--fold test] [--limit N]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav import geo  # noqa: E402
from shadownav import pipeline_kinematic as pipeline  # noqa: E402
from shadownav.data import fetch, iovnbd  # noqa: E402
from shadownav.evaluation import masking, metrics, splits  # noqa: E402
from shadownav.utils.seed import seed_everything  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

#: Rows run past the scoring window so the re-acquisition can be watched.
#: The gate escape fires after three rejected fixes, i.e. up to ~27 s at the
#: dataset's 9 s fix period, and a blend that only completes then must be
#: caught rather than reported as "no jump".
REACQ_TAIL_ROWS = 400


def load_conformal_factors(path: Path = ROOT / "shared" / "conformal.json") -> dict[float, float]:
    """Per-horizon inflation factors fitted on the val fold, if committed."""
    if not path.exists():
        return {}
    blob = json.loads(path.read_text(encoding="utf-8"))
    return {float(h): float(v) for h, v in blob.get("factors", {}).items()}


def nearest_factor(factors: dict[float, float], horizon_s: float) -> float:
    if not factors:
        return 1.0
    nearest = min(factors, key=lambda h: abs(h - horizon_s))
    return factors[nearest]


def evaluate_sequence(
    seq: iovnbd.Sequence,
    split: splits.Split,
    cfg: pipeline.KinematicPipelineConfig,
    method: str,
    aligned_any: list[bool] | None = None,
    speed_estimator=None,
    factors: dict[float, float] | None = None,
) -> list[metrics.OutageResult]:
    factors = factors if factors is not None else {}
    ref_lat, ref_lon = pipeline.enu_reference(seq)
    true_e, true_n = geo.lla_to_enu(
        seq.df["gps_lat_deg"].to_numpy(),
        seq.df["gps_lon_deg"].to_numpy(),
        ref_lat, ref_lon,
    )
    fix_rows = np.flatnonzero(seq.df["gps_fix_is_new"].to_numpy())
    out: list[metrics.OutageResult] = []

    for horizon in split.horizons_s:
        windows = masking.plan_outages(
            seq, horizon,
            n=split.outages_per_sequence, seed=split.seed,
            min_speed_ms=split.min_speed_ms, guard_s=split.guard_s,
        )
        for w in windows:
            if not w.informative:
                continue
            end_row = min(len(seq) - 1, w.start_row + int(horizon * 10) + 150)
            if end_row <= w.start_row + 2:
                continue

            # Find the scoring instant *before* running, and hide GNSS through
            # it: the fix used to score the estimate must never be handed to
            # the estimator (masking.extend_to_row explains why). The run then
            # continues past it so the re-acquisition can be measured.
            usable = fix_rows[(fix_rows >= w.start_row) & (fix_rows <= end_row)]
            eval_row = metrics.evaluation_row(seq.time_s, usable, w.start_row, horizon)
            if eval_row is None:
                continue
            scored = masking.extend_to_row(seq, w, eval_row)
            run_end = min(len(seq) - 1, eval_row + REACQ_TAIL_ROWS)

            # Give the filter pre-outage context to settle its biases on.
            warm = max(0, w.start_row - 300)
            masked = masking.apply_mask(seq, scored)
            if speed_estimator is not None:
                # Fix the vertical once per drive from aided data. Re-estimating
                # it per window reintroduces the short-window tilt error.
                speed_estimator.set_gravity(
                    seq.df[["acc_x", "acc_y", "acc_z"]].to_numpy()[: w.start_row + 1]
                )
            try:
                traj = pipeline.run(
                    masked, config=cfg, start_row=warm, end_row=run_end,
                    speed_estimator=speed_estimator,
                )
            except (ValueError, np.linalg.LinAlgError):
                continue
            if aligned_any is not None:
                aligned_any.append(traj.aligned)

            est_e = np.full(len(seq), np.nan)
            est_n = np.full(len(seq), np.nan)
            speed = np.full(len(seq), np.nan)
            mode = np.full(len(seq), None, dtype=object)
            cov = np.zeros((len(seq), 2, 2))
            sl = slice(warm, run_end + 1)
            est_e[sl] = traj.east_m
            est_n[sl] = traj.north_m
            speed[sl] = traj.speed_ms
            mode[sl] = traj.mode
            cov[sl] = traj.cov_xy

            res = metrics.evaluate_window(
                sequence=seq.name, method=method, horizon_s=horizon,
                time_s=seq.time_s, est_e=est_e, est_n=est_n,
                true_e=true_e, true_n=true_n,
                fix_rows=usable, start_row=w.start_row,
                distance_m=scored.distance_m,
                n_fixes_suppressed=scored.n_fixes_suppressed,
                cov_xy=cov,
            )
            if res is None or not np.isfinite(res.crse_m):
                continue

            transitions = metrics.transition_metrics(
                time_s=seq.time_s, mode=mode, est_e=est_e, est_n=est_n,
                speed_ms=speed, true_e=true_e, true_n=true_n,
                fix_rows=fix_rows, start_row=w.start_row,
                mask_end_row=scored.end_row,
            )
            lam = nearest_factor(factors, horizon)
            out.append(dataclasses.replace(
                res,
                **transitions.as_dict(),
                radius90_raw_m=metrics.calibrated_radius(cov[eval_row], 1.0),
                radius90_cal_m=metrics.calibrated_radius(cov[eval_row], lam),
            ))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fold", default="all", choices=["all", "train", "val", "test"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--cent", action="store_true",
                    help="ablation: enable the centripetal-consistency observation")
    ap.add_argument("--accel-speed", action="store_true",
                    help="ablation: integrate forward accel instead of holding speed")
    ap.add_argument("--speednet", action="store_true",
                    help="use the trained CNN+GRU forward-speed front end")
    ap.add_argument("--speednet-checkpoint", type=Path, default=None,
                    help="override the checkpoint path (default: shared/speednet.pt); "
                         "for evaluating experimental checkpoints, e.g. an ensemble, "
                         "without touching the committed default")
    ap.add_argument("--speednet-gate", type=float, default=None,
                    help="hard confidence gate: skip the speed update entirely "
                         "when the network's sigma exceeds this (m/s)")
    ap.add_argument("--gated", action="store_true",
                    help="wrap --speednet in the confidence gate (models/gate.py)")
    ap.add_argument("--no-ackermann", action="store_true",
                    help="ablation: disable the Ackermann curvature/friction bounds")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.gated and not args.speednet:
        ap.error("--gated requires --speednet")

    seed_everything()
    split = splits.load_split()
    cfg = pipeline.KinematicPipelineConfig(
        use_centripetal=args.cent,
        use_accel_speed=args.accel_speed,
        use_ackermann=not args.no_ackermann,
        speednet_sigma_gate=args.speednet_gate,
    )
    method = "kinematic"
    if args.cent:
        method += "_cent"
    if args.accel_speed:
        method += "_accel"
    if args.no_ackermann:
        method += "_no_ack"
    if args.speednet_gate is not None:
        method += f"_gate{args.speednet_gate:g}"

    speed_estimator = None
    if args.speednet:
        from shadownav.models.inference import GatedSpeedNetEstimator, SpeedNetEstimator

        if args.gated:
            speed_estimator = GatedSpeedNetEstimator(checkpoint=args.speednet_checkpoint)
            method += "_speednet_gated"
        else:
            speed_estimator = SpeedNetEstimator(checkpoint=args.speednet_checkpoint)
            method += "_speednet"
        print(f"speed front end: {speed_estimator.variant} variant, "
              f"window {speed_estimator.window}")

    data_dir = fetch.default_data_dir() / "iovnbd" / "S"
    paths = sorted(data_dir.glob("S-*.csv"))
    if not paths:
        print(f"no data in {data_dir}; run: python -m shadownav.data.fetch")
        return 1

    results: list[metrics.OutageResult] = []
    per_fold: dict[str, list[metrics.OutageResult]] = defaultdict(list)
    n_seq = 0
    aligned_flags: list[bool] = []
    factors = load_conformal_factors()
    if factors:
        print("conformal factors loaded from shared/conformal.json: "
              + ", ".join(f"{h:.0f}s={v:.1f}" for h, v in sorted(factors.items())))

    for path in paths:
        try:
            sessions = iovnbd.load_s_sessions(path)
        except iovnbd.IOVNBDError:
            continue
        for seq in sessions:
            fold = split.fold_of(seq.name)
            if args.fold != "all" and fold != args.fold:
                continue
            if args.limit is not None and n_seq >= args.limit:
                break
            n_seq += 1
            rs = evaluate_sequence(seq, split, cfg, method, aligned_flags,
                                   speed_estimator, factors)
            results.extend(rs)
            per_fold[fold].extend(rs)

    if not results:
        print("no evaluable outages produced")
        return 1

    summary = metrics.summarise(results)
    frac = (100.0 * sum(aligned_flags) / len(aligned_flags)) if aligned_flags else 0.0
    print(f"method: {method}   sequences: {n_seq}   outages scored: {len(results)}")
    print(f"device-to-car alignment observable in {frac:.0f}% of runs")
    print(f"{'horizon':>8} {'n':>5} {'t_eval':>7} {'CRSE med':>10} {'CRSE p90':>10} "
          f"{'CTE med':>9} {'drift med':>10} {'NEES':>8}")
    for h, s in summary.items():
        rs = [r for r in results if r.horizon_s == h]
        nees = np.nanmedian([r.nees for r in rs if r.nees is not None])
        print(f"{h:>8.0f} {s['n']:>5.0f} {s['t_eval_median_s']:>7.1f} "
              f"{s['crse_median_m']:>10.1f} {s['crse_p90_m']:>10.1f} "
              f"{s['cte_median_m']:>9.1f} {s['drift_median_pct']:>9.2f}% "
              f"{nees:>8.1f}")

    print("\nper fold, CRSE median (m):")
    for fold in ("train", "val", "test"):
        if per_fold[fold]:
            fs = metrics.summarise(per_fold[fold])
            print(f"  {fold:<6} " + "  ".join(
                f"{h:.0f}s={v['crse_median_m']:.1f}" for h, v in fs.items()))

    print("\ntransitions and the ring (medians):")
    print(f"{'horizon':>8} {'<10% drift':>10} {'detect s':>9} {'snap m':>8} "
          f"{'max step m':>11} {'settle s':>9} {'resid m':>8} {'ring raw':>9} {'ring cal':>9}")
    for h, s in summary.items():
        print(f"{h:>8.0f} {100 * s['share_under_10pct']:>9.1f}% "
              f"{s['detection_latency_median_s']:>9.2f} {s['reacq_snap_median_m']:>8.1f} "
              f"{s['reacq_max_step_median_m']:>11.1f} {s['reacq_settle_median_s']:>9.2f} "
              f"{s['reacq_residual_median_m']:>8.1f} {s['radius90_raw_median_m']:>9.1f} "
              f"{s['radius90_cal_median_m']:>9.1f}")

    # Head-to-head with the committed drift floor.
    floor_path = Path(__file__).resolve().parents[2] / "eval" / "results" / "baseline_naive.json"
    if floor_path.exists():
        floor = json.loads(floor_path.read_text(encoding="utf-8"))["summary"]
        print("\nvs naive strapdown floor (CRSE median):")
        for h, s in summary.items():
            base = floor.get(str(float(h)), {}).get("crse_median_m")
            if base:
                print(f"  {h:>5.0f}s  {base:>10.1f} m -> {s['crse_median_m']:>8.1f} m "
                      f"({base / max(s['crse_median_m'], 1e-9):>6.1f}x better)")

    gate = None
    if args.gated:
        gate = {"config": dataclasses.asdict(speed_estimator.config),
                "counts": speed_estimator.diagnostics()}
        print("\ngate decisions: "
              + ", ".join(f"{k}={v}" for k, v in gate["counts"].items()))

    out = args.out or (
        Path(__file__).resolve().parents[2] / "eval" / "results" / f"{method}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "method": method,
                "seed": split.seed,
                "n_sequences": n_seq,
                "n_outages": len(results),
                **({"gate": gate} if gate else {}),
                "summary": {str(k): v for k, v in summary.items()},
                "per_fold": {
                    f: {str(k): v for k, v in metrics.summarise(rs).items()}
                    for f, rs in per_fold.items() if rs
                },
                "results": [r.as_dict() for r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
