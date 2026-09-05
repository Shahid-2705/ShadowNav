"""Export one representative synthetically-masked outage session for the web MVP.

Blueprint Step 7 (plans/shadownav-3d-mvp-web-deck.md). Reuses run_mvp.py's
exact load -> mask -> run pattern, same split/seed, so this is not a second,
divergent data path -- it is the same pipeline the committed eval/results/
numbers came from, applied to one sequence and exported per-timestep instead
of reduced to summary statistics.

FIX-16: PLAN.md documents that all evaluation uses synthetic masking -- the
dataset's real GPS dropouts have no ground truth and exist only as
exclusions. There is no session with a *real* tunnel outage and real ground
truth through it. This export's outage is a synthetic mask over otherwise-
continuous driving, and the output JSON says so explicitly (`"synthetic":
true`) so the web UI can label it honestly rather than implying a real
dropout.

Run:  PYTHONPATH=. python scripts/export_web_session.py [--horizon 60] [--out ../frontend/public/data/session.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav import geo  # noqa: E402
from shadownav import pipeline_kinematic as pipeline  # noqa: E402
from shadownav.data import fetch, iovnbd  # noqa: E402
from shadownav.evaluation import masking, splits  # noqa: E402
from shadownav.utils.seed import seed_everything  # noqa: E402


def enu_to_lla(east_m: np.ndarray, north_m: np.ndarray, ref_lat_deg: float, ref_lon_deg: float):
    """Exact inverse of geo.lla_to_enu -- geo.py has no inverse of its own."""
    m_rad, n_rad = geo.curvature_radii(ref_lat_deg)
    lat = ref_lat_deg + np.degrees(north_m / m_rad)
    lon = ref_lon_deg + np.degrees(east_m / (n_rad * np.cos(np.radians(ref_lat_deg))))
    return lat, lon


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--horizon", type=float, default=60.0,
                     help="outage duration in seconds (must be one of the split's horizons)")
    ap.add_argument("--fold", default="test", choices=["train", "val", "test", "all"])
    ap.add_argument("--out", type=Path,
                     default=Path(__file__).resolve().parents[2] / "frontend" / "public" / "data" / "session.json")
    args = ap.parse_args(argv)

    seed_everything()
    split = splits.load_split()
    conformal_path = Path(__file__).resolve().parents[2] / "shared" / "conformal.json"
    conformal = json.loads(conformal_path.read_text(encoding="utf-8"))
    lam = float(conformal["factors"][str(float(args.horizon))])

    cfg = pipeline.KinematicPipelineConfig()
    data_dir = fetch.default_data_dir() / "iovnbd" / "S"
    paths = sorted(data_dir.glob("S-*.csv"))
    if not paths:
        print(f"no data in {data_dir}; run: python -m shadownav.data.fetch")
        return 1

    for path in paths:
        try:
            sessions = iovnbd.load_s_sessions(path)
        except iovnbd.IOVNBDError:
            continue
        for seq in sessions:
            fold = split.fold_of(seq.name)
            if args.fold != "all" and fold != args.fold:
                continue

            windows = masking.plan_outages(
                seq, args.horizon, n=split.outages_per_sequence, seed=split.seed,
                min_speed_ms=split.min_speed_ms, guard_s=split.guard_s,
            )
            informative = [w for w in windows if w.informative]
            if not informative:
                continue
            w = informative[0]

            end_row = min(len(seq) - 1, w.start_row + int(args.horizon * 10) + 150)
            if end_row <= w.start_row + 2:
                continue
            warm = max(0, w.start_row - 300)
            masked = masking.apply_mask(seq, w)

            try:
                traj = pipeline.run(masked, config=cfg, start_row=warm, end_row=end_row)
            except (ValueError, np.linalg.LinAlgError):
                continue

            ref_lat, ref_lon = pipeline.enu_reference(seq)
            sl = slice(warm, end_row + 1)
            truth_lat = seq.df["gps_lat_deg"].to_numpy(dtype=float)[sl]
            truth_lon = seq.df["gps_lon_deg"].to_numpy(dtype=float)[sl]
            est_lat, est_lon = enu_to_lla(traj.east_m, traj.north_m, ref_lat, ref_lon)

            sigma_m = np.sqrt(0.5 * (traj.cov_xy[:, 0, 0] + traj.cov_xy[:, 1, 1]))
            radius_90_m = sigma_m * lam * 2.146  # same convention as MainActivity.render() / TrackView

            rows = []
            for i in range(len(traj)):
                rows.append({
                    "t": round(float(traj.time_s[i] - traj.time_s[0]), 2),
                    "mode": str(traj.mode[i]),
                    "estLat": round(float(est_lat[i]), 7),
                    "estLon": round(float(est_lon[i]), 7),
                    "truthLat": round(float(truth_lat[i]), 7) if np.isfinite(truth_lat[i]) else None,
                    "truthLon": round(float(truth_lon[i]), 7) if np.isfinite(truth_lon[i]) else None,
                    "speedMs": round(float(traj.speed_ms[i]), 3),
                    "headingRad": round(float(traj.heading_rad[i]), 4),
                    "radius90m": round(float(radius_90_m[i]), 2) if np.isfinite(radius_90_m[i]) else None,
                })

            export = {
                "synthetic": True,
                "note": ("This outage is a synthetic GNSS mask applied to otherwise-continuous "
                         "driving, not a real tunnel dropout -- PLAN.md documents that the "
                         "dataset's real GPS dropouts have no ground truth and are excluded from "
                         "all evaluation. Ground truth positions here are the recorded GPS fixes, "
                         "held between updates the same way the source data holds them."),
                "session": seq.name,
                "fold": fold,
                "horizonS": args.horizon,
                "outageStartS": round(float(w.start_s), 2),
                "outageDurationS": args.horizon,
                "distanceM": round(float(w.distance_m), 1),
                "conformalLambda": lam,
                "conformalLevel": conformal["level"],
                "refLat": ref_lat,
                "refLon": ref_lon,
                "source": "eval pipeline (shadownav.pipeline_kinematic), same split/seed as eval/results/kinematic.json",
                "rows": rows,
            }

            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(export), encoding="utf-8")
            print(f"exported {seq.name} ({fold}), {len(rows)} rows, "
                  f"outage {w.start_s:.1f}s+{args.horizon:.0f}s, distance {w.distance_m:.0f}m "
                  f"-> {args.out} ({args.out.stat().st_size} bytes)")
            return 0

    print("no informative outage window found in the requested fold")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
