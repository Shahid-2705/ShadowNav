"""IO-VNBD S-side (smartphone) sequence loader.

Every hazard this module defends against is documented in
``research/SIH26168-open-track-findings.md`` Track H, except two found by
inspecting the real ``S-Vta10.csv`` on 2026-09-05 and recorded here:

  * files use CRLF line endings
  * ``ORIENTATION (Roll )`` carries a space before the closing paren

and one that *contradicts* Track H, recorded in
``research/SIH26168-external-review-response.md`` and re-verified by
``scripts/audit_gps_rate.py``: the GPS fix does not update at 1 Hz. See
:func:`load_s_sequence` and the ``gps_update_period_s`` property.

Scope: S-side only. V-side files are vehicle-ECU data, England-only, and carry
wheel-speed sensors this project deliberately does not use (PLAN.md:13).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import repair as repair_mod
from . import schema
from .repair import RepairReport


class IOVNBDError(RuntimeError):
    """Base class for loader failures."""


class IOVNBDSchemaError(IOVNBDError):
    """The file does not have the schema we expect. Never coerced away."""


class IOVNBDScopeError(IOVNBDError):
    """The file is real but out of scope for a smartphone-only system."""


#: Columns that define a distinct GPS fix: the horizontal position solution,
#: and nothing else.
#:
#: Derived fields must NOT be included. Course over ground and reported accuracy
#: jitter every sample while the vehicle is stationary, and including them marks
#: every standstill row as a new fix -- S-Y1 reported 785 "fixes" that way, most
#: of them at zero speed with the vehicle not moving at all, which silently
#: inflated the apparent fix rate and made the filter believe it was being
#: corrected when it was not.
#:
#: Latitude alone is equally wrong in the other direction: on a near-east/west
#: drive it is constant to 6 decimal places for scores of rows while longitude
#: advances at every fix. The pair is the right signal.
_GPS_FIX_COLUMNS = (
    "gps_lat_deg",
    "gps_lon_deg",
)


@dataclass(frozen=True)
class Sequence:
    """One loaded S-side drive.

    Immutable by construction: :meth:`with_columns` returns a new Sequence
    rather than mutating this one, so a masking or resampling step can never
    corrupt the loaded original held by a caller upstream.
    """

    name: str
    path: Path
    df: pd.DataFrame
    repair: RepairReport = RepairReport()

    # -- timing ----------------------------------------------------------
    @property
    def time_s(self) -> np.ndarray:
        return self.df["time_s"].to_numpy()

    @property
    def duration_s(self) -> float:
        t = self.time_s
        return float(t[-1] - t[0])

    @property
    def sample_rate_hz(self) -> float:
        dt = np.diff(self.time_s)
        return float(1.0 / np.median(dt))

    # -- GPS -------------------------------------------------------------
    @property
    def n_unique_gps_fixes(self) -> int:
        return int(self.df["gps_fix_index"].max()) + 1

    @property
    def gps_update_period_s(self) -> float:
        """Median wall-clock seconds between distinct GPS fixes.

        Track H states 1 Hz. Measured values on the real data are far longer --
        this property exists so the assumption is always checked, never assumed.
        """
        new = self.df.loc[self.df["gps_fix_is_new"], "time_s"].to_numpy()
        if new.size < 2:
            return float("nan")
        return float(np.median(np.diff(new)))

    @property
    def rows_per_gps_fix(self) -> float:
        return len(self.df) / max(self.n_unique_gps_fixes, 1)

    def with_columns(self, **columns: np.ndarray) -> "Sequence":
        """Return a new Sequence with extra columns. Never mutates self."""
        return Sequence(self.name, self.path, self.df.assign(**columns), self.repair)

    def slice_time(self, t0: float, t1: float) -> "Sequence":
        """Return a new Sequence restricted to ``[t0, t1)`` seconds."""
        m = (self.df["time_s"] >= t0) & (self.df["time_s"] < t1)
        return Sequence(
            self.name, self.path, self.df.loc[m].reset_index(drop=True), self.repair
        )

    def __len__(self) -> int:
        return len(self.df)


def _resolve_columns(raw_columns: list[str]) -> dict[str, str]:
    """Map raw header fields to canonical names by token signature.

    Ambiguity is an error rather than a silent first-match, because a silent
    mismatch here maps gyroscope data into accelerometer columns and every
    downstream number becomes quietly wrong.
    """
    stripped = {c: c.strip() for c in raw_columns}
    mapping: dict[str, str] = {}
    for canonical, tokens in schema.S_TOKEN_SIGNATURES.items():
        hits = [raw for raw, s in stripped.items() if tokens <= schema.tokenise(s)]
        if len(hits) > 1:
            raise IOVNBDSchemaError(
                f"column signature {set(tokens)} for {canonical!r} is ambiguous; "
                f"matched {hits}"
            )
        if hits:
            mapping[hits[0]] = canonical

    missing = schema.S_REQUIRED - set(mapping.values())
    if missing:
        raise IOVNBDSchemaError(
            f"required columns not found: {sorted(missing)}. "
            f"Header was: {[stripped[c] for c in raw_columns][:6]}..."
        )
    return mapping


def _parse_satellites(raw: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Split ``"22 / 23"`` into (used_in_fix, visible).

    Semantics inferred from the data, not from the header: across
    ``S-Vta10.csv`` the left value is never greater than the right
    (``22 / 23``, ``23 / 24``, ``22 / 24``), which is only consistent with
    left = in fix, right = in range. The invariant is asserted below so that a
    file violating it fails loudly instead of silently inverting the meaning.
    """
    text = raw.astype(str).str.strip()
    parts = text.str.split("/", n=1, expand=True)
    if parts.shape[1] != 2:
        raise IOVNBDSchemaError(
            "satellite column is not of the form 'used / visible'; "
            f"first value was {text.iloc[0]!r}"
        )
    try:
        used = pd.to_numeric(parts[0].str.strip(), errors="raise").to_numpy()
        visible = pd.to_numeric(parts[1].str.strip(), errors="raise").to_numpy()
    except (ValueError, TypeError) as exc:
        bad = text[~text.str.match(r"^\s*\d+\s*/\s*\d+\s*$")].unique()[:3]
        raise IOVNBDSchemaError(
            f"satellite column has non-numeric entries, e.g. {list(bad)}"
        ) from exc

    if np.any(used > visible):
        raise IOVNBDSchemaError(
            "satellite column has used > visible, which inverts the assumed "
            "'in fix / in range' reading. Investigate before proceeding."
        )
    return used.astype(np.int32), visible.astype(np.int32)


def _gps_fix_structure(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Index distinct GPS fixes and flag the first row of each block.

    Change detection uses the *whole* GPS tuple, not latitude alone. On a
    near-east/west drive latitude is constant to 6 decimal places for scores of
    rows while longitude advances every fix, so a latitude-only test reports a
    fix rate that is wrong by an order of magnitude.
    """
    present = [c for c in _GPS_FIX_COLUMNS if c in df.columns]
    tup = df[present].to_numpy()
    changed = np.ones(len(df), dtype=bool)
    if len(df) > 1:
        changed[1:] = np.any(tup[1:] != tup[:-1], axis=1)
    return np.cumsum(changed) - 1, changed


DEFAULT_MIN_SESSION_ROWS = 100


def _read_raw(path: Path) -> pd.DataFrame:
    """Read and canonicalise columns, before any session splitting."""
    if path.name.upper().startswith("V-"):
        raise IOVNBDScopeError(
            f"{path.name} is vehicle-ECU (V-side) data: England-only, and it "
            f"carries wheel-speed sensors. This project is smartphone-only "
            f"(PLAN.md:13). Use an S- sequence."
        )

    # latin-1 is mandatory: the unit symbols include a bare 0xB2 which is not
    # valid UTF-8. skipinitialspace handles the leading spaces; column names are
    # stripped separately because some carry a *trailing* space too.
    df = pd.read_csv(path, encoding="latin-1", skipinitialspace=True)

    mapping = _resolve_columns(list(df.columns))
    df = df[list(mapping)].rename(columns=mapping)
    df.columns = [c.strip() for c in df.columns]
    return df


def _finalise(df: pd.DataFrame, name: str, path: Path, report: RepairReport) -> Sequence:
    """Derive canonical units and GPS structure on one already-split session."""
    df = df.reset_index(drop=True)

    t_ms = pd.to_numeric(df["time_ms"], errors="coerce").to_numpy(dtype=float)
    if np.isnan(t_ms).any():
        raise IOVNBDSchemaError("time column contains non-numeric entries")
    df["time_s"] = (t_ms - t_ms[0]) / 1000.0

    df["gps_speed_ms"] = df["gps_speed_kmh"].to_numpy(dtype=float) * schema.KMH_TO_MS

    fix_index, is_new = _gps_fix_structure(df)
    df["gps_fix_index"] = fix_index.astype(np.int32)
    df["gps_fix_is_new"] = is_new

    if not np.all(np.diff(df["time_s"].to_numpy()) > 0):
        raise IOVNBDSchemaError(
            "time is still not strictly increasing after session splitting and "
            "deduplication -- investigate rather than coercing"
        )
    return Sequence(name=name, path=path, df=df, repair=report)


def load_s_sessions(
    path: str | Path, *, min_rows: int = DEFAULT_MIN_SESSION_ROWS
) -> list[Sequence]:
    """Load every independent recording session in one S-side CSV.

    Five files concatenate multiple AndroSensor recordings, marked by the clock
    resetting toward zero while the wall-clock date continues. Those are split
    here rather than stitched: integrating across such a boundary would inject a
    fabricated multi-minute gap into the trajectory. Most files yield exactly
    one session.

    See :mod:`shadownav.data.repair` for the three defects handled.
    """
    path = Path(path)
    df = _read_raw(path)
    rows_in_file = len(df)

    df["gps_satellites_raw"], n_excel = repair_mod.repair_excel_satellites(
        df["gps_satellites_raw"]
    )

    # Validate and expand the satellite column across the whole file *before*
    # session splitting. Doing it per session would let the minimum-length check
    # mask a genuine schema error behind a misleading "no session survived".
    used, visible = _parse_satellites(df["gps_satellites_raw"])
    df["gps_sats_used"] = used
    df["gps_sats_visible"] = visible

    t_ms = pd.to_numeric(df["time_ms"], errors="coerce").to_numpy(dtype=float)
    if np.isnan(t_ms).any():
        raise IOVNBDSchemaError("time column contains non-numeric entries")
    spans = repair_mod.find_session_boundaries(t_ms)

    out: list[Sequence] = []
    for i, (start, stop) in enumerate(spans):
        chunk = df.iloc[start:stop]
        chunk, n_dup = repair_mod.drop_duplicate_timestamps(chunk)
        if len(chunk) < min_rows:
            continue
        suffix = f"#{i}" if len(spans) > 1 else ""
        report = RepairReport(
            # Excel repairs are counted per file, not per session; attributing
            # them per session would need a second pass for no benefit.
            excel_dates_repaired=n_excel if i == 0 else 0,
            duplicate_rows_dropped=n_dup,
            sessions_found=len(spans),
            session_index=i,
            rows_in_file=rows_in_file,
            rows_kept=len(chunk),
        )
        out.append(_finalise(chunk, f"{path.stem}{suffix}", path, report))

    if not out:
        raise IOVNBDError(
            f"{path.name}: no session survived the {min_rows}-row minimum "
            f"(file had {rows_in_file} rows across {len(spans)} sessions)"
        )
    return out


def load_s_sequence(path: str | Path, *, min_rows: int = DEFAULT_MIN_SESSION_ROWS) -> Sequence:
    """Load the longest session from one S-side CSV.

    Convenience wrapper over :func:`load_s_sessions` for the common case. The
    returned Sequence's ``repair`` report states how many sessions the file
    actually held, so choosing the longest is never invisible.
    """
    sessions = load_s_sessions(path, min_rows=min_rows)
    return max(sessions, key=len)


def load_directory(
    directory: str | Path, *, min_rows: int = DEFAULT_MIN_SESSION_ROWS
) -> list[Sequence]:
    """Load every session of every ``S-*.csv`` in a directory, sorted by name."""
    directory = Path(directory)
    paths = sorted(p for p in directory.glob("S-*.csv"))
    if not paths:
        raise IOVNBDError(
            f"no S-*.csv found in {directory}. "
            f"Run: python -m shadownav.data.fetch"
        )
    out: list[Sequence] = []
    for p in paths:
        out.extend(load_s_sessions(p, min_rows=min_rows))
    return out
