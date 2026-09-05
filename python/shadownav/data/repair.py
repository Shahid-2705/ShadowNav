"""Repairs for IO-VNBD S-side defects found on 2026-09-05.

None of these three are in Track H. All were found by auditing all 72 S-side
files rather than by reading the dataset paper, and all of them silently corrupt
downstream numbers if left alone.

1. Excel date corruption of the satellite column
   ------------------------------------------------------------------
   12 of 72 files contain values like ``Dec-14``, ``Nov-16`` and ``10-Dec`` in
   ``GPS SATELLITES IN RANGE``. These are Excel's date autocorrect applied to
   ``"12 / 14"``, ``"11 / 16"`` and ``"10 / 12"``: somebody opened the CSVs in
   Excel and re-saved them.

   The corruption is *selective in the worst possible way*. Excel only converts
   a value it can read as a date, which requires the first number to be <= 12.
   So it destroys exactly the rows where fewer than 13 satellites were in the
   fix -- the degraded-GNSS rows this project exists to handle. Dropping the
   corrupted rows would bias the dataset away from the conditions under test.

   The transform is exactly invertible: ``MMM-DD`` -> ``month / DD`` and
   ``DD-MMM`` -> ``DD / month``. Verified across all 48 distinct corrupted forms
   present in the dataset -- every one inverts to ``used <= visible``, which is
   the independent invariant that says the inversion is right.

2. Concatenated recording sessions
   ------------------------------------------------------------------
   5 files contain a point where ``TIME SINCE START`` resets toward zero while
   the wall-clock ``DATE`` column continues forward. Separate AndroSensor
   recordings were concatenated into one CSV. In S-S2 the clock jumps from
   186311 ms back to 10 ms while the date advances 12:06:58.041 -> 12:06:59.249.

   These are different drives, not one drive with a glitch, so they are split
   rather than stitched. Integrating across the boundary would inject a
   fabricated 186-second gap into the trajectory.

3. Duplicate timestamp rows
   ------------------------------------------------------------------
   7 files repeat rows at an identical timestamp; S-Vtb1 has 5456 such pairs
   across 32459 rows (17%). Inspection shows 5370 of 5456 are byte-identical
   duplicates of the preceding row, so deduplication is safe and is not
   discarding independent samples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
         "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    )
}

_WELL_FORMED = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")
_MMM_DD = re.compile(r"^([A-Za-z]{3})-(\d{1,2})$")
_DD_MMM = re.compile(r"^(\d{1,2})-([A-Za-z]{3})$")


@dataclass(frozen=True)
class RepairReport:
    """What the loader had to fix. Attached to every Sequence, never silent."""

    excel_dates_repaired: int = 0
    duplicate_rows_dropped: int = 0
    sessions_found: int = 1
    session_index: int = 0
    rows_in_file: int = 0
    rows_kept: int = 0

    @property
    def clean(self) -> bool:
        return (
            self.excel_dates_repaired == 0
            and self.duplicate_rows_dropped == 0
            and self.sessions_found == 1
        )

    def summary(self) -> str:
        if self.clean:
            return "clean"
        bits = []
        if self.excel_dates_repaired:
            bits.append(f"{self.excel_dates_repaired} excel-date cells repaired")
        if self.duplicate_rows_dropped:
            bits.append(f"{self.duplicate_rows_dropped} duplicate rows dropped")
        if self.sessions_found > 1:
            bits.append(
                f"session {self.session_index + 1}/{self.sessions_found}"
            )
        return "; ".join(bits)


def repair_excel_satellites(raw: pd.Series) -> tuple[pd.Series, int]:
    """Invert Excel's date autocorrect on the satellite column.

    Returns the repaired series and the number of cells changed. Values that are
    already well formed are passed through untouched; values matching neither
    the well-formed pattern nor either date pattern are left as they are, so the
    downstream parser still raises on them rather than having them quietly
    swallowed here.
    """
    text = raw.astype(str).str.strip()
    repaired = text.copy()
    n = 0

    for idx, value in text.items():
        if _WELL_FORMED.match(value):
            continue
        m = _MMM_DD.match(value)
        if m:
            month = _MONTHS.get(m.group(1).upper())
            if month is not None:
                repaired.at[idx] = f"{month} / {int(m.group(2))}"
                n += 1
                continue
        m = _DD_MMM.match(value)
        if m:
            month = _MONTHS.get(m.group(2).upper())
            if month is not None:
                repaired.at[idx] = f"{int(m.group(1))} / {month}"
                n += 1
    return repaired, n


def find_session_boundaries(time_ms: np.ndarray) -> list[tuple[int, int]]:
    """Split at every backwards jump in the clock.

    Returns ``[(start, stop), ...]`` half-open row ranges. A strictly backwards
    step means a new recording session; a zero step is a duplicate row and is
    handled separately by :func:`drop_duplicate_timestamps`.
    """
    if time_ms.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(time_ms) < 0) + 1
    edges = [0, *breaks.tolist(), len(time_ms)]
    return [(a, b) for a, b in zip(edges[:-1], edges[1:]) if b > a]


def drop_duplicate_timestamps(df: pd.DataFrame, time_col: str = "time_ms") -> tuple[pd.DataFrame, int]:
    """Keep the first row of each timestamp, drop later repeats.

    Safe because the repeats are byte-identical duplicates of their predecessor
    (verified on S-Vtb1, the worst case at 17%). Keeping the first rather than
    the last is arbitrary but deterministic, which is what the reproducibility
    gate needs.
    """
    before = len(df)
    out = df.drop_duplicates(subset=[time_col], keep="first")
    return out.reset_index(drop=True), before - len(out)
