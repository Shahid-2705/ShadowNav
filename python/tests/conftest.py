"""Byte-accurate IO-VNBD fixtures.

The point of this file is that the loader must be testable with no download.
Every hazard documented in research/SIH26168-open-track-findings.md Track H is
reproduced here at the byte level, plus two found by inspecting the real file
`S-Vta10.csv` on 2026-09-05 that Track H did not record:

  * CRLF line endings
  * an internal trailing space inside ``ORIENTATION (Roll )``

The header below is a verbatim transcription of the real S-side header, with the
unit symbols written as the latin-1 bytes they actually are (0xB0 degree,
0xB2 superscript two, 0xB5 micro). Note that the degree and micro symbols happen
to arrive as valid UTF-8 two-byte sequences while the superscript two does not --
that mixture is exactly why ``encoding='latin-1'`` is mandatory rather than
merely convenient.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

# Real header, byte for byte. Deliberately NOT built by joining a list of clean
# names: the whitespace irregularity is the thing under test.
#   - most columns carry a leading space, but "GPS SATELLITES IN RANGE" does not
#   - "ACCELEROMETER X (m/s2) " carries a *trailing* space
#   - "ORIENTATION (Roll )" carries a space before the closing paren
S_HEADER_LATIN1 = (
    b"GPS LATITUDE (degrees), GPS LONGITUDE (degrees), GPS ALTITUDE (m),"
    b" GPS SPEED (Kmh), GPS ACCURACY (m), GPS ORIENTATION (\xc2\xb0),"
    b"GPS SATELLITES IN RANGE, TIME SINCE START (ms),"
    b" DATE (YYYY-MO-DD HH-MI-SS_SSS),"
    b" ACCELEROMETER X (m/s\xb2) , ACCELEROMETER Y (m/s\xb2),"
    b" ACCELEROMETER Z (m/s\xb2), GRAVITY X (m/s\xb2), GRAVITY Y (m/s\xb2),"
    b" GRAVITY Z (m/s\xb2), GYROSCOPE X (rad/s), GYROSCOPE Y (rad/s),"
    b" GYROSCOPE Z (rad/s), MAGNETIC FIELD X (\xc2\xb5T),"
    b" MAGNETIC FIELD Y (\xc2\xb5T), MAGNETIC FIELD Z (\xc2\xb5T),"
    b" ORIENTATION (Azimuth) (\xc2\xb0), ORIENTATION (Pitch) (\xc2\xb0),"
    b" ORIENTATION (Roll ) (\xc2\xb0)"
)

SAMPLE_HZ = 10.0
GPS_HZ = 1.0
GPS_REPEAT = int(SAMPLE_HZ / GPS_HZ)  # 10 rows share one fix


def synth_s_rows(
    n_rows: int = 300,
    *,
    lat0: float = 52.881744,
    lon0: float = -1.717480,
    speed_kmh: float = 36.0,
    heading_deg: float = 90.0,
    yaw_rate_dps: float = 0.0,
    seed: int = 20260905,
) -> list[bytes]:
    """Synthesise physically coherent S-side rows.

    Straight-line or constant-yaw-rate motion at a fixed speed, with the GPS
    block-repeat structure of the real files. Coherent enough that a strapdown
    integration of the accelerometer and gyroscope columns reproduces the GPS
    track, which is what makes the baseline tests meaningful.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / SAMPLE_HZ
    speed_ms = speed_kmh / 3.6
    yaw_rate = math.radians(yaw_rate_dps)

    # Local tangent plane scale factors at lat0 (WGS84).
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    s = math.sin(math.radians(lat0))
    n_rad = a / math.sqrt(1 - e2 * s * s)
    m_rad = a * (1 - e2) / (1 - e2 * s * s) ** 1.5

    rows: list[bytes] = []
    east = north = 0.0
    heading = math.radians(heading_deg)
    t0_ms = 956512

    # GPS values are held for GPS_REPEAT rows, then refreshed from the truth.
    held: tuple[float, float, float, float] | None = None

    for i in range(n_rows):
        if i % GPS_REPEAT == 0:
            held = (
                lat0 + math.degrees(north / m_rad),
                lon0 + math.degrees(east / (n_rad * math.cos(math.radians(lat0)))),
                122.15,
                speed_kmh,
            )
        assert held is not None
        lat, lon, alt, spd = held

        # Body frame: x right, y forward, z up. Nav frame ENU. `heading` is
        # clockwise from north, so psi_dot = +yaw_rate here, and because ENU is
        # right-handed about up, the *gyroscope* reads the opposite sign:
        # gyr_z = -psi_dot. Specific force on x is the centripetal term
        # v * psi_dot; gravity appears as +g on body up.
        acc_x = speed_ms * yaw_rate + rng.normal(0, 0.02)
        acc_y = rng.normal(0, 0.02)
        acc_z = 9.80665 + rng.normal(0, 0.02)
        gyr_z = -yaw_rate + rng.normal(0, 0.001)

        azimuth = (math.degrees(heading)) % 360.0
        row = (
            f"{lat:.6f},{lon:.6f},{alt:.2f},{spd:.2f},4,{azimuth:.2f},22 / 22,"
            f"{t0_ms + i * 100},2019-11-06 12:01:50:393,"
            f"{acc_x:.4f},{acc_y:.4f},{acc_z:.4f},"
            f"0.0572,-0.0702,9.8061,"
            f"{rng.normal(0, 0.001):.4f},{rng.normal(0, 0.001):.4f},{gyr_z:.4f},"
            f"2.69,-37.12,11.06,"
            f"{azimuth:.2f},-80.16,148.59"
        ).encode("latin-1")
        rows.append(row)

        heading += yaw_rate * dt
        east += speed_ms * math.sin(heading) * dt
        north += speed_ms * math.cos(heading) * dt

    return rows


def write_s_csv(path: Path, rows: list[bytes]) -> Path:
    """Write a fixture with the real file's latin-1 encoding and CRLF endings."""
    body = b"\r\n".join([S_HEADER_LATIN1, *rows]) + b"\r\n"
    path.write_bytes(body)
    return path


@pytest.fixture
def s_csv_straight(tmp_path: Path) -> Path:
    """300 rows (30 s) of straight-line driving at 36 km/h due east."""
    return write_s_csv(tmp_path / "S-Fixture01.csv", synth_s_rows())


@pytest.fixture
def s_csv_turning(tmp_path: Path) -> Path:
    """300 rows of a constant 6 deg/s left turn -- exercises the centripetal path."""
    return write_s_csv(
        tmp_path / "S-Fixture02.csv",
        synth_s_rows(yaw_rate_dps=6.0, seed=7),
    )
