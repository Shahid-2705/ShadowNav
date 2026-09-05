"""Tests for the three IO-VNBD defects found by auditing all 72 S-side files.

None of these three appear in Track H. Each corrupts downstream numbers
silently, so each gets a test that fails loudly if the repair is removed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from shadownav.data import iovnbd, repair
from tests.conftest import synth_s_rows, write_s_csv


# --------------------------------------------------------------------------
# Defect 1: Excel date corruption of the satellite column
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "corrupt,expected",
    [
        ("Dec-14", (12, 14)),   # MMM-DD  -> month / day
        ("Nov-16", (11, 16)),
        ("Oct-13", (10, 13)),
        ("May-22", (5, 22)),
        ("10-Dec", (10, 12)),   # DD-MMM  -> day / month
        ("12-Dec", (12, 12)),
        ("11-Dec", (11, 12)),
        ("10-Nov", (10, 11)),
    ],
)
def test_excel_date_inversion(corrupt: str, expected: tuple[int, int]):
    out, n = repair.repair_excel_satellites(pd.Series([corrupt]))
    assert n == 1
    used, visible = (int(x) for x in out.iloc[0].split("/"))
    assert (used, visible) == expected
    assert used <= visible, "inversion must satisfy the used<=visible invariant"


def test_well_formed_values_are_untouched():
    src = pd.Series(["22 / 23", "18 / 19", "7 / 20"])
    out, n = repair.repair_excel_satellites(src)
    assert n == 0
    assert list(out) == list(src)


def test_unrecognised_garbage_is_left_for_the_parser_to_reject():
    """Repair must not swallow values it does not understand."""
    out, n = repair.repair_excel_satellites(pd.Series(["not-a-count"]))
    assert n == 0
    assert out.iloc[0] == "not-a-count"


def test_corrupted_file_loads_after_repair(tmp_path: Path):
    rows = synth_s_rows(n_rows=200)
    # Excel only mangles values whose first number is <= 12, so corrupt a row
    # the way Excel actually would.
    for i in (30, 31, 32):
        rows[i] = rows[i].replace(b"22 / 22", b"Dec-14")
    path = write_s_csv(tmp_path / "S-Excel.csv", rows)

    seq = iovnbd.load_s_sequence(path)
    assert seq.repair.excel_dates_repaired == 3
    assert seq.df["gps_sats_used"].iloc[30] == 12
    assert seq.df["gps_sats_visible"].iloc[30] == 14


def test_corruption_selectively_hits_low_satellite_rows():
    """The reason repair matters rather than dropping rows.

    Excel only converts values it can read as a date, which needs the first
    number <= 12. So corruption is confined to rows with few satellites in the
    fix -- exactly the degraded-GNSS rows under study. Dropping them would bias
    the dataset away from the condition being tested.
    """
    convertible = [f"{u} / 20" for u in range(1, 13)]
    safe = [f"{u} / 20" for u in range(13, 25)]
    for v in convertible:
        assert int(v.split("/")[0]) <= 12
    for v in safe:
        assert int(v.split("/")[0]) > 12


# --------------------------------------------------------------------------
# Defect 2: concatenated recording sessions
# --------------------------------------------------------------------------

def test_backwards_clock_splits_into_sessions():
    t = np.array([0.0, 100, 200, 300, 10, 110, 210])
    spans = repair.find_session_boundaries(t)
    assert spans == [(0, 4), (4, 7)]


def test_forward_only_clock_yields_one_session():
    t = np.arange(0.0, 1000.0, 100.0)
    assert repair.find_session_boundaries(t) == [(0, len(t))]


def test_loader_splits_a_concatenated_file(tmp_path: Path):
    a = synth_s_rows(n_rows=200, seed=1)
    b = synth_s_rows(n_rows=150, seed=2)
    path = write_s_csv(tmp_path / "S-TwoSessions.csv", a + b)

    sessions = iovnbd.load_s_sessions(path)
    assert len(sessions) == 2
    assert [len(s) for s in sessions] == [200, 150]
    assert sessions[0].repair.sessions_found == 2
    # Each session's clock restarts at zero -- no fabricated gap.
    for s in sessions:
        assert s.time_s[0] == pytest.approx(0.0)
        assert np.all(np.diff(s.time_s) > 0)


def test_load_s_sequence_returns_the_longest_session_and_says_so(tmp_path: Path):
    a = synth_s_rows(n_rows=120, seed=1)
    b = synth_s_rows(n_rows=400, seed=2)
    path = write_s_csv(tmp_path / "S-Uneven.csv", a + b)

    seq = iovnbd.load_s_sequence(path)
    assert len(seq) == 400
    assert seq.repair.sessions_found == 2
    assert not seq.repair.clean, "choosing a session must never be invisible"


def test_short_sessions_are_dropped_by_the_minimum(tmp_path: Path):
    a = synth_s_rows(n_rows=300, seed=1)
    b = synth_s_rows(n_rows=5, seed=2)
    path = write_s_csv(tmp_path / "S-Fragment.csv", a + b)
    sessions = iovnbd.load_s_sessions(path, min_rows=100)
    assert len(sessions) == 1
    assert len(sessions[0]) == 300


# --------------------------------------------------------------------------
# Defect 3: duplicate timestamp rows
# --------------------------------------------------------------------------

def test_duplicate_timestamps_are_dropped_keeping_the_first():
    df = pd.DataFrame({"time_ms": [0, 100, 100, 200], "v": [1, 2, 99, 3]})
    out, n = repair.drop_duplicate_timestamps(df)
    assert n == 1
    assert list(out["time_ms"]) == [0, 100, 200]
    assert list(out["v"]) == [1, 2, 3]


def test_loader_deduplicates_and_reports(tmp_path: Path):
    rows = synth_s_rows(n_rows=200)
    rows = rows[:50] + [rows[49], rows[49]] + rows[50:]
    path = write_s_csv(tmp_path / "S-Dup.csv", rows)

    seq = iovnbd.load_s_sequence(path)
    assert seq.repair.duplicate_rows_dropped == 2
    assert len(seq) == 200
    assert np.all(np.diff(seq.time_s) > 0)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def test_clean_file_reports_clean(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    assert seq.repair.clean
    assert seq.repair.summary() == "clean"


def test_repair_summary_names_every_applied_fix(tmp_path: Path):
    a = synth_s_rows(n_rows=200, seed=1)
    a[10] = a[10].replace(b"22 / 22", b"Nov-16")
    a = a[:60] + [a[59]] + a[60:]
    path = write_s_csv(tmp_path / "S-Messy.csv", a + synth_s_rows(n_rows=150, seed=2))

    seq = iovnbd.load_s_sequence(path)
    text = seq.repair.summary()
    assert "excel-date" in text
    assert "duplicate" in text
    assert "session" in text
