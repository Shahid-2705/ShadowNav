"""Build the speed-regression dataset from IO-VNBD.

One training example per **real** GNSS fix: a causal window of IMU ending at
the fix instant, labelled with the speed the receiver reported there.

Two constraints shape this and both come from measurement, not preference.

* There are only ~14,000 real fixes in the entire dataset, because GPS updates
  every ~9 s (``scripts/audit_gps_rate.py``). Every design choice here is about
  spending that budget well: invariant features, a small model, group-wise
  splitting.
* Labels must come from rows where ``gps_fix_is_new`` is set. The speed column
  is held between fixes, so sampling every row would repeat each label ~90
  times and let the network memorise held values -- inflating validation
  performance while learning nothing transferable.

Windows are strictly causal: they end at the labelled instant and never look
forward, because at deployment nothing is available from the future.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..data import fetch, iovnbd
from ..evaluation import splits
from .features import gravity_direction, invariant_features

#: 64 samples at 10 Hz is 6.4 s -- long enough to contain a full acceleration
#: or braking event, short enough that the vehicle's speed is roughly one
#: regime across it.
DEFAULT_WINDOW = 64


@dataclass(frozen=True)
class SpeedDataset:
    """Feature windows, speed labels, and the group each example came from."""

    x: np.ndarray           # (N, window, 6)
    y: np.ndarray           # (N,) speed in m/s
    groups: np.ndarray      # (N,) sequence names, for leakage checks
    window: int

    def __len__(self) -> int:
        return len(self.y)

    def standardiser(self) -> tuple[np.ndarray, np.ndarray]:
        """Per-channel mean and std, computed on this split only.

        Computing these on the full dataset would leak test statistics into
        training. They are saved with the model because inference must apply
        exactly the same transform.
        """
        flat = self.x.reshape(-1, self.x.shape[-1])
        mean = flat.mean(axis=0)
        std = flat.std(axis=0)
        std[std < 1e-6] = 1.0
        return mean, std

    def standardise(self, mean: np.ndarray, std: np.ndarray) -> "SpeedDataset":
        return SpeedDataset((self.x - mean) / std, self.y, self.groups, self.window)


def windows_from_sequence(
    seq: iovnbd.Sequence, window: int = DEFAULT_WINDOW
) -> tuple[np.ndarray, np.ndarray]:
    """Causal feature windows and speed labels at every real fix in ``seq``."""
    acc = seq.df[["acc_x", "acc_y", "acc_z"]].to_numpy(dtype=float)
    gyr = seq.df[["gyr_x", "gyr_y", "gyr_z"]].to_numpy(dtype=float)
    speed = seq.df["gps_speed_ms"].to_numpy(dtype=float)
    fix_rows = np.flatnonzero(seq.df["gps_fix_is_new"].to_numpy())

    # One gravity direction per sequence: the mounting is fixed for a drive, and
    # estimating it per window would reintroduce the short-window tilt error.
    up = gravity_direction(acc)

    xs: list[np.ndarray] = []
    ys: list[float] = []
    for row in fix_rows:
        if row < window - 1 or not np.isfinite(speed[row]):
            continue
        lo = row - window + 1
        xs.append(invariant_features(acc[lo : row + 1], gyr[lo : row + 1], up))
        ys.append(float(speed[row]))

    if not xs:
        return np.zeros((0, window, 6)), np.zeros(0)
    return np.stack(xs), np.asarray(ys)


def build(
    fold: str,
    *,
    window: int = DEFAULT_WINDOW,
    data_dir: Path | None = None,
    split: splits.Split | None = None,
    limit_sequences: int | None = None,
) -> SpeedDataset:
    """Assemble one fold of the published split."""
    split = split or splits.load_split()
    data_dir = data_dir or (fetch.default_data_dir() / "iovnbd" / "S")
    paths = sorted(data_dir.glob("S-*.csv"))
    if not paths:
        raise FileNotFoundError(
            f"no S-*.csv in {data_dir}; run: python -m shadownav.data.fetch"
        )

    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    gs: list[np.ndarray] = []
    n_seq = 0

    for path in paths:
        try:
            sessions = iovnbd.load_s_sessions(path)
        except iovnbd.IOVNBDError:
            continue
        for seq in sessions:
            if split.fold_of(seq.name) != fold:
                continue
            if limit_sequences is not None and n_seq >= limit_sequences:
                break
            n_seq += 1
            x, y = windows_from_sequence(seq, window)
            if len(y) == 0:
                continue
            xs.append(x)
            ys.append(y)
            gs.append(np.full(len(y), seq.name, dtype=object))

    if not xs:
        return SpeedDataset(np.zeros((0, window, 6)), np.zeros(0),
                            np.zeros(0, dtype=object), window)
    return SpeedDataset(
        np.concatenate(xs), np.concatenate(ys), np.concatenate(gs), window
    )
