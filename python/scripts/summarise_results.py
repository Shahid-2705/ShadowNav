"""One table across every committed result in eval/results/.

Reads whatever is present rather than re-running anything, so it is cheap and
always reflects the last committed numbers.

Run:  PYTHONPATH=. python scripts/summarise_results.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "eval" / "results"

#: file stem -> (label, whether it is an ablation rather than a headline config)
KNOWN = {
    "baseline_naive": ("naive strapdown (floor)", False),
    "kinematic": ("kinematic MVP", False),
    "kinematic_ctrl8": ("kinematic (8-seq control)", False),
    "kinematic_speednet": ("kinematic + speed net (8-seq)", False),
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
