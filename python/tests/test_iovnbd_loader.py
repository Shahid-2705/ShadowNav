"""Loader regression tests -- one test per documented dataset hazard.

Each hazard in research/SIH26168-open-track-findings.md Track H gets a test that
fails loudly if the mitigation is ever removed. These are the tests that stop a
future refactor from silently reintroducing a full day of debugging.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from shadownav.data import iovnbd, schema
from tests.conftest import GPS_REPEAT, S_HEADER_LATIN1, synth_s_rows, write_s_csv


# --------------------------------------------------------------------------
# Hazard 1: leading (and trailing) whitespace in column names
# --------------------------------------------------------------------------

def test_header_really_has_irregular_whitespace():
    """Guard the fixture itself: if this stops being true the tests below are vacuous."""
    header = S_HEADER_LATIN1.decode("latin-1")
    fields = header.split(",")
    assert fields[1].startswith(" "), "expected a leading space on column 2"
    assert not fields[6].startswith(" "), (
        "GPS SATELLITES IN RANGE has no leading space in the real file -- "
        "the whitespace is irregular, not uniform"
    )
    assert any(f.rstrip(")").endswith(" ") or f.endswith(" ") for f in fields), (
        "expected at least one trailing space"
    )
    assert "Roll )" in header, "expected the space before the closing paren in Roll"


def test_columns_are_canonicalised(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    for name in (
        "time_s", "gps_lat_deg", "gps_lon_deg", "gps_speed_ms",
        "acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z",
        "gps_sats_used", "gps_sats_visible",
    ):
        assert name in seq.df.columns, f"missing canonical column {name}"
    assert not any(c != c.strip() for c in seq.df.columns), "untrimmed column name survived"


# --------------------------------------------------------------------------
# Hazard 2: latin-1, not UTF-8
# --------------------------------------------------------------------------

def test_file_is_not_valid_utf8(s_csv_straight: Path):
    """The mitigation is only meaningful if the hazard is real."""
    raw = s_csv_straight.read_bytes()
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")


def test_utf8_read_fails_but_loader_succeeds(s_csv_straight: Path):
    with pytest.raises(UnicodeDecodeError):
        pd.read_csv(s_csv_straight, encoding="utf-8")
    seq = iovnbd.load_s_sequence(s_csv_straight)
    assert len(seq.df) == 300


# --------------------------------------------------------------------------
# Hazard 3: "GPS SATELLITES IN RANGE" is a string like "22 / 22"
# --------------------------------------------------------------------------

def test_satellites_string_is_split_into_two_integers(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    assert seq.df["gps_sats_used"].dtype.kind in "iu"
    assert seq.df["gps_sats_visible"].dtype.kind in "iu"
    assert (seq.df["gps_sats_used"] == 22).all()
    assert (seq.df["gps_sats_visible"] == 22).all()


def test_malformed_satellite_field_is_rejected_not_coerced(tmp_path: Path):
    rows = synth_s_rows(n_rows=20)
    rows[5] = rows[5].replace(b"22 / 22", b"not-a-count")
    path = write_s_csv(tmp_path / "S-Bad.csv", rows)
    with pytest.raises(iovnbd.IOVNBDSchemaError, match="satellite"):
        iovnbd.load_s_sequence(path)


# --------------------------------------------------------------------------
# Hazard 4: 10 Hz sampling with a 1 Hz GPS update -- fixes repeat in blocks
# --------------------------------------------------------------------------

def test_gps_fixes_repeat_in_blocks_of_ten(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    assert len(seq.df) == 300
    assert seq.n_unique_gps_fixes == 300 // GPS_REPEAT
    assert seq.df["gps_fix_index"].max() == 300 // GPS_REPEAT - 1


def test_gps_fix_is_new_flag_marks_exactly_one_row_per_fix(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    assert seq.df["gps_fix_is_new"].sum() == seq.n_unique_gps_fixes
    # The first row of each block is the new one.
    idx = np.flatnonzero(seq.df["gps_fix_is_new"].to_numpy())
    assert (idx % GPS_REPEAT == 0).all()


def test_repeated_fixes_are_not_independent_observations(s_csv_straight: Path):
    """Regression guard against treating 300 rows as 300 GPS observations."""
    seq = iovnbd.load_s_sequence(s_csv_straight)
    assert seq.n_unique_gps_fixes < len(seq.df) / 5, (
        "if this ever passes trivially the block structure has been lost"
    )


# --------------------------------------------------------------------------
# Hazard 5: CRLF line endings (found on the real file, not in Track H)
# --------------------------------------------------------------------------

def test_fixture_uses_crlf_and_loader_does_not_leak_carriage_returns(s_csv_straight: Path):
    assert b"\r\n" in s_csv_straight.read_bytes()
    seq = iovnbd.load_s_sequence(s_csv_straight)
    assert not any("\r" in c for c in seq.df.columns)
    assert seq.df.select_dtypes("object").empty or not (
        seq.df.select_dtypes("object")
        .apply(lambda col: col.astype(str).str.contains("\r").any())
        .any()
    )


# --------------------------------------------------------------------------
# Units and derived quantities
# --------------------------------------------------------------------------

def test_speed_is_converted_from_kmh_to_ms(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    np.testing.assert_allclose(seq.df["gps_speed_ms"].to_numpy(), 36.0 / 3.6, rtol=1e-9)


def test_time_is_seconds_from_zero_and_monotonic(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    t = seq.df["time_s"].to_numpy()
    assert t[0] == pytest.approx(0.0)
    assert np.all(np.diff(t) > 0)
    np.testing.assert_allclose(np.diff(t), 0.1, atol=1e-9)
    assert seq.sample_rate_hz == pytest.approx(10.0, rel=1e-6)


def test_duration_matches_row_count(s_csv_straight: Path):
    seq = iovnbd.load_s_sequence(s_csv_straight)
    assert seq.duration_s == pytest.approx(29.9)


# --------------------------------------------------------------------------
# Scope guards
# --------------------------------------------------------------------------

def test_v_side_load_refuses_with_an_explanation(tmp_path: Path):
    """V- files are ECU, England-only, and out of scope for a smartphone-only PS."""
    path = tmp_path / "V-Vta10.csv"
    path.write_bytes(b"GPS SATELLITES, TIME\r\n1,2\r\n")
    with pytest.raises(iovnbd.IOVNBDScopeError, match="smartphone-only"):
        iovnbd.load_s_sequence(path)


def test_unknown_column_signature_raises_rather_than_silently_dropping(tmp_path: Path):
    header = b"ALPHA (x), BETA (y)"
    body = header + b"\r\n1,2\r\n"
    path = tmp_path / "S-Weird.csv"
    path.write_bytes(body)
    with pytest.raises(iovnbd.IOVNBDSchemaError):
        iovnbd.load_s_sequence(path)


# --------------------------------------------------------------------------
# Schema resolver
# --------------------------------------------------------------------------

def test_token_signatures_are_unambiguous():
    """Every canonical column must match exactly one real header field."""
    fields = [f.strip() for f in S_HEADER_LATIN1.decode("latin-1").split(",")]
    for canonical, tokens in schema.S_TOKEN_SIGNATURES.items():
        hits = [f for f in fields if tokens <= schema.tokenise(f)]
        assert len(hits) == 1, f"{canonical} matched {len(hits)} fields: {hits}"


def test_every_real_column_is_claimed_by_exactly_one_signature():
    fields = [f.strip() for f in S_HEADER_LATIN1.decode("latin-1").split(",")]
    for field in fields:
        toks = schema.tokenise(field)
        owners = [c for c, sig in schema.S_TOKEN_SIGNATURES.items() if sig <= toks]
        assert len(owners) == 1, f"{field!r} claimed by {owners}"
