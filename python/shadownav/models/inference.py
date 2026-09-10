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
from .gate import GateConfig, GatedSpeed
from .speednet import SpeedNet, SpeedNetConfig

DEFAULT_MODEL = Path(__file__).resolve().parents[3] / "shared" / "speednet.pt"


class SpeedNetEstimator:
    """Trained forward-speed front end, ready to hand to the pipeline.

    Loads either a single-model checkpoint (``state_dict``) or a seed-ensemble
    checkpoint (``state_dicts``, a list -- see ``scripts/train_speednet_ensemble.py``).
    An ensemble's members are averaged with Gaussian-mixture moment matching
    (mean of means; variance = mean of variances + variance of means), which is
    what makes disagreement between members show up as *higher* reported sigma
    rather than silently cancelling out.
    """

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
        if "state_dicts" in blob:
            self.models = []
            for sd in blob["state_dicts"]:
                m = SpeedNet(self.config)
                m.load_state_dict(sd)
                m.eval()
                self.models.append(m)
            self.model = self.models[0]
        else:
            self.model = SpeedNet(self.config)
            self.model.load_state_dict(blob["state_dict"])
            self.model.eval()
            self.models = [self.model]

        self.mean = np.asarray(blob["feature_mean"].numpy(), dtype=float)
        self.std = np.asarray(blob["feature_std"].numpy(), dtype=float)
        self.window = int(blob["window"])
        self.variant = blob.get("variant", "unknown")
        # Corrects the NLL head's systematic under-dispersion. Fitted on
        # the val fold at training time; 1.0 when absent.
        self.sigma_scale = float(blob.get("sigma_scale", 1.0))
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

        if len(self.models) == 1:
            speed, log_var = self.model(x)
            var = torch.exp(log_var)
        else:
            mus, log_vars = [], []
            for m in self.models:
                mu, lv = m(x)
                mus.append(mu)
                log_vars.append(lv)
            mu_stack = torch.stack(mus, dim=0)
            var_stack = torch.exp(torch.stack(log_vars, dim=0))
            speed = mu_stack.mean(dim=0)
            var = var_stack.mean(dim=0) + ((mu_stack - speed) ** 2).mean(dim=0)

        sigma = float(torch.sqrt(var).item()) * self.sigma_scale
        return (
            float(speed.item()),
            float(np.clip(sigma, self.sigma_floor, self.sigma_ceiling)),
        )


class GatedSpeedNetEstimator:
    """``SpeedNetEstimator`` behind the confidence gate in ``models/gate.py``.

    The wrapped network is unchanged: same checkpoint, same features, same
    val-fitted ``sigma_scale`` (the gate's thresholds are in calibrated m/s,
    so the scale must be applied before the gate sees a sigma, and it is).
    ``set_gravity`` is called once per drive by the evaluation harness and is
    the only per-run hook the pipeline offers, so it also resets the gate's
    prior: a new drive must not inherit the previous one's speed.
    """

    def __init__(
        self,
        checkpoint: Path | str | None = None,
        *,
        gate: GateConfig | None = None,
        gravity: np.ndarray | None = None,
    ) -> None:
        self.net = SpeedNetEstimator(checkpoint, gravity=gravity)
        self.gate = GatedSpeed(self.net, gate)

    @property
    def window(self) -> int:
        return self.net.window

    @property
    def variant(self) -> str:
        return self.net.variant

    @property
    def sigma_scale(self) -> float:
        return self.net.sigma_scale

    @property
    def config(self) -> GateConfig:
        return self.gate.config

    def set_gravity(self, acc_history: np.ndarray) -> None:
        self.net.set_gravity(acc_history)
        self.gate.reset()

    def diagnostics(self) -> dict[str, int]:
        """Accept / reject / shrink counts over every run so far, this one included."""
        return self.gate.totals.merged(self.gate.counts).as_dict()

    def __call__(self, window_acc: np.ndarray, window_gyr: np.ndarray) -> tuple[float, float]:
        return self.gate(window_acc, window_gyr)
