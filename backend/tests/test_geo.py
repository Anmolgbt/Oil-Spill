"""Geographic helpers, against values that do not depend on our own code."""
import math

from services.geo import (EARTH_RADIUS_KM, bearing_deg, destination,
                          haversine_km, km_per_deg_lon)


def test_haversine_zero_distance():
    assert haversine_km(28.5, -94.8, 28.5, -94.8) == 0.0


def test_haversine_one_degree_of_latitude():
    """One degree of latitude is a fixed arc: R * pi / 180, anywhere on Earth."""
    expected = EARTH_RADIUS_KM * math.pi / 180
    assert haversine_km(0, 0, 1, 0) == pytest_approx(expected)
    assert haversine_km(45, -94, 46, -94) == pytest_approx(expected)


def test_haversine_is_symmetric():
    a = haversine_km(28.4968, -94.8322, 28.4585, -94.7887)
    b = haversine_km(28.4585, -94.7887, 28.4968, -94.8322)
    assert a == pytest_approx(b)


def test_bearing_cardinal_directions():
    assert bearing_deg(0, 0, 1, 0) == pytest_approx(0.0, abs=1e-6)      # north
    assert bearing_deg(0, 0, 0, 1) == pytest_approx(90.0, abs=1e-6)     # east
    assert bearing_deg(1, 0, 0, 0) == pytest_approx(180.0, abs=1e-6)    # south


def test_destination_round_trips_through_haversine():
    """Travelling d km on a bearing should land d km away."""
    lat, lon = destination(28.5, -94.8, 12.5, 135.0)
    assert haversine_km(28.5, -94.8, lat, lon) == pytest_approx(12.5, abs=0.01)


def test_km_per_deg_lon_shrinks_with_latitude():
    assert km_per_deg_lon(0) > km_per_deg_lon(45) > km_per_deg_lon(80)
    assert km_per_deg_lon(0) == pytest_approx(111.320)


def pytest_approx(value, abs=None, rel=1e-9):
    import pytest
    return pytest.approx(value, abs=abs, rel=None if abs else rel)
