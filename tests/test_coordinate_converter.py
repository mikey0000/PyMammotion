"""Unit tests for CoordinateConverter.enu_to_lla.

Validates against pymap3d (https://pymap3d.readthedocs.io/), the reference
implementation of ENU ↔ geodetic conversions based on Bowring's method and
the WGS-84 ellipsoid.

Call-site convention
--------------------
The function signature is ``enu_to_lla(east, north)`` but the implementation
internally swaps the two components in the matrix multiply.  All call sites in
the codebase compensate for this by passing ``(north_value, east_value)``
— i.e. north first, east second — so the two inversions cancel and the result
is correct.  These tests document and verify that contract for both hemispheres.
"""
from __future__ import annotations

import math

import pymap3d
import pytest

from pymammotion.utility.map import CoordinateConverter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOLERANCE_DEG = 1e-6  # ~0.1 m at the equator


def _check(lat_deg: float, lon_deg: float, east_m: float, north_m: float, label: str) -> None:
    """Assert CoordinateConverter matches pymap3d for a given ENU offset."""
    ref_lat, ref_lon, _ = pymap3d.enu2geodetic(east_m, north_m, 0.0, lat_deg, lon_deg, 0.0)

    conv = CoordinateConverter(math.radians(lat_deg), math.radians(lon_deg))
    # Call convention: pass (north, east) — compensates for the internal swap.
    result = conv.enu_to_lla(north_m, east_m)

    assert abs(result.latitude - ref_lat) < _TOLERANCE_DEG, (
        f"{label}: latitude {result.latitude:.8f} != ref {ref_lat:.8f}"
    )
    assert abs(result.longitude - ref_lon) < _TOLERANCE_DEG, (
        f"{label}: longitude {result.longitude:.8f} != ref {ref_lon:.8f}"
    )


# ---------------------------------------------------------------------------
# Northern hemisphere (Germany, lat ≈ +54°)
# ---------------------------------------------------------------------------

NORTH_LAT = 54.079261
NORTH_LON = 12.369534


def test_northern_pure_east() -> None:
    _check(NORTH_LAT, NORTH_LON, 10.0, 0.0, "northern pure east")


def test_northern_pure_north() -> None:
    _check(NORTH_LAT, NORTH_LON, 0.0, 10.0, "northern pure north")


def test_northern_west_south() -> None:
    _check(NORTH_LAT, NORTH_LON, -5.0, -8.0, "northern west+south")


def test_northern_mixed() -> None:
    _check(NORTH_LAT, NORTH_LON, 7.3, -4.1, "northern mixed")


def test_northern_origin() -> None:
    """enu_to_lla(0, 0) must return the reference RTK position exactly."""
    conv = CoordinateConverter(math.radians(NORTH_LAT), math.radians(NORTH_LON))
    result = conv.enu_to_lla(0.0, 0.0)
    assert abs(result.latitude - NORTH_LAT) < _TOLERANCE_DEG
    assert abs(result.longitude - NORTH_LON) < _TOLERANCE_DEG


# ---------------------------------------------------------------------------
# Southern hemisphere (New Zealand, lat ≈ -38°)
# ---------------------------------------------------------------------------

SOUTH_LAT = -38.002342
SOUTH_LON = 175.317709


def test_southern_pure_east() -> None:
    _check(SOUTH_LAT, SOUTH_LON, 10.0, 0.0, "southern pure east")


def test_southern_pure_north() -> None:
    _check(SOUTH_LAT, SOUTH_LON, 0.0, 10.0, "southern pure north")


def test_southern_west_south() -> None:
    _check(SOUTH_LAT, SOUTH_LON, -5.0, -8.0, "southern west+south")


def test_southern_mixed() -> None:
    _check(SOUTH_LAT, SOUTH_LON, 7.3, -4.1, "southern mixed")


def test_southern_origin() -> None:
    conv = CoordinateConverter(math.radians(SOUTH_LAT), math.radians(SOUTH_LON))
    result = conv.enu_to_lla(0.0, 0.0)
    assert abs(result.latitude - SOUTH_LAT) < _TOLERANCE_DEG
    assert abs(result.longitude - SOUTH_LON) < _TOLERANCE_DEG
