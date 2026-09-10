"""Load a drive recorded by the Android app into the pipeline's ``Sequence``.

What the app writes today, and why that is not enough
-----------------------------------------------------
``android/.../TripRecorder.kt`` writes 26 columns at the UI's 10 Hz: the
filter's *estimate* (``est_lat_deg``, ``east_m``, ``speed_ms``, ``sigma_m`` ...),
the mode machine's state and the GNSS telemetry. It writes **no accelerometer,
no gyroscope and no raw fix** -- ``est_lat_deg`` is ``engine.estimateLatLon()``,
not the receiver's position -- and during a simulated blackout
``NavigationEngine.onFix`` returns before the fix reaches anything, so the
real position during the blackout is never logged anywhere.

That file therefore cannot be replayed through ``pipeline_kinematic``; it can
only be summarised (``scripts/replay_trip.py`` calls that "self-consistency").

This loader accepts that layout *and* the raw-sample superset the recorder must
be extended to write before a replay is possible: one row per IMU sample with

    time_ns                        sensor event timestamp (ms or s also accepted)
    acc_x acc_y acc_z              m/s^2, device frame, gravity included
    gyr_x gyr_y gyr_z              rad/s, device frame
    gps_lat_deg gps_lon_deg        the *raw* fix, on the row it arrived, empty
                                   otherwise -- and still written while
                                   ``simulated_blackout`` is 1, because those
                                   rows are the only ground truth there is
    gps_speed_ms gps_course_deg gps_accuracy_m gps_sats_used cn0_mean
    has_fix simulated_blackout     as today

Columns are resolved by ASCII token signature, as ``iovnbd.py`` does, so a
renamed or inserted column cannot silently shift gyroscope data into
accelerometer fields. Nothing is resampled: the pipeline handles arbitrary dt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .iovnbd import Sequence
from .repair import RepairReport
from .schema import tokenise


class TripError(RuntimeError):
    """Base class for trip-CSV failures."""


class TripSchemaError(TripError):
    """The file does not have a usable schema. Never coerced away."""


#: A raw fix is held forward for this long so the estimator sees "a fix
#: exists" between 1 Hz arrivals at 401 Hz, exactly as ``NavigationEngine``
#: does (``fsm.timeSinceFixS < 2.0``). Held rows are never new fixes.
GNSS_HOLD_S = 2.0

#: Satellite count assumed where a fix exists but the file carries no
#: ``gps_sats_used`` column. Chosen as the FSM's healthy threshold so a missing
#: telemetry column does not push the replay into DEGRADED; reported in
#: :attr:`TripInfo.sats_source` so it is never invisible.
ASSUMED_SATS_USED = 6

#: Fraction of rows with a NaN IMU sample above which the file is rejected
#: rather than trimmed. A handful of leading rows before the first gyroscope
#: sample is normal; a tenth of the file is a broken recorder.
MAX_IMU_NAN_FRACTION = 0.01

_S = frozenset

#: canonical name -> accepted token signatures. A signature matches a header
#: field whose token set contains it; when several fields contain it, the one
#: whose token set *equals* it wins, otherwise the match is ambiguous.
TRIP_TOKEN_SIGNATURES: dict[str, tuple[frozenset[str], ...]] = {
    # raw inertial
    "acc_x": (_S({"ACC", "X"}), _S({"ACCEL", "X"}), _S({"ACCELEROMETER", "X"})),
    "acc_y": (_S({"ACC", "Y"}), _S({"ACCEL", "Y"}), _S({"ACCELEROMETER", "Y"})),
    "acc_z": (_S({"ACC", "Z"}), _S({"ACCEL", "Z"}), _S({"ACCELEROMETER", "Z"})),
    "gyr_x": (_S({"GYR", "X"}), _S({"GYRO", "X"}), _S({"GYROSCOPE", "X"})),
    "gyr_y": (_S({"GYR", "Y"}), _S({"GYRO", "Y"}), _S({"GYROSCOPE", "Y"})),
    "gyr_z": (_S({"GYR", "Z"}), _S({"GYRO", "Z"}), _S({"GYROSCOPE", "Z"})),
    # raw GNSS
    "gps_lat_deg": (_S({"GPS", "LAT"}), _S({"GPS", "LATITUDE"})),
    "gps_lon_deg": (_S({"GPS", "LON"}), _S({"GPS", "LONGITUDE"})),
    "gps_speed_raw": (_S({"GPS", "SPEED"}),),
    "gps_accuracy_m": (_S({"GPS", "ACCURACY"}),),
    "gps_orientation_deg": (_S({"GPS", "COURSE"}), _S({"GPS", "BEARING"}), _S({"GPS", "ORIENTATION"})),
    "gps_sats_used": (_S({"GPS", "SATS", "USED"}), _S({"GPS", "SATELLITES", "USED"})),
    "gps_sats_visible": (_S({"GPS", "SATS", "VISIBLE"}), _S({"GPS", "SATELLITES", "VISIBLE"})),
    "cn0_mean": (_S({"CN0"}),),
    # flags
    "has_fix": (_S({"HAS", "FIX"}),),
    "simulated_blackout": (_S({"SIMULATED", "BLACKOUT"}),),
    # the app's own estimate and diagnostics, kept under an app_ prefix so
    # they can never be mistaken for truth
    "app_mode": (_S({"MODE"}),),
    "app_lat_deg": (_S({"EST", "LAT"}),),
    "app_lon_deg": (_S({"EST", "LON"}),),
    "app_east_m": (_S({"EAST"}),),
    "app_north_m": (_S({"NORTH"}),),
    "app_speed_ms": (_S({"SPEED", "MS"}),),
    "app_heading_deg": (_S({"HEADING"}),),
    "app_sigma_m": (_S({"SIGMA"}),),
    "app_time_since_fix_s": (_S({"TIME", "SINCE", "FIX"}),),
    "app_dr_distance_m": (_S({"DR", "DISTANCE"}),),
    "app_imu_hz": (_S({"IMU", "HZ"}),),
    "app_alignment_quality": (_S({"ALIGNMENT", "QUALITY"}),),
    "app_aligned": (_S({"ALIGNED"}),),
    "app_stationary": (_S({"STATIONARY"}),),
    "app_gps_accepted": (_S({"GPS", "ACCEPTED"}),),
    "app_gps_rejected": (_S({"GPS", "REJECTED"}),),
    "app_gate_overrides": (_S({"GATE", "OVERRIDES"}),),
    "navic_visible": (_S({"NAVIC", "VISIBLE"}),),
    "navic_used": (_S({"NAVIC", "USED"}),),
    "agc_db": (_S({"AGC"}),),
}

#: Time columns in priority order: the finest clock present wins.
_TIME_SIGNATURES: tuple[tuple[str, tuple[frozenset[str], ...]], ...] = (
    ("ns", (_S({"TIME", "NS"}), _S({"TIMESTAMP", "NS"}), _S({"T", "NS"}))),
    ("ms", (_S({"TIME", "MS"}), _S({"TIMESTAMP", "MS"}), _S({"T", "MS"}))),
    ("s", (_S({"TIME", "S"}), _S({"TIMESTAMP", "S"}), _S({"T", "S"}))),
)
_UNITLESS_TIME: tuple[frozenset[str], ...] = (_S({"TIME"}), _S({"TIMESTAMP"}), _S({"T"}))

IMU_COLUMNS = ("acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z")
_GNSS_HELD = ("gps_lat_deg", "gps_lon_deg", "gps_speed_ms", "gps_accuracy_m", "gps_orientation_deg")


@dataclass(frozen=True)
class BlackoutSpan:
    """One contiguous run of suppressed GNSS. ``end_row`` is exclusive."""

    start_row: int
    end_row: int
    start_s: float
    end_s: float
    n_fixes_inside: int

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    def as_dict(self) -> dict:
        return {
            "start_row": self.start_row, "end_row": self.end_row,
            "start_s": self.start_s, "end_s": self.end_s,
            "duration_s": self.duration_s, "n_fixes_inside": self.n_fixes_inside,
        }


@dataclass(frozen=True)
class TripInfo:
    """What the loader found, so no assumption about the file is silent."""

    name: str
    path: Path
    n_rows: int
    duration_s: float
    time_unit: str
    imu_rate_hz: float
    max_gap_ms: float
    has_imu: bool
    has_raw_gnss: bool
    gnss_period_s: float
    mask_source: str
    sats_source: str
    duplicate_rows_dropped: int
    imu_nan_rows_dropped: int
    spans: tuple[BlackoutSpan, ...]

    @property
    def replayable(self) -> bool:
        """Can ``pipeline_kinematic.run`` be executed on this file?"""
        return self.has_imu and self.has_raw_gnss

    @property
    def layout(self) -> str:
        if self.replayable:
            return "raw-sample (IMU + raw GNSS)"
        if self.has_imu:
            return "IMU without raw GNSS"
        return "estimate-only (TripRecorder v1, 26 columns)"


@dataclass(frozen=True)
class Trip:
    sequence: Sequence
    info: TripInfo


# ------------------------------------------------------------ resolution


def _match(columns: dict[str, frozenset[str]], signature: frozenset[str], canonical: str) -> str | None:
    """The single raw column whose tokens contain ``signature``.

    Exact token equality breaks a tie between e.g. ``time_s`` and
    ``time_since_fix_s``; any other multiple match is a hard error.
    """
    hits = [raw for raw, toks in columns.items() if signature <= toks]
    if len(hits) <= 1:
        return hits[0] if hits else None
    exact = [raw for raw in hits if columns[raw] == signature]
    if len(exact) == 1:
        return exact[0]
    raise TripSchemaError(
        f"column signature {sorted(signature)} for {canonical!r} is ambiguous; matched {hits}"
    )


def _resolve_one(columns: dict[str, frozenset[str]], canonical: str,
                 signatures: tuple[frozenset[str], ...]) -> str | None:
    found = [m for sig in signatures if (m := _match(columns, sig, canonical)) is not None]
    if len(set(found)) > 1:
        raise TripSchemaError(f"{canonical!r} is ambiguous: {sorted(set(found))} all match")
    return found[0] if found else None


def _resolve_time(columns: dict[str, frozenset[str]]) -> tuple[str, str | None]:
    """Return ``(raw column, unit)``; unit is None when it must be inferred."""
    for unit, sigs in _TIME_SIGNATURES:
        raw = _resolve_one(columns, f"time_{unit}", sigs)
        if raw is not None:
            return raw, unit
    for sig in _UNITLESS_TIME:
        exact = [raw for raw, toks in columns.items() if toks == sig]
        if len(exact) == 1:
            return exact[0], None
    raise TripSchemaError(
        "no time column found: expected time_ns, time_ms, time_s or a bare "
        f"time/timestamp column. Header was {list(columns)[:8]}..."
    )


def _resolve_columns(raw_columns: list[str]) -> tuple[dict[str, str], str, str | None]:
    columns = {c: tokenise(c.strip()) for c in raw_columns}
    time_raw, unit = _resolve_time(columns)
    mapping = {time_raw: "time_raw"}
    for canonical, sigs in TRIP_TOKEN_SIGNATURES.items():
        raw = _resolve_one(columns, canonical, sigs)
        if raw is not None and raw != time_raw:
            mapping[raw] = canonical
    present = set(mapping.values())
    imu_present = [c for c in IMU_COLUMNS if c in present]
    if imu_present and len(imu_present) != len(IMU_COLUMNS):
        missing = [c for c in IMU_COLUMNS if c not in present]
        raise TripSchemaError(f"partial IMU: found {imu_present}, missing {missing}")
    return mapping, time_raw, unit


# ------------------------------------------------------------------- time


def _infer_time_unit(values: np.ndarray) -> str:
    """Magnitude heuristic for an unlabelled clock.

    Android sensor timestamps are elapsedRealtimeNanos, i.e. 1e11-1e15;
    epoch or elapsed milliseconds are 1e5-1e13 with steps of at least 1; a
    seconds clock started at zero never reaches 1e5 in a drive.
    """
    step = float(np.median(np.diff(values))) if values.size > 1 else 0.0
    if values.max() > 1e11 or step >= 1e5:
        return "ns"
    if values.max() > 1e5 or step >= 1.0:
        return "ms"
    return "s"


def _time_seconds(raw: pd.Series, unit: str | None) -> tuple[np.ndarray, str]:
    values = pd.to_numeric(raw, errors="coerce").to_numpy(dtype=float)
    if np.isnan(values).any():
        raise TripSchemaError("time column contains non-numeric entries")
    unit = unit or _infer_time_unit(values)
    scale = {"ns": 1e-9, "ms": 1e-3, "s": 1.0}[unit]
    return (values - values[0]) * scale, unit


def _check_monotonic(t: np.ndarray) -> None:
    bad = np.flatnonzero(np.diff(t) <= 0)
    if bad.size:
        i = int(bad[0]) + 1
        raise TripSchemaError(
            f"time is not strictly increasing at row {i} ({t[i - 1]:.6f} s -> "
            f"{t[i]:.6f} s after deduplication). A trip is one recording; a "
            f"backwards clock means a corrupt or concatenated file. Investigate "
            f"rather than coercing."
        )


# ------------------------------------------------------------------- GNSS


def _fix_structure(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """True on rows carrying a fix whose position differs from the previous fix."""
    finite = np.isfinite(lat) & np.isfinite(lon)
    is_new = np.zeros(lat.size, dtype=bool)
    prev: tuple[float, float] | None = None
    for i in np.flatnonzero(finite):
        cur = (float(lat[i]), float(lon[i]))
        if cur != prev:
            is_new[i] = True
            prev = cur
    return is_new


def _hold_forward(df: pd.DataFrame, t: np.ndarray, is_fix: np.ndarray) -> pd.DataFrame:
    """Repeat each fix's fields until the next one or ``GNSS_HOLD_S``."""
    fix_rows = np.flatnonzero(is_fix)
    if fix_rows.size == 0:
        empty = {c: np.full(t.size, np.nan) for c in _GNSS_HELD}
        return df.assign(**empty), np.zeros(t.size, dtype=bool)
    last = np.searchsorted(fix_rows, np.arange(t.size), side="right") - 1
    has_prior = last >= 0
    age = np.where(has_prior, t - t[fix_rows[np.maximum(last, 0)]], np.inf)
    held = has_prior & (age <= GNSS_HOLD_S)
    src = fix_rows[np.maximum(last, 0)]
    out = {}
    for col in _GNSS_HELD:
        values = df[col].to_numpy(dtype=float)
        out[col] = np.where(held, values[src], np.nan)
    return df.assign(**out), held


def _empty_gnss(df: pd.DataFrame) -> pd.DataFrame:
    """No raw receiver output: every GNSS field is NaN, no row is a fix."""
    n = len(df)
    empty = {c: np.full(n, np.nan) for c in _GNSS_HELD}
    sats = {} if "gps_sats_used" in df.columns else {"gps_sats_used": np.zeros(n, dtype=np.int32)}
    return df.assign(**empty, **sats, gps_fix_is_new=np.zeros(n, dtype=bool),
                     gps_fix_index=np.full(n, -1, dtype=np.int32))


def _gnss_columns(
    df: pd.DataFrame, t: np.ndarray, has_raw: bool, speed_is_kmh: bool,
) -> tuple[pd.DataFrame, np.ndarray, str]:
    """Canonical GNSS columns, fix flags and the held-fix mask."""
    if not has_raw:
        source = "recorded" if "gps_sats_used" in df.columns else "absent (no raw GNSS either)"
        return _empty_gnss(df), np.zeros(len(df), dtype=bool), source

    n = len(df)
    speed = (pd.to_numeric(df["gps_speed_raw"], errors="coerce").to_numpy(dtype=float)
             if "gps_speed_raw" in df.columns else np.full(n, np.nan))
    if speed_is_kmh:
        speed = speed / 3.6
    lat = pd.to_numeric(df["gps_lat_deg"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(df["gps_lon_deg"], errors="coerce").to_numpy(dtype=float)
    missing = {c: np.full(n, np.nan) for c in ("gps_accuracy_m", "gps_orientation_deg")
               if c not in df.columns}
    df = df.drop(columns=["gps_speed_raw"], errors="ignore").assign(
        **missing, gps_lat_deg=lat, gps_lon_deg=lon, gps_speed_ms=speed,
    )
    is_new = _fix_structure(lat, lon)
    df, held = _hold_forward(df, t, np.isfinite(lat) & np.isfinite(lon))
    df = df.assign(gps_fix_is_new=is_new, gps_fix_index=(np.cumsum(is_new) - 1).astype(np.int32))
    if "gps_sats_used" in df.columns:
        sats = pd.to_numeric(df["gps_sats_used"], errors="coerce").fillna(0).to_numpy()
        return df.assign(gps_sats_used=sats.astype(np.int32)), held, "recorded"
    assumed = np.where(held, ASSUMED_SATS_USED, 0).astype(np.int32)
    return df.assign(gps_sats_used=assumed), held, (
        f"assumed {ASSUMED_SATS_USED} where a fix is held (no gps_sats_used column)"
    )


def _mask(df: pd.DataFrame, held: np.ndarray) -> tuple[np.ndarray, str]:
    if "simulated_blackout" in df.columns:
        flag = pd.to_numeric(df["simulated_blackout"], errors="coerce").fillna(0).to_numpy()
        return flag != 0, "simulated_blackout column"
    return ~held, (
        "gnss-unavailable spans (no simulated_blackout column in this file; a "
        "real dropout and a simulated one are indistinguishable here)"
    )


def _spans(t: np.ndarray, mask: np.ndarray, is_new: np.ndarray) -> tuple[BlackoutSpan, ...]:
    if not mask.any():
        return ()
    edges = np.flatnonzero(np.diff(mask.astype(np.int8)))
    starts = [0] if mask[0] else []
    starts += [int(e) + 1 for e in edges if mask[e + 1]]
    ends = [int(e) + 1 for e in edges if mask[e]]
    if mask[-1]:
        ends.append(int(mask.size))
    out = []
    for a, b in zip(starts, ends):
        end_s = float(t[b]) if b < t.size else float(t[-1] + (t[-1] - t[-2]))
        out.append(BlackoutSpan(a, b, float(t[a]), end_s, int(is_new[a:b].sum())))
    return tuple(out)


# -------------------------------------------------------------------- IMU


def _imu_columns(df: pd.DataFrame, has_imu: bool) -> tuple[pd.DataFrame, np.ndarray]:
    """Cast IMU columns to float and flag rows that carry no sample."""
    if not has_imu:
        return df, np.ones(len(df), dtype=bool)
    cast = {c: pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float) for c in IMU_COLUMNS}
    ok = np.all(np.stack([np.isfinite(v) for v in cast.values()]), axis=0)
    if (~ok).sum() > MAX_IMU_NAN_FRACTION * len(df):
        raise TripSchemaError(
            f"{int((~ok).sum())} of {len(df)} rows have a NaN IMU sample, above the "
            f"{MAX_IMU_NAN_FRACTION:.0%} allowance for a warm-up gap"
        )
    return df.assign(**cast), ok


def _rate(t: np.ndarray) -> tuple[float, float]:
    if t.size < 2:
        return float("nan"), float("nan")
    dt = np.diff(t)
    return float(1.0 / np.median(dt)), float(dt.max() * 1e3)


def _gnss_period(t: np.ndarray, is_new: np.ndarray) -> float:
    rows = np.flatnonzero(is_new)
    return float(np.median(np.diff(t[rows]))) if rows.size >= 2 else float("nan")


# ------------------------------------------------------------------ public


def _read_frame(path: Path) -> tuple[pd.DataFrame, str | None, bool]:
    """Read and canonicalise columns. Returns the frame, the time unit if the
    header names one, and whether the raw speed column is in km/h."""
    raw = pd.read_csv(path, skipinitialspace=True)
    if raw.empty:
        raise TripSchemaError(f"{path.name} has a header but no rows")
    mapping, time_raw, unit = _resolve_columns(list(raw.columns))
    df = raw[list(mapping)].rename(columns=mapping)
    speed_raw = next((r for r, c in mapping.items() if c == "gps_speed_raw"), "")
    speed_is_kmh = bool(tokenise(speed_raw) & {"KMH", "KPH"})
    return df, unit, speed_is_kmh


def read_trip(path: str | Path) -> Trip:
    """Load one recorded trip and describe what was found."""
    path = Path(path)
    df, unit, speed_is_kmh = _read_frame(path)
    rows_in_file = len(df)
    t_all, unit = _time_seconds(df["time_raw"], unit)
    df = df.assign(time_s=t_all).drop(columns=["time_raw"])

    before = len(df)
    df = df.drop_duplicates(subset=["time_s"], keep="first").reset_index(drop=True)
    n_dup = before - len(df)
    _check_monotonic(df["time_s"].to_numpy())

    has_imu = all(c in df.columns for c in IMU_COLUMNS)
    df, imu_ok = _imu_columns(df, has_imu)
    n_imu_dropped = int((~imu_ok).sum())
    df = df.loc[imu_ok].reset_index(drop=True)
    if len(df) < 2:
        raise TripSchemaError(f"{path.name}: fewer than two usable rows")
    t = df["time_s"].to_numpy()

    has_raw_gnss = "gps_lat_deg" in df.columns and "gps_lon_deg" in df.columns
    df, held, sats_source = _gnss_columns(df, t, has_raw_gnss, speed_is_kmh)
    mask, mask_source = _mask(df, held)
    df = df.assign(gnss_available=held & ~mask, blackout_mask=mask)
    is_new = df["gps_fix_is_new"].to_numpy()

    rate_hz, max_gap_ms = _rate(t)
    report = RepairReport(duplicate_rows_dropped=n_dup, rows_in_file=rows_in_file, rows_kept=len(df))
    seq = Sequence(name=path.stem, path=path, df=df, repair=report)
    info = TripInfo(
        name=path.stem, path=path, n_rows=len(df), duration_s=float(t[-1] - t[0]),
        time_unit=unit, imu_rate_hz=rate_hz, max_gap_ms=max_gap_ms,
        has_imu=has_imu, has_raw_gnss=has_raw_gnss,
        gnss_period_s=_gnss_period(t, is_new),
        mask_source=mask_source, sats_source=sats_source,
        duplicate_rows_dropped=n_dup, imu_nan_rows_dropped=n_imu_dropped,
        spans=_spans(t, mask, is_new),
    )
    return Trip(sequence=seq, info=info)


def load_trip(path: str | Path) -> Sequence:
    """The recorded trip as a pipeline ``Sequence``. See :func:`read_trip`."""
    return read_trip(path).sequence
