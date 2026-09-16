"""
The environment service, and the guarantee that matters most: the app runs
fully without a dataset.

No dataset is committed, so `fallback` is the shipped state rather than an edge
case, and the first test here is the one that has to keep passing forever. The
historical path is exercised against a SYNTHETIC fixture under tests/data/ —
four nodes at two times, values chosen so a midpoint is checkable by eye. It is
not data and is deliberately not stored where the app would find it.

Nothing here asserts that a reanalysis would be correct. It asserts that the
service reads one faithfully, refuses to extrapolate past its edges, and never
passes an assumption off as an observation.
"""
from pathlib import Path

import pytest

from services import environment as env
from services.damage import drift_vector

FIXTURE = Path(__file__).parent / "data" / "synthetic_environment_grid.csv"


@pytest.fixture
def grid():
    """Point the service at the synthetic grid, and put it back afterwards."""
    env.reset_provider_cache()
    provider = env.GridFileProvider(FIXTURE)
    original = env._grid_provider
    env._grid_provider = lambda: (provider, None)
    yield provider
    env._grid_provider = original
    env.reset_provider_cache()


def test_without_a_dataset_the_service_still_answers_and_says_why():
    """The shipped state. This test failing means the demo cannot run."""
    result = env.get_conditions(28.5, -94.9, "2021-03-28T21:39:59Z")

    assert result["environment_mode"] == "fallback"
    assert result["measured"] is False
    assert "PROVENANCE.md" in result["environment_reason"]
    # The fallback drift must be the assumed drift the rest of the app uses —
    # not a second, subtly different vector.
    assert result["drift"]["speed_kmh"] == drift_vector()["speed_kmh"]
    assert result["drift"]["direction_deg"] == drift_vector()["direction_deg"]
    assert result["current"]["measured"] is False and result["wind"]["measured"] is False


def test_drift_vector_is_unchanged_by_the_shared_arithmetic():
    """
    combine_current_and_wind() was lifted out of drift_vector(). The envelope,
    the search radius and every driver figure depend on this value, so it is
    pinned rather than trusted.
    """
    d = drift_vector()
    assert (d["speed_kmh"], d["direction_deg"]) == (1.394, 181.2)


def test_a_point_on_a_grid_node_returns_that_node(grid):
    """No interpolation error where there is nothing to interpolate."""
    r = env.get_conditions(28.0, -95.0, "2021-03-28T12:00:00Z")

    assert r["environment_mode"] == "historical"
    assert r["measured"] is True
    assert r["environment_reason"] is None
    # uo=0.1, vo=0 -> 0.1 m/s due east (bearing 90).
    assert r["current"] == {"speed_ms": 0.1, "direction_deg": 90.0, "measured": True}
    assert r["wind"] == {"speed_ms": 1.0, "direction_deg": 90.0, "measured": True}


def test_interpolation_between_nodes_is_the_mean(grid):
    """Midway in space and midway in time, both checkable by hand."""
    # Spatial: centre of the square at t=12:00. uo corners 0.1/0.3/0.5/0.7 -> 0.4.
    middle = env.get_conditions(28.5, -94.5, "2021-03-28T12:00:00Z")
    assert middle["current"]["speed_ms"] == pytest.approx(0.4, abs=1e-6)

    # Temporal: same node, halfway between the 12:00 and 18:00 slices.
    # uo goes 0.1 -> 1.1, so the midpoint is 0.6.
    half = env.get_conditions(28.0, -95.0, "2021-03-28T15:00:00Z")
    assert half["current"]["speed_ms"] == pytest.approx(0.6, abs=1e-6)
    # Wind is identical in both slices, so it must not move with time.
    assert half["wind"]["speed_ms"] == pytest.approx(1.0, abs=1e-6)


def test_outside_coverage_falls_back_rather_than_extrapolating(grid):
    """A value invented past the data's edge looks like data. Refuse instead."""
    for lat, lon, when in [(27.0, -94.5, "2021-03-28T12:00:00Z"),   # south of it
                           (28.5, -90.0, "2021-03-28T12:00:00Z"),   # east of it
                           (28.5, -94.5, "2021-03-29T12:00:00Z")]:  # after it
        r = env.get_conditions(lat, lon, when)
        assert r["environment_mode"] == "fallback"
        assert "outside the dataset's coverage" in r["environment_reason"]
        assert r["drift"]["speed_kmh"] == drift_vector()["speed_kmh"]


def test_a_scan_reports_the_mode_without_changing_any_figure():
    """
    This phase adds the mode to the payload and nothing else. The drift, and so
    the envelope and the search radius, must be exactly what they were.
    """
    from services.fleet_pipeline import run_fleet_scan

    scan = run_fleet_scan("t3")
    block = scan["environment"]
    assert block["environment_mode"] == "fallback"
    assert block["environment_reason"]
    assert block["measured"] is False
    assert block["drift"]["speed_kmh"] == 1.394
    assert scan["spills"][0]["affected_area"]["radius_km"] == 5.58
