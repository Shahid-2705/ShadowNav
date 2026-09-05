"""One real IO-VNBD outage, plotted from the same code path the evaluation uses.

Reproduces the committed row for S-Vw6 at the 60 s horizon in
eval/results/kinematic.json (538 m path, 154 m error) and draws the hidden
ground-truth fixes, the ShadowNav track, the naive strapdown, and the
conformal-inflated 90 % region. Requires the dataset (python -m shadownav.data.fetch).

Run from the repository root:

    PYTHONPATH=python python submission/figures/make_traj_figure.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from shadownav import geo, pipeline_kinematic as pipeline  # noqa: E402
from shadownav.baselines import naive  # noqa: E402
from shadownav.data import fetch, iovnbd  # noqa: E402
from shadownav.evaluation import masking, splits  # noqa: E402
from shadownav.utils.seed import seed_everything  # noqa: E402

OUT = Path(__file__).resolve().parent
NAME = "S-Vw6"
HORIZON_S = 60.0
NAVY, BLUE, RED = "#1F497D", "#0070C0", "#C0504D"


def main() -> None:
    seed_everything()
    split = splits.load_split()
    cfg = pipeline.KinematicPipelineConfig()
    path = fetch.default_data_dir() / "iovnbd" / "S" / f"{NAME}.csv"
    seq = next(s for s in iovnbd.load_s_sessions(path) if s.name == NAME)
    ref_lat, ref_lon = pipeline.enu_reference(seq)
    te, tn = geo.lla_to_enu(seq.df["gps_lat_deg"].to_numpy(), seq.df["gps_lon_deg"].to_numpy(),
                            ref_lat, ref_lon)
    fix_rows = np.flatnonzero(seq.df["gps_fix_is_new"].to_numpy())

    # Same planner call as scripts/run_mvp.py; this drive has one informative 60 s window.
    windows = masking.plan_outages(seq, HORIZON_S, n=split.outages_per_sequence, seed=split.seed,
                                   min_speed_ms=split.min_speed_ms, guard_s=split.guard_s)
    w = next(w for w in windows if w.informative)
    end_row = min(len(seq) - 1, w.start_row + int(HORIZON_S * 10) + 150)
    warm = max(0, w.start_row - 300)
    traj = pipeline.run(masking.apply_mask(seq, w), config=cfg, start_row=warm, end_row=end_row)

    speed0 = float(seq.df["gps_speed_ms"].iloc[w.start_row])
    course = seq.df["gps_orientation_deg"].iloc[w.start_row]
    course0 = (math.radians(float(course)) if np.isfinite(course)
               else float(geo.heading_from_track(te, tn)[w.start_row]))
    dr = naive.dead_reckon(seq, w.start_row, end_row, init_speed_ms=speed0, init_heading_rad=course0)
    ne, nn = te[w.start_row] + dr.east_m, tn[w.start_row] + dr.north_m

    fr_in = fix_rows[(fix_rows >= w.start_row) & (fix_rows <= w.end_row)]
    fr_after = fix_rows[(fix_rows > w.end_row) & (fix_rows <= end_row)]
    r_eval = int(fr_after[0]) if len(fr_after) else end_row
    i = r_eval - warm
    err_ours = math.hypot(traj.east_m[i] - te[r_eval], traj.north_m[i] - tn[r_eval])
    err_naive = math.hypot(ne[r_eval - w.start_row] - te[r_eval], nn[r_eval - w.start_row] - tn[r_eval])
    span = fix_rows[(fix_rows >= w.start_row) & (fix_rows <= r_eval)]
    path_m = float(np.sum(np.hypot(np.diff(te[span]), np.diff(tn[span]))))

    lam = json.loads((ROOT / "eval" / "results" / "conformal_calibration.json").read_text())
    lam = lam["calibration"]["factors"][f"{HORIZON_S}"]
    cov = traj.cov_xy[i] * lam
    vals, vecs = np.linalg.eigh(cov)
    k = math.sqrt(-2 * math.log(0.1))
    ang = math.degrees(math.atan2(vecs[1, 1], vecs[0, 1]))

    fig, ax = plt.subplots(figsize=(6.0, 4.5), dpi=220)
    ax.plot(te[warm:w.start_row + 1], tn[warm:w.start_row + 1], color="#B8C2CC", lw=2.2,
            label="GNSS track before the cut")
    ax.plot(te[fr_in], tn[fr_in], "o", color="black", ms=3.4, label="hidden GNSS fixes (ground truth)")
    o0, o1 = w.start_row - warm, w.end_row - warm
    ax.plot(traj.east_m[o0:o1 + 1], traj.north_m[o0:o1 + 1], color=BLUE, lw=2.6,
            label="ShadowNav, no GNSS for 60 s")
    ax.plot(ne[:w.end_row - w.start_row + 1], nn[:w.end_row - w.start_row + 1], color=RED, lw=1.4,
            ls="--", label="naive strapdown (runs off-chart)")
    ax.add_patch(Ellipse((traj.east_m[i], traj.north_m[i]), 2 * k * math.sqrt(vals[1]),
                         2 * k * math.sqrt(vals[0]), angle=ang, fc=BLUE, alpha=0.12, ec=BLUE,
                         lw=1.2, ls="--", label="calibrated 90 % region"))
    ax.plot(te[w.start_row], tn[w.start_row], "s", color=NAVY, ms=7)
    ax.annotate("GPS cut", (te[w.start_row], tn[w.start_row]), xytext=(8, -14),
                textcoords="offset points", fontsize=8.5, color=NAVY, fontweight="bold")
    ax.plot(te[r_eval], tn[r_eval], "^", color="black", ms=7)
    ax.annotate("first fix back", (te[r_eval], tn[r_eval]), xytext=(8, 4),
                textcoords="offset points", fontsize=8.5, fontweight="bold")
    ax.set_aspect("equal")
    ax.set_xlabel("east (m)")
    ax.set_ylabel("north (m)")
    xs = np.r_[te[warm:r_eval + 1], traj.east_m[:i + 1]]
    ys = np.r_[tn[warm:r_eval + 1], traj.north_m[:i + 1]]
    pad = 100
    ax.set_xlim(np.nanmin(xs) - pad, np.nanmax(xs) + pad)
    ax.set_ylim(np.nanmin(ys) - pad, np.nanmax(ys) + pad)
    ax.set_title(f"Real drive (IO-VNBD {NAME}): GPS cut for 60 s, {path_m:,.0f} m travelled\n"
                 f"error at first fix back: ShadowNav {err_ours:,.0f} m, "
                 f"naive strapdown {err_naive / 1000:,.1f} km",
                 fontsize=9.3, loc="left", color=NAVY)
    ax.legend(fontsize=7.6, frameon=False, loc="best")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "fig_traj.png")
    (OUT / "fig_traj.json").write_text(json.dumps({
        "sequence": NAME, "horizon_s": HORIZON_S, "distance_m": path_m,
        "t_eval_s": float(seq.time_s[r_eval] - w.start_s), "err_ours_m": err_ours,
        "err_naive_m": err_naive, "lambda_60": lam, "start_s": w.start_s,
    }, indent=1))
    print(f"{NAME}: path {path_m:.0f} m, ShadowNav {err_ours:.0f} m, naive {err_naive:.0f} m")


if __name__ == "__main__":
    main()
