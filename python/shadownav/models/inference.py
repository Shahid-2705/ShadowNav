"""Load a trained SpeedNet and expose it as a filter measurement source.

Implements the ``SpeedEstimator`` protocol from ``pipeline_kinematic``: given a
causal window of raw device-frame accelerometer and gyroscope, return
``(speed_ms, sigma_ms)``.

The sigma is the network's own predicted standard deviation and becomes the
measurement noise R for that pseudo-measurement. This is the point of the
Gaussian-NLL head: a network that knows it is guessing widens the filter's gate
instead of dragging the estimate. A model that always returned a fixed sigma
would be no better than a hand-tuned constant.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from .features import gravity_direction, invariant_features
from .speednet import SpeedNet, SpeedNetConfig

DEFAULT_MODEL = Path(__file__).resolve().parents[3] / "shared" / "speednet.pt"


class SpeedNetEstimator:
    """Trained forward-speed front end, ready to hand to the pipeline."""

    def __init__(
        self,
        checkpoint: Path | str | None = None,
        *,
        gravity: np.ndarray | None = None,
        sigma_floor: float = 0.4,
        sigma_ceiling: float = 8.0,
    ) -> None:
        path = Path(checkpoint) if checkpoint else DEFAULT_MODEL
        if not path.exists():
            raise FileNotFoundError(
                f"no trained model at {path}; run scripts/train_speednet.py"
            )
        # weights_only=True refuses to unpickle arbitrary objects. torch.load
        # defaults to False, which is arbitrary code execution on any
        # checkpoint you did not produce yourself.
        blob = torch.load(path, map_location="cpu", weights_only=True)
        self.config = SpeedNetConfig(**blob["config"])
        self.model = SpeedNet(self.config)
        self.model.load_state_dict(blob["state_dict"])
        self.model.eval()

        self.mean = np.asarray(blob["feature_mean"].numpy(), dtype=float)
        self.std = np.asarray(blob["feature_std"].numpy(), dtype=float)
        self.window = int(blob["window"])
        self.variant = blob.get("variant", "unknown")
        # Fixed for a drive: re-estimating gravity per window reintroduces the
        # short-window tilt error documented in baselines/naive.py.
        self.gravity = gravity
        self.sigma_floor = sigma_floor
        self.sigma_ceiling = sigma_ceiling

    def set_gravity(self, acc_history: np.ndarray) -> None:
        """Fix the vertical from a long run of aided data, once per drive."""
        self.gravity = gravity_direction(acc_history)

    @torch.no_grad()
    def __call__(self, window_acc: np.ndarray, window_gyr: np.ndarray) -> tuple[float, float]:
        if len(window_acc) < self.window:
            return float("nan"), float("nan")
        acc = np.asarray(window_acc[-self.window :], dtype=float)
        gyr = np.asarray(window_gyr[-self.window :], dtype=float)
        up = self.gravity if self.gravity is not None else gravity_direction(acc)

        feat = (invariant_features(acc, gyr, up) - self.mean) / self.std
        x = torch.tensor(feat, dtype=torch.float32).unsqueeze(0)
        speed, log_var = self.model(x)
        sigma = float(torch.exp(0.5 * log_var).item())
        return (
            float(speed.item()),
            float(np.clip(sigma, self.sigma_floor, self.sigma_ceiling)),
        )
