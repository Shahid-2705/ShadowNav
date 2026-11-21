"""One table across every committed result in eval/results/.

Reads whatever is present rather than re-running anything, so it is cheap and
always reflects the last committed numbers.

Run:  PYTHONPATH=. python scripts/summarise_results.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav.evaluation import compare  # noqa: E402

RESULTS = Path(__file__).resolve().parents[2] / "eval" / "results"

#: file stem -> (label, whether it is an ablation rather than a headline config)
KNOWN = {
    "baseline_naive": ("naive strapdown (floor)", False),
    "baseline_freeze": ("freeze last fix", False),
    "baseline_cv": ("constant velocity (no IMU)", False),
    "baseline_gyro": ("speed hold + gyro heading", False),
    "kinematic": ("kinematic MVP", False),
    "kinematic_ctrl8": ("kinematic (8-seq control)", False),
    "kinematic_speednet": ("kinematic + speed net (8-seq)", False),
    "kinematic_maphead": ("  map heading constraint: ON", True),
    "kinematic_maphead_off": ("  map heading constraint: OFF", True),
    "kinematic_no_ack": ("  ablation: no Ackermann", True),
    "kinematic_cent": ("  ablation: + L_cent", True),
    "kinematic_accel": ("  ablation: + accel speed", True),
    "kinematic_cent_accel": ("  ablation: + both", True),
    "kinematic_no_cent_no_accel": ("  (superseded run)", True),
    "kinematic_no_cent": ("  (superseded run)", True),
    "kinematic_no_accel": ("  (superseded run)", True),
    "ekf_nhc": ("  (superseded: 21-state strapdown)", True),
}

HORIZONS = ["10.0", "30.0", "60.0", "120.0", "180.0"]

#: Comparators a judge will ask about, paired per outage against the MVP.
COMPARATORS = ("baseline_freeze", "baseline_cv", "baseline_gyro", "baseline_naive")


def _find(rows, stem_label: str):
    return next((r for r in rows if r[0] == KNOWN[stem_label][0]), None)


def print_fair_comparison(rows) -> None:
    """The PS's 10% target, and paired wins against each comparator."""
    print(f"\nshare of outages under the PS target ({compare.PS_DRIFT_TARGET_PCT:.0f}% of "
          f"distance travelled)\n")
    for label, is_ab, blob, _ in rows:
        if is_ab or "results" not in blob:
            continue
        share = compare.share_under_drift(blob["results"], compare.PS_DRIFT_TARGET_PCT)
        cells = "  ".join(f"{h:.0f}s={100 * v:.1f}%" for h, v in share.items())
        print(f"  {label:<34}{cells}")

    mvp = _find(rows, "kinematic")
    if mvp is None or "results" not in mvp[2]:
        return
    ours = mvp[2]["results"]
    print("\nkinematic MVP vs each comparator, paired on the identical outage\n"
          "  (share of outages the MVP wins; median comparator/MVP error ratio)\n")
    for stem in COMPARATORS:
        row = _find(rows, stem)
        if row is None or "results" not in row[2]:
            continue
        theirs = row[2]["results"]
        wins = compare.share_beating(ours, theirs)
        ratio = compare.paired_median_ratio(ours, theirs)
        n = compare.paired_count(ours, theirs)
        cells = "  ".join(
            f"{h:.0f}s={100 * wins[h]:.0f}% ({ratio[h]:.2f}x, n={n[h]})" for h in wins
        )
        print(f"  vs {row[0]:<31}{cells}")


def print_transitions(rows) -> None:
    """What the PS grades as seamless, plus the ring the app would draw."""
    mvp = _find(rows, "kinematic")
    if mvp is None:
        return
    summary = mvp[3]
    if "reacq_snap_median_m" not in summary.get(HORIZONS[0], {}):
        print("\n(kinematic.json predates the transition metrics; re-run run_mvp.py)")
        return
    print("\nkinematic MVP transitions and the 90% ring (medians)\n")
    print(f"{'horizon':>8} {'detect s':>9} {'snap m':>8} {'max step m':>11} "
          f"{'settle s':>9} {'resid m':>8} {'ring raw m':>11} {'ring cal m':>11}")
    for h in HORIZONS:
        s = summary.get(h)
        if not s:
            continue
        print(f"{float(h):>8.0f} {s['detection_latency_median_s']:>9.2f} "
              f"{s['reacq_snap_median_m']:>8.1f} {s['reacq_max_step_median_m']:>11.1f} "
              f"{s['reacq_settle_median_s']:>9.2f} {s['reacq_residual_median_m']:>8.1f} "
              f"{s['radius90_raw_median_m']:>11.1f} {s['radius90_cal_median_m']:>11.1f}")
    print("  snap = error a naive re-anchor would jump by; max step = largest single-sample\n"
          "  displayed movement beyond the vehicle's own motion within 30 s of the fix;\n"
          "  resid = error at the next real fix after re-acquisition.")


def main() -> int:
    rows = []
    for stem, (label, is_ablation) in KNOWN.items():
        path = RESULTS / f"{stem}.json"
        if not path.exists():
            continue
        blob = json.loads(path.read_text(encoding="utf-8"))
        summary = blob.get("summary", {})
        rows.append((label, is_ablation, blob, summary))

    if not rows:
        print(f"no results in {RESULTS}")
        return 1

    print("CRSE median (m), by outage horizon\n")
    def hlabel(h: str) -> str:
        return f"{float(h):.0f}s"

    head = f"{'method':<36}{'n_seq':>7}" + "".join(f"{hlabel(h):>10}" for h in HORIZONS)
    print(head)
    print("-" * len(head))
    for label, _, blob, summary in rows:
        cells = ""
        for h in HORIZONS:
            v = summary.get(h, {}).get("crse_median_m")
            cells += f"{v:>10.1f}" if v is not None else f"{'-':>10}"
        print(f"{label:<36}{blob.get('n_sequences', 0):>7}{cells}")

    floor_row = next((r for r in rows if "floor" in r[0]), None)
    floor = floor_row[3] if floor_row else None
    floor_n = floor_row[2].get("n_sequences") if floor_row else None
    if floor:
        print("\nimprovement over the naive floor (x better)\n")
        print(head)
        print("-" * len(head))
        for label, is_ab, blob, summary in rows:
            if "floor" in label or is_ab:
                continue
            n = blob.get("n_sequences")
            if n != floor_n:
                # Comparing a ratio across different sequence sets is not a
                # result, it is an artefact. Refuse rather than mislead.
                print(f"{label:<36}{n:>7}   SKIPPED: {n} sequences vs the "
                      f"floor's {floor_n}; re-run both on the same set")
                continue
            cells = ""
            for h in HORIZONS:
                a = floor.get(h, {}).get("crse_median_m")
                b = summary.get(h, {}).get("crse_median_m")
                cells += f"{a / b:>9.1f}x" if a and b else f"{'-':>10}"
            print(f"{label:<36}{n:>7}{cells}")

    print("\ndrift (% of distance travelled) and median NEES\n")
    for label, is_ab, _, summary in rows:
        if is_ab:
            continue
        d = "  ".join(
            f"{float(h):.0f}s={summary.get(h, {}).get('drift_median_pct', float('nan')):.0f}%"
            for h in HORIZONS if h in summary
        )
        print(f"  {label:<34}{d}")

    print_fair_comparison(rows)
    print_transitions(rows)

    # Reference points, so a reader can place these numbers.
    print("\nreference points (PLAN.md section 5):")
    print("  AVNet, real 578 m / 55 s tunnel, phone IMU only : 0.64% drift")
    print("  PathPulse (SIH competitor), self-reported       : 10.0% mean drift")
    print("  Agastya (SIH competitor), gated policy          : 1.42-1.64 m ATE")
    print("  WhONet @120 s -- uses WHEEL SPEED, not like-for-like : 2.62 m CRSE")

    conformal = RESULTS / "conformal_calibration.json"
    if conformal.exists():
        c = json.loads(conformal.read_text(encoding="utf-8"))
        print(f"\nconfidence: mean containment {c['mean_coverage_raw']:.2f} raw -> "
              f"{c['mean_coverage_calibrated']:.2f} calibrated "
              f"(nominal {c['level']:.2f})")
        print(f"  {c['claim']}")

    latency = RESULTS / "inference_latency.json"
    if latency.exists():
        l = json.loads(latency.read_text(encoding="utf-8"))
        print(f"\nspeed net: {l['n_parameters']:,} params, {l['checkpoint_mb']:.2f} MB, "
              f"{l['median_ms']:.2f} ms median / {l['p95_ms']:.2f} ms p95 (1 thread)")
        print(f"  projected low-end p95 ~{l['projected_low_end_p95_ms']:.1f} ms "
              f"vs {l['budget_ms']:.0f} ms budget -- PROXY, not on-device")

    # Persist summary.md (winnability-plan item A11)
    summary_path = RESULTS / "summary.md"
    try:
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            print("# ShadowNav — Evaluation Summary\n")
            print("```text")
            print(head)
            print("-" * len(head))
            for label, _, blob, sm in rows:
                cells = "".join(
                    f"{sm.get(h, {}).get('crse_median_m', float('nan')):>10.1f}"
                    if sm.get(h, {}).get('crse_median_m') is not None else f"{'-':>10}"
                    for h in HORIZONS
                )
                print(f"{label:<36}{blob.get('n_sequences', 0):>7}{cells}")
            print("```\n")
            print_fair_comparison(rows)
            print_transitions(rows)
        summary_path.write_text(buf.getvalue(), encoding="utf-8")
    except Exception as exc:
        print(f"warning: failed to write {summary_path}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
