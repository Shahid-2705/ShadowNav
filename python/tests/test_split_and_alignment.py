"""The published split, and the gravity-levelling window selector."""

from __future__ import annotations

import math

import numpy as np
import pytest

from shadownav.baselines import naive
from shadownav.evaluation import splits


# --------------------------------------------------------------------------
# split
# --------------------------------------------------------------------------

def test_split_file_loads():
    s = splits.load_split()
    assert set(s.groups) == {"train", "val", "test"}
    assert s.horizons_s == (10.0, 30.0, 60.0, 120.0, 180.0)
    assert s.seed == 20260905


def test_groups_are_disjoint():
    """Overlap would leak the same road into train and test."""
    s = splits.load_split()
    seen: set[str] = set()
    for members in s.groups.values():
        assert not (seen & set(members)), "a group appears in two folds"
        seen |= set(members)


def test_every_real_group_is_assigned():
    """An unassigned group silently defaulting into training is the failure
    mode this file exists to prevent."""
    s = splits.load_split()
    assigned = {g for members in s.groups.values() for g in members}
    assert assigned == {"Vta", "Vtb", "Vw", "Vfa", "S", "M", "Y"}


@pytest.mark.parametrize(
    "name,fold",
    [
        ("S-Vta10", "train"), ("S-Vtb1", "train"),
        ("S-Vw15", "val"), ("S-Vfa01", "val"),
        ("S-S3a", "test"), ("S-M", "test"), ("S-Y1", "test"),
    ],
)
def test_fold_assignment(name: str, fold: str):
    assert splits.load_split().fold_of(name) == fold


def test_session_suffix_does_not_change_the_fold():
    """Split files yield names like 'S-S2#1'; those must not escape the split."""
    s = splits.load_split()
    assert s.fold_of("S-S2#1") == s.fold_of("S-S2") == "test"


def test_unknown_group_raises_rather_than_defaulting():
    s = splits.load_split()
    with pytest.raises(splits.SplitError, match="no fold"):
        s.fold_of("S-Zzz9")


def test_test_fold_holds_out_whole_drivers():
    """Test is drivers A, B and D; train and val are driver E.

    A random per-sequence split would put near-identical repeats of the same
    route in both, which is the classic way to inflate this benchmark.
    """
    s = splits.load_split()
    assert set(s.groups["test"]) == {"S", "M", "Y"}
    assert not (set(s.groups["train"]) & set(s.groups["test"]))


# --------------------------------------------------------------------------
# alignment window selection
# --------------------------------------------------------------------------

def _acc(n: int, lateral: float) -> np.ndarray:
    a = np.zeros((n, 3))
    a[:, 0] = lateral
    a[:, 2] = naive.GRAVITY_MS2
    return a


def test_selector_prefers_the_quiet_window():
    """A window with no lateral acceleration beats one that is turning hard."""
    acc = np.concatenate([_acc(20, 2.0), _acc(20, 0.0)])
    gyr = np.zeros((40, 3))
    gyr[:20, 2] = 0.2
    sl = naive.select_alignment_window(acc, gyr, 0, 40, width=10)
    assert sl.start >= 20, "picked the turning window over the quiet one"


def test_selector_returns_a_window_when_nothing_is_quiet():
    acc = _acc(30, 2.0)
    gyr = np.full((30, 3), 0.2)
    sl = naive.select_alignment_window(acc, gyr, 0, 30, width=10)
    assert sl.stop - sl.start == 10


def test_quiet_alignment_recovers_true_vertical():
    acc = _acc(20, 0.0)
    r = naive.initial_attitude(acc[:10], 0.0)
    up = r @ np.array([0.0, 0.0, 1.0])
    np.testing.assert_allclose(up, [0, 0, 1], atol=1e-9)


def test_turning_alignment_tilts_the_vertical_by_the_expected_angle():
    """Quantifies the 206 m failure mode, so a regression is visible.

    A 1.04 m/s^2 lateral acceleration tilts the estimated vertical by
    atan(1.04 / 9.80665) = 6.05 deg, mis-projecting gravity by 1.03 m/s^2.
    """
    lateral = 1.04
    r = naive.initial_attitude(_acc(10, lateral), 0.0)
    up = r @ np.array([0.0, 0.0, 1.0])
    tilt = math.degrees(math.acos(np.clip(up[2], -1.0, 1.0)))
    assert tilt == pytest.approx(math.degrees(math.atan2(lateral, naive.GRAVITY_MS2)), abs=0.1)

    horizontal_error = naive.GRAVITY_MS2 * math.sin(math.radians(tilt))
    assert horizontal_error == pytest.approx(1.03, abs=0.02)
    # Double-integrated over 20 s.
    assert 0.5 * horizontal_error * 20.0**2 == pytest.approx(206.0, abs=5.0)
