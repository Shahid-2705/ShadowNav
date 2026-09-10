"""Run a comparator over the published S-side split.

``--method naive`` produces the drift floor. Every later claim -- learned
front end, nonholonomic constraint, centripetal loss -- is measured against
these numbers, so they are committed to ``eval/results/baseline_naive.json``
rather than printed and forgotten.

The other three methods are the comparators a judge will actually ask about,
scored through the identical harness so the comparison is like-for-like:

    freeze   leave the dot at the last fix
    cv       hold the last GNSS speed and course, straight line, no IMU
    gyro     hold speed, integrate heading from the gyroscope, no filter

Run:  PYTHONPATH=. python scripts/run_baseline.py [--method M] [--fold test] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav import geo  # noqa: E402
from shadownav.baselines import constant_velocity, freeze, gyro_heading, naive  # noqa: E402
from shadownav.data import fetch, iovnbd  # noqa: E402
from shadownav.evaluation import masking, metrics, splits  # noqa: E402
from shadownav.utils.seed import seed_everything  # noqa: E402

Estimator = Callable[..., naive.DeadReckonResult]

#: cli name -> (estimator, method label, result stem, note)
METHODS: dict[str, tuple[Estimator, str, str, str]] = {
    "naive": (
        naive.dead_reckon, "naive_strapdown", "baseline_naive",
        "Unaided strapdown INS: attitude from gyroscope integration, "
        "gravity removed analytically, acceleration double-integrated. "
        "No ZUPT, no nonholonomic constraint, no learned correction, "
        "no map. Accelerometer and gyroscope only. This is the drift "
        "floor every later claim is measured against.",
    ),
    "freeze": (
        freeze.dead_reckon, "freeze_last_fix", "baseline_freeze",
        "Leave the position at the last GNSS fix for the whole outage. Its "
        "error is the vehicle's displacement, so an estimator whose error "
        "exceeds the distance driven is worse than doing nothing.",
    ),
    "cv": (
        constant_velocity.dead_reckon, "constant_velocity", "baseline_cv",
        "Hold the last GNSS speed and course and extrapolate in a straight "
        "line. Uses no inertial sensor; what a map app does for the first "
        "seconds of a tunnel.",
    ),
    "gyro": (
        gyro_heading.dead_reckon, "gyro_heading_hold", "baseline_gyro",
        "Hold the last GNSS speed; integrate heading from the gyroscope's "
        "component about the vehicle's vertical. No bias state, no "
        "nonholonomic constraint, no Ackermann bound, no filter.",
    ),
}


def _initial_conditions(seq: iovnbd.Sequence, row: int, true_e, true_n) -> tuple[float, float]:
    """Speed and course immediately before the outage, from GNSS.

    Legitimate: the outage is what is being simulated, and GNSS is present right
    up to its start. Course prefers the receiver's own reading and falls back to
    the track between distinct fixes, since the receiver course can be stale for
    up to one 9 s fix period.
    """
    speed = float(seq.df["gps_speed_ms"].iloc[row])
    course_deg = seq.df["gps_orientation_deg"].iloc[row]
    if np.isfinite(course_deg):
        return speed, math.radians(float(course_deg))
    return speed, float(geo.heading_from_track(true_e, true_n)[row])


def evaluate_sequence(
    seq: iovnbd.Sequence,
    split: splits.Split,
    estimator: Estimator = naive.dead_reckon,
    method: str = "naive_strapdown",
) -> list[metrics.OutageResult]:
    true_e, true_n = geo.lla_to_enu(
        seq.df["gps_lat_deg"].to_numpy(), seq.df["gps_lon_deg"].to_numpy()
    )
    fix_rows = np.flatnonzero(seq.df["gps_fix_is_new"].to_numpy())
    out: list[metrics.OutageResult] = []

    for horizon in split.horizons_s:
        windows = masking.plan_outages(
            seq, horizon,
            n=split.outages_per_sequence,
            seed=split.seed,
            min_speed_ms=split.min_speed_ms,
            guard_s=split.guard_s,
        )
        for w in windows:
            if not w.informative:
                continue  # hid no real fix; a test of interpolation, not of DR
            # Integrate a generous margin past the horizon so a real fix can be
            # found even when the next one is up to a fix period away.
            end_row = min(len(seq) - 1, w.start_row + int(horizon * 10) + 150)
            if end_row <= w.start_row + 2:
                continue

            speed0, course0 = _initial_conditions(seq, w.start_row, true_e, true_n)
            if not np.isfinite(speed0) or not np.isfinite(course0):
                continue

            dr = estimator(
                seq, w.start_row, end_row,
                init_speed_ms=speed0, init_heading_rad=course0,
            )
            est_e = np.full(len(seq), np.nan)
            est_n = np.full(len(seq), np.nan)
            span = slice(w.start_row, end_row + 1)
            est_e[span] = true_e[w.start_row] + dr.east_m
            est_n[span] = true_n[w.start_row] + dr.north_m

            usable = fix_rows[(fix_rows >= w.start_row) & (fix_rows <= end_row)]
            res = metrics.evaluate_window(
                sequence=seq.name, method=method, horizon_s=horizon,
                time_s=seq.time_s, est_e=est_e, est_n=est_n,
                true_e=true_e, true_n=true_n,
                fix_rows=usable, start_row=w.start_row,
                distance_m=w.distance_m, n_fixes_suppressed=w.n_fixes_suppressed,
            )
            if res is not None and np.isfinite(res.crse_m):
                out.append(res)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--method", default="naive", choices=sorted(METHODS))
    ap.add_argument("--fold", default="all", choices=["all", "train", "val", "test"])
    ap.add_argument("--limit", type=int, default=None, help="cap sequences, for a smoke run")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    estimator, method, stem, note = METHODS[args.method]
    seed_everything()
    split = splits.load_split()
    data_dir = fetch.default_data_dir() / "iovnbd" / "S"
    paths = sorted(data_dir.glob("S-*.csv"))
    if not paths:
        print(f"no data in {data_dir}; run: python -m shadownav.data.fetch")
        return 1

    results: list[metrics.OutageResult] = []
    per_fold: dict[str, list[metrics.OutageResult]] = defaultdict(list)
    n_seq = 0
    skipped: list[str] = []

    for path in paths:
        try:
            sessions = iovnbd.load_s_sessions(path)
        except iovnbd.IOVNBDError as exc:
            skipped.append(f"{path.stem}: {exc}")
            continue
        for seq in sessions:
            fold = split.fold_of(seq.name)
            if args.fold != "all" and fold != args.fold:
                continue
            if args.limit is not None and n_seq >= args.limit:
                break
            n_seq += 1
            rs = evaluate_sequence(seq, split, estimator, method)
            results.extend(rs)
            per_fold[fold].extend(rs)

    if not results:
        print("no evaluable outages produced")
        return 1

    print(f"sequences evaluated: {n_seq}   outages scored: {len(results)}")
    if skipped:
        print(f"skipped: {len(skipped)}")
        for s in skipped[:5]:
            print(f"  {s}")

    print(f"\n{method.upper()} -- {note.split('.')[0]}")
    print(f"{'horizon':>8} {'n':>5} {'t_eval':>7} {'CRSE med':>10} {'CRSE p90':>10} "
          f"{'CTE med':>9} {'drift med':>10} {'truth gap':>10}")
    summary = metrics.summarise(results)
    for h, s in summary.items():
        print(f"{h:>8.0f} {s['n']:>5.0f} {s['t_eval_median_s']:>7.1f} "
              f"{s['crse_median_m']:>10.1f} {s['crse_p90_m']:>10.1f} "
              f"{s['cte_median_m']:>9.1f} {s['drift_median_pct']:>9.1f}% "
              f"{s['truth_gap_median_m']:>9.1f}")

    print("\nper fold, CRSE median (m):")
    for fold in ("train", "val", "test"):
        if not per_fold[fold]:
            continue
        fs = metrics.summarise(per_fold[fold])
        line = "  ".join(f"{h:.0f}s={v['crse_median_m']:.0f}" for h, v in fs.items())
        print(f"  {fold:<6} {line}")

    out = args.out or (
        Path(__file__).resolve().parents[2] / "eval" / "results" / f"{stem}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "method": method,
                "note": note,
                "seed": split.seed,
                "n_sequences": n_seq,
                "n_outages": len(results),
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
