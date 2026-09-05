"""Load and apply the published S-side split.

The split is data, not code: it lives in ``eval/splits/shadownav_s_split.yaml``
so it can be cited in a writeup and diffed in review. This module only reads it
and answers "which group does this sequence belong to".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_GROUP_RE = re.compile(r"^S-([A-Za-z]+)")


def default_split_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "eval" / "splits" / "shadownav_s_split.yaml"
    )


class SplitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Split:
    """The published train/val/test partition, keyed by sequence group."""

    groups: dict[str, tuple[str, ...]]
    horizons_s: tuple[float, ...]
    outages_per_sequence: int
    seed: int
    min_speed_ms: float
    guard_s: float

    def group_of(self, sequence_name: str) -> str:
        """Route/driver group for a sequence name such as ``S-Vta10#1``."""
        m = _GROUP_RE.match(sequence_name)
        if not m:
            raise SplitError(f"cannot derive a group from {sequence_name!r}")
        return m.group(1)

    def fold_of(self, sequence_name: str) -> str:
        """Which fold a sequence belongs to: train, val or test."""
        group = self.group_of(sequence_name)
        for fold, members in self.groups.items():
            if group in members:
                return fold
        raise SplitError(
            f"group {group!r} (from {sequence_name!r}) is in no fold. "
            f"Every sequence must be assigned explicitly -- an unassigned "
            f"sequence silently leaking into training is exactly what this "
            f"file exists to prevent."
        )

    def filter(self, names: list[str], fold: str) -> list[str]:
        return [n for n in names if self.fold_of(n) == fold]


@lru_cache(maxsize=4)
def load_split(path: str | Path | None = None) -> Split:
    path = Path(path) if path else default_split_path()
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    proto = doc["protocol"]
    return Split(
        groups={k: tuple(v) for k, v in doc["groups"].items()},
        horizons_s=tuple(float(h) for h in proto["horizons_s"]),
        outages_per_sequence=int(proto["outages_per_sequence"]),
        seed=int(proto["seed"]),
        min_speed_ms=float(proto["min_speed_ms"]),
        guard_s=float(proto["guard_s"]),
    )
