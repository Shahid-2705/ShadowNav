"""CNN+GRU forward-speed network with GNIO's Motion Bank and gated head.

Architecture lineage
--------------------
The convolutional front end and GRU follow DeepOdo/DeepOri, which AVNet is
built from and which the dossier verified directly from the authors' released
code (research section 1.1). The Motion Bank and gated prediction head follow
GNIO (research section 1.2), whose ablation reports 17.5% from the bank alone,
23.3% from the gate alone, and 30.8% from both.

Everything is scaled down deliberately. GNIO uses 64 prototypes of 512
dimensions on a ResNet-18 backbone; the target here is a low-end Android phone
with a binding budget of 5 MB INT8 and 30 ms per 10 Hz update
(research/SIH26168-external-review-response.md section 4). This model is about
118k parameters, roughly 470 KB in float32.

One deliberate departure from GNIO
----------------------------------
GNIO gates a **signed displacement vector** and its Table IV shows Tanh beating
Sigmoid for that. Forward speed is a **non-negative scalar**, so a [-1, 1] gate
is the wrong shape: it can only reach zero by cancelling against the magnitude
branch. The natural analogue for a magnitude is a [0, 1] gate, so this uses
Sigmoid and keeps the property that actually matters -- the gate can drive the
output smoothly to zero, giving a differentiable zero-velocity update rather
than a hard threshold. Both are selectable so the choice can be measured rather
than asserted.

Uncertainty
-----------
The head emits a mean and a log-variance and is trained with Gaussian NLL, the
two-stage strategy TLIO uses and GNIO adopts. That variance is not decoration:
it becomes the measurement noise R the filter uses for this pseudo-measurement,
so a network that knows it is guessing widens the filter's gate instead of
dragging the estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import torch
import torch.nn as nn
import torch.nn.functional as F

from .features import N_CHANNELS


@dataclass(frozen=True)
class SpeedNetConfig:
    in_channels: int = N_CHANNELS
    window: int = 64
    conv1_out: int = 48
    conv2_out: int = 96
    hidden: int = 96
    bank_size: int = 32          # GNIO sweeps 16/32/64/128 and finds 64 best at
                                 # D=512; scaled down with the hidden width here
    n_heads: int = 4
    use_motion_bank: bool = True
    use_gate: bool = True
    gate_activation: str = "sigmoid"   # "sigmoid" for a magnitude, "tanh" per GNIO
    dropout: float = 0.1

    def as_dict(self) -> dict:
        return asdict(self)


class MotionBank(nn.Module):
    """Learned prototypes of motion, queried by multi-head attention.

    The current feature is the query; the bank is both keys and values. In
    effect: "which of the motions I have seen before does this window resemble".
    A sliding-window convolution has no such long-range memory, which is GNIO's
    stated reason for adding it.
    """

    def __init__(self, size: int, dim: int, n_heads: int) -> None:
        super().__init__()
        self.bank = nn.Parameter(torch.randn(size, dim) * 0.02)
        self.attention = nn.MultiheadAttention(
            embed_dim=dim, num_heads=n_heads, batch_first=True
        )

    def forward(self, feat: torch.Tensor) -> torch.Tensor:
        # (B, D) -> (B, 1, D) query against the shared bank.
        query = feat.unsqueeze(1)
        bank = self.bank.unsqueeze(0).expand(feat.shape[0], -1, -1)
        context, _ = self.attention(query, bank, bank, need_weights=False)
        return feat + context.squeeze(1)      # residual fusion, as in GNIO


class SpeedNet(nn.Module):
    """Window of invariant IMU features -> (speed, log variance)."""

    def __init__(self, config: SpeedNetConfig | None = None) -> None:
        super().__init__()
        cfg = config or SpeedNetConfig()
        self.config = cfg

        self.conv = nn.Sequential(
            nn.Conv1d(cfg.in_channels, cfg.conv1_out, kernel_size=7, padding=3),
            nn.BatchNorm1d(cfg.conv1_out),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(2),
            nn.Conv1d(cfg.conv1_out, cfg.conv2_out, kernel_size=5, padding=2),
            nn.BatchNorm1d(cfg.conv2_out),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(2),
        )
        self.gru = nn.GRU(cfg.conv2_out, cfg.hidden, batch_first=True)
        self.bank = (
            MotionBank(cfg.bank_size, cfg.hidden, cfg.n_heads)
            if cfg.use_motion_bank else None
        )
        self.dropout = nn.Dropout(cfg.dropout)
        self.trunk = nn.Sequential(
            nn.Linear(cfg.hidden, 64), nn.ReLU(inplace=True)
        )
        self.magnitude = nn.Linear(64, 1)
        self.gate = nn.Linear(64, 1) if cfg.use_gate else None
        self.log_var = nn.Linear(64, 1)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """``x`` is ``(B, window, channels)``."""
        h = self.conv(x.transpose(1, 2)).transpose(1, 2)
        out, _ = self.gru(h)
        feat = out[:, -1, :]                   # causal: last step only
        if self.bank is not None:
            feat = self.bank(feat)
        feat = self.trunk(self.dropout(feat))

        magnitude = F.softplus(self.magnitude(feat)).squeeze(-1)
        if self.gate is not None:
            raw = self.gate(feat).squeeze(-1)
            gate = (torch.sigmoid(raw) if self.config.gate_activation == "sigmoid"
                    else torch.tanh(raw))
            speed = magnitude * gate
        else:
            speed = magnitude
        # Bounded so a diverging head cannot emit an absurd sigma the filter
        # would then trust or ignore entirely.
        log_var = self.log_var(feat).squeeze(-1).clamp(-6.0, 6.0)
        return speed, log_var

    @property
    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())


def gaussian_nll(pred: torch.Tensor, log_var: torch.Tensor,
                 target: torch.Tensor) -> torch.Tensor:
    """Heteroscedastic loss. Lets the network say when it does not know."""
    return (0.5 * (torch.exp(-log_var) * (target - pred) ** 2 + log_var)).mean()


def mse(pred: torch.Tensor, _log_var: torch.Tensor,
        target: torch.Tensor) -> torch.Tensor:
    """Stage-one loss. Training NLL from scratch lets the model escape by
    predicting a huge variance instead of learning the mean."""
    return F.mse_loss(pred, target)
