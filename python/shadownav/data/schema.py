"""Canonical column names for IO-VNBD, resolved by ASCII token signature.

Why signatures rather than exact string matching: the real headers embed unit
symbols as raw latin-1 bytes (0xB0 degree, 0xB2 superscript two, 0xB5 micro) and
carry irregular leading/trailing whitespace. Exact matching against those strings
is brittle -- one re-encode upstream and every column silently fails to resolve.

Positional matching is worse: it fails *silently and wrongly*, mapping gyroscope
data into accelerometer columns if a column is ever inserted.

Signature matching keys on the ASCII words a human would use to name the column
("ACCELEROMETER" and "X"), which survive any encoding mangling of the unit symbol
because the mangling only ever touches non-ASCII bytes. Ambiguity is a hard error,
and tests assert that every signature claims exactly one real column and that
every real column is claimed by exactly one signature.
"""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def tokenise(field: str) -> frozenset[str]:
    """Reduce a raw header field to the ASCII words it contains.

    Non-ASCII bytes are dropped rather than transliterated, because the whole
    point is to not depend on how the unit symbol survived the encoding.
    """
    ascii_only = field.encode("ascii", "ignore").decode("ascii").upper()
    return frozenset(t for t in _NON_ALNUM.split(ascii_only) if t)


def _sig(*tokens: str) -> frozenset[str]:
    return frozenset(tokens)


#: Canonical name -> the token set that must be a subset of the header field.
#: Order is the real file's column order, for readability only.
S_TOKEN_SIGNATURES: dict[str, frozenset[str]] = {
    "gps_lat_deg": _sig("GPS", "LATITUDE"),
    "gps_lon_deg": _sig("GPS", "LONGITUDE"),
    "gps_alt_m": _sig("GPS", "ALTITUDE"),
    "gps_speed_kmh": _sig("GPS", "SPEED"),
    "gps_accuracy_m": _sig("GPS", "ACCURACY"),
    "gps_orientation_deg": _sig("GPS", "ORIENTATION"),
    "gps_satellites_raw": _sig("GPS", "SATELLITES"),
    "time_ms": _sig("TIME", "SINCE", "START"),
    "date_raw": _sig("DATE"),
    "acc_x": _sig("ACCELEROMETER", "X"),
    "acc_y": _sig("ACCELEROMETER", "Y"),
    "acc_z": _sig("ACCELEROMETER", "Z"),
    "grav_x": _sig("GRAVITY", "X"),
    "grav_y": _sig("GRAVITY", "Y"),
    "grav_z": _sig("GRAVITY", "Z"),
    "gyr_x": _sig("GYROSCOPE", "X"),
    "gyr_y": _sig("GYROSCOPE", "Y"),
    "gyr_z": _sig("GYROSCOPE", "Z"),
    "mag_x": _sig("MAGNETIC", "X"),
    "mag_y": _sig("MAGNETIC", "Y"),
    "mag_z": _sig("MAGNETIC", "Z"),
    "ori_azimuth_deg": _sig("ORIENTATION", "AZIMUTH"),
    "ori_pitch_deg": _sig("ORIENTATION", "PITCH"),
    "ori_roll_deg": _sig("ORIENTATION", "ROLL"),
}

#: Columns without which nothing downstream can run.
S_REQUIRED: frozenset[str] = frozenset(
    {
        "gps_lat_deg",
        "gps_lon_deg",
        "gps_speed_kmh",
        "gps_satellites_raw",
        "time_ms",
        "acc_x",
        "acc_y",
        "acc_z",
        "gyr_x",
        "gyr_y",
        "gyr_z",
    }
)

#: Sensor columns the PS scope permits us to *use* in the estimator.
#: Magnetometer, gravity (a fused output) and the phone's own orientation
#: estimate are loaded so they can be used as ground-truth aids and ablations,
#: but must never enter the shipped signal path. See PLAN.md:13.
PS_SCOPED_INPUTS: frozenset[str] = frozenset(
    {"acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z"}
)

#: Loaded, but out of PS scope for the estimator. Ablation / reference only.
OUT_OF_PS_SCOPE: frozenset[str] = frozenset(
    {
        "mag_x", "mag_y", "mag_z",
        "grav_x", "grav_y", "grav_z",
        "ori_azimuth_deg", "ori_pitch_deg", "ori_roll_deg",
    }
)

KMH_TO_MS = 1.0 / 3.6
