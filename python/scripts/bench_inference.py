"""Measure speed-net inference latency against the low-end budget.

The target-hardware decision sets 30 ms per 10 Hz update on a low-end Android
phone (research/SIH26168-external-review-response.md section 4). This measures
the Python/PyTorch float32 path pinned to **one thread**, which is the closest
honest proxy available without the device: a low-end phone core is roughly 3-5x
slower than a desktop core, and INT8 on XNNPACK is faster than float32, so the
two corrections push in opposite directions.

This is a proxy, not the real measurement. The real one is Phase E on hardware.
Do not quote this as an on-device number.

Run:  PYTHONPATH=. python scripts/bench_inference.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav.models.inference import DEFAULT_MODEL, SpeedNetEstimator  # noqa: E402

BUDGET_MS = 30.0
UPDATE_PERIOD_MS = 100.0     # 10 Hz
LOW_END_SLOWDOWN = 5.0       # pessimistic desktop-core to phone-core factor


def main() -> int:
    if not Path(DEFAULT_MODEL).exists():
        print(f"no trained model at {DEFAULT_MODEL}; run scripts/train_speednet.py")
        return 1

    torch.set_num_threads(1)
    est = SpeedNetEstimator()
    rng = np.random.default_rng(0)
    acc = rng.normal(0, 0.3, (est.window, 3)) + np.array([0.0, 0.0, 9.81])
    gyr = rng.normal(0, 0.05, (est.window, 3))
    est.set_gravity(acc)

    for _ in range(20):
        est(acc, gyr)

    samples = []
    for _ in range(500):
        t0 = time.perf_counter()
        est(acc, gyr)
        samples.append((time.perf_counter() - t0) * 1000.0)
    t = np.array(samples)

    median, p95 = float(np.median(t)), float(np.percentile(t, 95))
    size_mb = Path(DEFAULT_MODEL).stat().st_size / 1e6

    print(f"model              : {est.variant} variant, "
          f"{est.model.n_parameters:,} params, {size_mb:.2f} MB on disk")
    print(f"threads            : 1")
    print(f"latency            : median {median:.2f} ms  p95 {p95:.2f} ms  "
          f"max {t.max():.2f} ms")
    print(f"share of 10 Hz slot: {100 * median / UPDATE_PERIOD_MS:.1f}%")
    print(f"budget {BUDGET_MS:.0f} ms      : "
          f"{'PASS' if p95 < BUDGET_MS else 'FAIL'} on this core")
    projected = p95 * LOW_END_SLOWDOWN
    print(f"projected low-end  : ~{projected:.1f} ms p95 at {LOW_END_SLOWDOWN:.0f}x "
          f"slowdown -> {'PASS' if projected < BUDGET_MS else 'AT RISK'}")
    print("\nProxy only. The real number is Phase E, on the device.")

    out = Path(__file__).resolve().parents[2] / "eval" / "results" / "inference_latency.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "note": (
                    "Desktop CPU, single thread, float32 PyTorch. A proxy for a "
                    "low-end phone core, not an on-device measurement."
                ),
                "variant": est.variant,
                "n_parameters": est.model.n_parameters,
                "checkpoint_mb": size_mb,
                "threads": 1,
                "median_ms": median,
                "p95_ms": p95,
                "max_ms": float(t.max()),
                "budget_ms": BUDGET_MS,
                "projected_low_end_p95_ms": projected,
                "low_end_slowdown_assumed": LOW_END_SLOWDOWN,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
