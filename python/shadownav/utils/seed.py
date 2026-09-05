"""Determinism controls.

The reproducibility gate is cheap now and expensive to retrofit, so it goes in
with Phase 0 rather than after Phase 2. Every stochastic component in this
project draws from a generator obtained here, never from module-level
``np.random`` state, so a run is reproducible from its seed alone regardless of
import order or test interleaving.
"""

from __future__ import annotations

import os
import random

import numpy as np

#: Project-wide default. Matches the seed shown in the presentation demo header
#: (demo/gnss-demo.html) so a demo run and an offline run are traceable to the
#: same number.
DEFAULT_SEED = 20260905


def rng(seed: int | None = None) -> np.random.Generator:
    """Return an independent generator. Prefer this over ``np.random.*``."""
    return np.random.default_rng(DEFAULT_SEED if seed is None else seed)


def seed_everything(seed: int = DEFAULT_SEED) -> int:
    """Seed every global RNG we might touch, including torch if it is present.

    torch is imported lazily: the data and evaluation layers must stay usable
    without it installed, which also keeps the Phase 0 test suite fast.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    try:  # pragma: no cover - exercised only when torch is installed
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.use_deterministic_algorithms(True, warn_only=True)
    except ImportError:
        pass
    return seed
