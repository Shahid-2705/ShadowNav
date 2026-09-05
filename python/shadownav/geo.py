"""Geodetic helpers: WGS84 latitude/longitude to a local tangent plane.

Distances here are short (a few km at most within one sequence), so a local
tangent plane about a reference latitude is accurate to well under the errors
being measured. The radii are the proper WGS84 meridional and normal radii of
curvature rather than a single spherical radius. At 53 deg N -- the latitude of
most of IO-VNBD -- they measure 6376234 m and 6391797 m, differing by 0.24%.
Over a 5 km drive that is 12 m, which is larger than the drift being resolved,
so it is not a refinement that can be skipped. Note both exceed the 6371 km
mean radius: at this latitude a single spherical radius is wrong in one
direction for both axes.
"""

from __future__ import annotations

import numpy as np

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


def curvature_radii(lat_deg: float) -> tuple[float, float]:
    """Return ``(meridional, normal)`` radii of curvature in metres."""
    s = np.sin(np.radians(lat_deg))
    denom = 1.0 - WGS84_E2 * s * s
    meridional = WGS84_A * (1.0 - WGS84_E2) / denom**1.5
    normal = WGS84_A / np.sqrt(denom)
    return float(meridional), float(normal)


def lla_to_enu(
    lat_deg: np.ndarray,
    lon_deg: np.ndarray,
    ref_lat_deg: float | None = None,
    ref_lon_deg: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Project latitude/longitude to local east/north metres.

    The reference defaults to the first sample, which makes every sequence start
    at the origin -- convenient, and it keeps the small-angle approximation
    tightest where the data actually is.
    """
    lat_deg = np.asarray(lat_deg, dtype=float)
    lon_deg = np.asarray(lon_deg, dtype=float)
    if ref_lat_deg is None:
        ref_lat_deg = float(lat_deg[0])
    if ref_lon_deg is None:
        ref_lon_deg = float(lon_deg[0])

    m_rad, n_rad = curvature_radii(ref_lat_deg)
    north = np.radians(lat_deg - ref_lat_deg) * m_rad
    east = np.radians(lon_deg - ref_lon_deg) * n_rad * np.cos(np.radians(ref_lat_deg))
    return east, north


def path_length(east: np.ndarray, north: np.ndarray) -> float:
    """Total along-path distance in metres."""
    return float(np.sum(np.hypot(np.diff(east), np.diff(north))))


def wrap_angle(a: np.ndarray | float) -> np.ndarray | float:
    """Wrap radians to ``(-pi, pi]``."""
    return (np.asarray(a) + np.pi) % (2.0 * np.pi) - np.pi


def heading_from_track(
    east: np.ndarray, north: np.ndarray, *, min_step_m: float = 0.5
) -> np.ndarray:
    """Course over ground in radians, measured clockwise from north.

    Consecutive differencing is not usable on IO-VNBD truth: the GPS fix holds
    for a median of 9 s, so 8 rows in 9 differ by exactly zero and
    ``arctan2(0, 0)`` returns 0 -- a due-north course for a vehicle heading
    anywhere. That silently zeroes every cross-track error.

    So the course is taken between successive *distinct* positions at least
    ``min_step_m`` apart, then held forward across the repeats, which is what
    the underlying data actually supports.
    """
    east = np.asarray(east, dtype=float)
    north = np.asarray(north, dtype=float)
    n = east.size
    if n < 2:
        return np.zeros(n)

    moved = np.flatnonzero(
        np.hypot(np.diff(east), np.diff(north)) >= min_step_m
    )
    if moved.size == 0:
        return np.zeros(n)

    head = np.zeros(n)
    for a, b in zip(moved[:-1], moved[1:]):
        head[a : b] = np.arctan2(east[b] - east[a], north[b] - north[a])
    first, last = int(moved[0]), int(moved[-1])
    head[last:] = np.arctan2(east[last] - east[first], north[last] - north[first])         if moved.size == 1 else head[last - 1]
    head[:first] = head[first] if first < n else 0.0
    return head
