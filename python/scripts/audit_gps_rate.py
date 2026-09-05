"""Measure the real GPS fix rate across every IO-VNBD S-side sequence.

Track H (research/SIH26168-open-track-findings.md) and PLAN.md:149 both state
that the smartphone side samples at 10 Hz with a 1 Hz GPS update, i.e. that GPS
rows repeat in blocks of about 10. Inspecting S-Vta10.csv on 2026-09-05 showed
blocks of 90. This script settles the question over the whole dataset rather
than from one file, because the answer changes the evaluation design:

  * how many independent GPS observations a synthetic outage actually removes
  * whether "ground truth" at 10 Hz is real or interpolated
  * how far the vehicle travels between consecutive truth points

Run:  PYTHONPATH=. python scripts/audit_gps_rate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav.data import fetch, iovnbd  # noqa: E402


def main() -> int:
    data_dir = fetch.default_data_dir() / "iovnbd" / "S"
    paths = sorted(data_dir.glob("S-*.csv"))
    if not paths:
        print(f"no data in {data_dir}; run: python -m shadownav.data.fetch")
        return 1

    rows = []
    for p in paths:
        try:
            sessions = iovnbd.load_s_sessions(p)
        except iovnbd.IOVNBDError as exc:
            rows.append({"name": p.stem, "error": str(exc)})
            continue
        for seq in sessions:
            _record(rows, seq)
    _report(rows)
    return 0


def _record(rows, seq):
        speed = seq.df["gps_speed_ms"].to_numpy()
        rows.append(
            {
                "name": seq.name,
                "rows": len(seq),
                "duration_s": round(seq.duration_s, 1),
                "imu_hz": round(seq.sample_rate_hz, 3),
                "n_fixes": seq.n_unique_gps_fixes,
                "rows_per_fix": round(seq.rows_per_gps_fix, 1),
                "gps_period_s": round(seq.gps_update_period_s, 2),
                "mean_speed_ms": round(float(np.nanmean(speed)), 2),
                "max_speed_ms": round(float(np.nanmax(speed)), 2),
                "gap_m": round(float(np.nanmean(speed)) * seq.gps_update_period_s, 1),
                "repair": seq.repair.summary(),
            }
        )


def _report(rows):

    ok = [r for r in rows if "error" not in r]
    errs = [r for r in rows if "error" in r]

    periods = np.array([r["gps_period_s"] for r in ok], dtype=float)
    periods = periods[np.isfinite(periods)]
    rpf = np.array([r["rows_per_fix"] for r in ok], dtype=float)
    gaps = np.array([r["gap_m"] for r in ok], dtype=float)
    imu = np.array([r["imu_hz"] for r in ok], dtype=float)

    print(f"sequences loaded : {len(ok)} / {len(rows)}")
    if errs:
        print(f"failures         : {len(errs)}")
        for e in errs[:5]:
            print(f"  {e['name']}: {e['error'][:120]}")

    def stat(label: str, a: np.ndarray, unit: str = "") -> None:
        print(
            f"{label:<18}: min {np.nanmin(a):7.2f}  p25 {np.nanpercentile(a, 25):7.2f}  "
            f"median {np.nanmedian(a):7.2f}  p75 {np.nanpercentile(a, 75):7.2f}  "
            f"max {np.nanmax(a):7.2f} {unit}"
        )

    print()
    stat("IMU sample rate", imu, "Hz")
    stat("rows per GPS fix", rpf)
    stat("GPS fix period", periods, "s")
    stat("distance per gap", gaps, "m")

    print()
    print(f"total drive time  : {sum(r['duration_s'] for r in ok) / 3600:.2f} h")
    print(f"total rows        : {sum(r['rows'] for r in ok):,}")
    print(f"total unique fixes: {sum(r['n_fixes'] for r in ok):,}")
    n_1hz = int(np.sum(rpf <= 15))
    print(f"sequences consistent with a 1 Hz GPS update (<=15 rows/fix): {n_1hz}/{len(ok)}")

    n_repaired = sum(1 for r in ok if r.get("repair") != "clean")
    print(f"sessions needing repair: {n_repaired}/{len(ok)}")

    out = Path(__file__).resolve().parents[2] / "eval" / "results" / "gps_rate_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "summary": {
                    "n_sequences": len(ok),
                    "imu_hz_median": float(np.nanmedian(imu)),
                    "rows_per_fix_median": float(np.nanmedian(rpf)),
                    "gps_period_s_median": float(np.nanmedian(periods)),
                    "gps_period_s_min": float(np.nanmin(periods)),
                    "gps_period_s_max": float(np.nanmax(periods)),
                    "distance_per_gap_m_median": float(np.nanmedian(gaps)),
                    "n_consistent_with_1hz": n_1hz,
                    "total_hours": sum(r["duration_s"] for r in ok) / 3600,
                    "total_rows": sum(r["rows"] for r in ok),
                    "total_unique_fixes": sum(r["n_fixes"] for r in ok),
                },
                "sequences": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
