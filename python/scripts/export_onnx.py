"""Export the shipped speed net to ONNX for the Android runtime.

What is exported
----------------
The ``full`` variant in ``shared/speednet.pt``, as a single graph

    input  "features" : float32 [1, window, 6]   standardised invariant features
    output "speed"    : float32 [1]              forward speed, m/s
    output "log_var"  : float32 [1]              clamped log-variance

The graph carries **only the network**. Feature construction
(``models/features.py``), standardisation by ``feature_mean`` / ``feature_std``,
the ``sigma_scale`` and the confidence gate (``models/gate.py``) all live
outside it and must be reproduced by the caller; ``shared/README.md`` states the
contract. ``speednet.pt`` remains the authoritative artifact -- the ONNX file
is derived from it and is regenerated, never edited.

Verification
------------
The exported graph is run through onnxruntime on 50 random windows drawn from a
seeded generator and compared against PyTorch; the maximum absolute difference
on both outputs is printed and must be below 1e-4. If ``onnx`` or
``onnxruntime`` is not installed the export still happens and the verification
is reported as "not run", which is the honest state rather than a pass.

Run:  PYTHONPATH=. python scripts/export_onnx.py [--out shared/speednet.onnx]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shadownav.models.features import N_CHANNELS  # noqa: E402
from shadownav.models.inference import DEFAULT_MODEL, SpeedNetEstimator  # noqa: E402
from shadownav.utils.seed import rng, seed_everything  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "shared" / "speednet.onnx"
OPSET = 17
N_VERIFY = 50
TOLERANCE = 1e-4


class _Exportable(torch.nn.Module):
    """Names the two outputs so the graph is self-describing."""

    def __init__(self, net: torch.nn.Module) -> None:
        super().__init__()
        self.net = net

    def forward(self, features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return self.net(features)


def export(est: SpeedNetEstimator, out: Path) -> Path:
    model = _Exportable(est.model).eval()
    example = torch.zeros(1, est.window, N_CHANNELS, dtype=torch.float32)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model, (example,), str(out),
        input_names=["features"], output_names=["speed", "log_var"],
        opset_version=OPSET, dynamo=False, do_constant_folding=True,
    )
    return out


def verify(est: SpeedNetEstimator, onnx_path: Path) -> dict[str, float | str]:
    """Compare onnxruntime against PyTorch on seeded random windows."""
    try:
        import onnx
        import onnxruntime as ort
    except ImportError as exc:                        # pragma: no cover
        return {"status": "not run", "reason": f"missing {exc.name}"}

    onnx.checker.check_model(str(onnx_path))
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    g = rng()
    max_speed = max_logvar = 0.0
    with torch.no_grad():
        for _ in range(N_VERIFY):
            x = g.normal(0.0, 1.0, (1, est.window, N_CHANNELS)).astype(np.float32)
            ref_speed, ref_logvar = est.model(torch.from_numpy(x))
            got_speed, got_logvar = sess.run(None, {"features": x})
            max_speed = max(max_speed, float(np.abs(got_speed - ref_speed.numpy()).max()))
            max_logvar = max(max_logvar, float(np.abs(got_logvar - ref_logvar.numpy()).max()))
    worst = max(max_speed, max_logvar)
    return {
        "status": "pass" if worst < TOLERANCE else "FAIL",
        "max_abs_diff_speed": max_speed,
        "max_abs_diff_log_var": max_logvar,
        "n_windows": N_VERIFY,
        "tolerance": TOLERANCE,
        "onnxruntime": ort.__version__,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    seed_everything()
    est = SpeedNetEstimator(args.checkpoint)
    if est.variant != "full":
        print(f"checkpoint is the {est.variant!r} variant, expected 'full'")
        return 1

    onnx_path = export(est, args.out)
    size_kb = onnx_path.stat().st_size / 1024
    result = verify(est, onnx_path)

    report = {
        "source": str(args.checkpoint.relative_to(ROOT)) if args.checkpoint.is_relative_to(ROOT) else str(args.checkpoint),
        "onnx": str(onnx_path.relative_to(ROOT)) if onnx_path.is_relative_to(ROOT) else str(onnx_path),
        "opset": OPSET,
        "input": {"name": "features", "shape": [1, est.window, N_CHANNELS], "dtype": "float32"},
        "outputs": ["speed", "log_var"],
        "size_bytes": onnx_path.stat().st_size,
        "sigma_scale": est.sigma_scale,
        "feature_mean": est.mean.tolist(),
        "feature_std": est.std.tolist(),
        "verification": result,
    }
    print(f"exported {onnx_path}  ({size_kb:.1f} KB, opset {OPSET}, "
          f"input [1, {est.window}, {N_CHANNELS}])")
    print(f"verification vs PyTorch on {N_VERIFY} windows: {result['status']}"
          + (f"  max|diff| speed {result['max_abs_diff_speed']:.2e}, "
             f"log_var {result['max_abs_diff_log_var']:.2e}"
             if "max_abs_diff_speed" in result else f"  ({result.get('reason')})"))

    sidecar = onnx_path.with_suffix(".onnx.json")
    sidecar.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {sidecar}")
    return 0 if result["status"] != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
