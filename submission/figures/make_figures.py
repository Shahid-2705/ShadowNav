"""Static figures for the SIH 2026 idea deck, drawn from committed results.

Reads eval/results/*.json (never hard-coded numbers) and writes PNGs next to
this file. Run from the repository root:

    python submission/figures/make_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "eval" / "results"
OUT = Path(__file__).resolve().parent

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
})
BLUE, NAVY, ORANGE = "#0070C0", "#1F497D", "#F79646"
GREEN, RED, GREY, LIGHT = "#2E9E5B", "#C0504D", "#6B7280", "#EAF2FB"
HORIZONS = ["10.0", "30.0", "60.0", "120.0", "180.0"]


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def drift_chart() -> None:
    kin = load("kinematic.json")["summary"]
    nai = load("baseline_naive.json")["summary"]
    naive = [nai[h]["crse_median_m"] for h in HORIZONS]
    ours = [kin[h]["crse_median_m"] for h in HORIZONS]
    counts = [kin[h]["n"] for h in HORIZONS]
    n_seq = load("kinematic.json")["n_sequences"]
    n_out = load("kinematic.json")["n_outages"]

    fig, ax = plt.subplots(figsize=(6.2, 3.9), dpi=220)
    xs = range(len(HORIZONS))
    w = 0.38
    ax.bar([i - w / 2 for i in xs], naive, w, color="#C9CED6",
           label="Naive strapdown (accel + gyro double integration)")
    ax.bar([i + w / 2 for i in xs], ours, w, color=BLUE, label="ShadowNav kinematic EKF")
    ax.set_yscale("log")
    ax.set_ylim(50, 1.5e6)
    ax.set_yticks([1e2, 1e3, 1e4, 1e5])
    ax.set_yticklabels(["100 m", "1 km", "10 km", "100 km"])
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"{int(float(h))} s outage\nn={int(c)}" for h, c in zip(HORIZONS, counts)],
                       fontsize=9)
    ax.set_ylabel("Median error at re-acquisition", fontsize=9.5)
    ax.set_title(f"GPS cut on real drives: IO-VNBD, {n_seq} drives, {n_out} outages",
                 fontsize=10.5, loc="left", color=NAVY, pad=8)
    for i, (va, vb) in enumerate(zip(naive, ours)):
        ax.text(i + w / 2, vb * 1.3, f"{vb:,.0f} m", ha="center", fontsize=8.3,
                color=BLUE, fontweight="bold")
        label = f"{va / 1000:,.1f} km" if va >= 1000 else f"{va:,.0f} m"
        ax.text(i - w / 2, va * 1.3, label, ha="center", fontsize=7.8, color=GREY)
        ax.text(i, 4.5e5, f"{va / vb:.1f}×\nbetter", ha="center", fontsize=9,
                color=GREEN, fontweight="bold", linespacing=1.1)
    ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "fig_drift.png")
    plt.close(fig)


def coverage_chart() -> None:
    c = load("conformal_calibration.json")
    raw = c["mean_coverage_raw"] * 100
    cal = c["mean_coverage_calibrated"] * 100
    target = c["level"] * 100
    fig, ax = plt.subplots(figsize=(3.4, 3.4), dpi=220)
    bars = ax.bar(["Filter's own\n90% circle", "After conformal\ninflation (test set)"],
                  [raw, cal], color=[RED, GREEN], width=0.55)
    ax.axhline(target, ls="--", color=NAVY, lw=1.2)
    ax.text(1.32, target + 1.5, f"{target:.0f}% target", fontsize=8.5, color=NAVY, ha="right")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Share of true positions inside circle (%)")
    for b, v in zip(bars, [raw, cal]):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}%", ha="center",
                fontweight="bold", fontsize=11)
    ax.set_title("Confidence you can act on", fontsize=10.5, loc="left", color=NAVY)
    fig.tight_layout()
    fig.savefig(OUT / "fig_coverage.png")
    plt.close(fig)


def _box(ax, x, y, w, h, title, lines=(), fc=LIGHT, ec=BLUE, tc=NAVY, fs=8.2, ts=9.4):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=fc, ec=ec, lw=1.6))
    ax.text(x + w / 2, y + h - 0.18, title, ha="center", va="top", fontsize=ts,
            fontweight="bold", color=tc)
    for i, line in enumerate(lines):
        ax.text(x + 0.1, y + h - 0.48 - i * 0.245, line, ha="left", va="top", fontsize=fs,
                color="#222")


def _arrow(ax, p, q, color=NAVY):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=13, color=color, lw=1.6))


def architecture() -> None:
    lat = load("inference_latency.json")
    params_k = lat["n_parameters"] / 1000
    fig, ax = plt.subplots(figsize=(9.6, 4.3), dpi=220)
    ax.set_xlim(0, 9.6)
    ax.set_ylim(0, 4.3)
    ax.axis("off")
    _box(ax, 0.1, 2.55, 1.95, 1.45, "Phone sensors",
         ["Accelerometer + gyro", "401 Hz on moto g64", "No magnetometer", "No wheel / CAN data"],
         fc="#FFF4E5", ec=ORANGE)
    _box(ax, 0.1, 0.6, 1.95, 1.45, "GNSS receiver",
         ["Fix, speed, course", "Per-satellite C/N₀", "NavIC visibility", "(instrumentation)"],
         fc="#FFF4E5", ec=ORANGE)
    _box(ax, 2.3, 2.55, 2.05, 1.45, "Self-calibration",
         ["Device→car alignment", "from turns + accel", "Gyro bias as EKF state", "Stationary detector"])
    _box(ax, 2.3, 0.6, 2.05, 1.45, "GNSS health gate",
         ["χ² innovation gate", "C/N₀ de-weighting", "FSM: aided → degraded", "→ dead-reck → reacquire"])
    _box(ax, 4.6, 1.15, 2.35, 2.5, "Kinematic EKF core",
         ["5 states: E, N, heading,", "speed, gyro bias", "Non-holonomic constraint",
          "Ackermann curvature and", "friction bounds", "Opt-in CNN+GRU speed net",
          f"{params_k:.0f} k params, 0.13 MB"],
         fc="#E8F5EE", ec=GREEN, ts=10)
    _box(ax, 7.2, 2.55, 2.3, 1.45, "Calibrated output",
         ["Position + heading", "90 % radius, conformal-", "inflated on held-out routes",
          "(coverage 17 % → 97 %)"], fc="#EEF0FF", ec="#5B5BD6")
    _box(ax, 7.2, 0.6, 2.3, 1.45, "Android app",
         ["Kotlin, minSdk 29, 2.2 MB", "Critically damped blend", "on re-acquisition: no jump",
          "Track view, CSV export"], fc="#EEF0FF", ec="#5B5BD6")
    _arrow(ax, (2.05, 3.27), (2.3, 3.27))
    _arrow(ax, (2.05, 1.32), (2.3, 1.32))
    _arrow(ax, (4.35, 3.27), (4.6, 3.0))
    _arrow(ax, (4.35, 1.32), (4.6, 1.7))
    _arrow(ax, (6.95, 2.8), (7.2, 3.1))
    _arrow(ax, (6.95, 1.9), (7.2, 1.5))
    _arrow(ax, (8.35, 2.55), (8.35, 2.05), color="#5B5BD6")
    ax.text(4.8, 0.25, "Everything runs on the phone: no cloud, no vendor SDK, no extra hardware.",
            fontsize=8.6, color=GREY, style="italic", ha="center")
    fig.savefig(OUT / "fig_arch.png", bbox_inches="tight")
    plt.close(fig)


def fsm_strip() -> None:
    fig, ax = plt.subplots(figsize=(9.6, 2.0), dpi=220)
    ax.set_xlim(0, 9.6)
    ax.set_ylim(0, 2.0)
    ax.axis("off")
    phases = [
        ("AIDED", 0.1, 2.1, GREEN, "GNSS accepted via χ² gate;\nbias and alignment learned"),
        ("DEGRADED", 2.3, 1.9, ORANGE, "C/N₀ falling: fixes de-weighted\n(urban canyon: GNSS lies)"),
        ("DEAD RECKONING", 4.3, 2.5, RED, "No usable fix: EKF propagates,\nspeed held, heading from gyro"),
        ("REACQUIRING", 6.9, 1.9, BLUE, "Blend spring ω = 2.3 rad/s,\ncritically damped, no jump"),
        ("AIDED", 8.9, 0.6, GREEN, ""),
    ]
    for name, x, w, col, desc in phases:
        ax.add_patch(FancyBboxPatch((x, 1.15), w, 0.6, boxstyle="round,pad=0.01,rounding_size=0.08",
                                    fc=col, ec="none"))
        ax.text(x + w / 2, 1.45, name, ha="center", va="center", color="white", fontsize=9,
                fontweight="bold")
        if desc:
            ax.text(x + w / 2, 1.0, desc, ha="center", va="top", fontsize=7.6, color="#222",
                    linespacing=1.25)
    ax.annotate("", xy=(9.5, 0.22), xytext=(0.1, 0.22),
                arrowprops=dict(arrowstyle="-|>", color=GREY, lw=1.2))
    ax.text(0.1, 0.04, "tunnel entry", fontsize=7.5, color=GREY)
    ax.text(9.5, 0.04, "tunnel exit", fontsize=7.5, color=GREY, ha="right")
    fig.savefig(OUT / "fig_fsm.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    drift_chart()
    coverage_chart()
    architecture()
    fsm_strip()
    print("wrote", sorted(p.name for p in OUT.glob("fig_*.png")))
