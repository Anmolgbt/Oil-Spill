"""
Environment-aware drift: the two properties that must hold, and one that must
not be quietly lost.

  1. In a uniform field the integration reduces to a single straight
     application of the environment's own vector. If it did not, "fallback"
     would silently mean something different from the stated constants.
  2. Forward-then-backward closes. The counterfactual's whole meaning rests on
     the backward run being the exact inverse of the forward one, and with a
     varying field that is a property of the SCHEME, not a given — the naive
     explicit backward step leaves 1.28 km at 4 h and refining the step does
     not help.
  3. The legacy hindcast and forecast are untouched and still differ from the
     environment-aware ones. That separation is real and is asserted, so it
     cannot be mistaken for a bug later.

Nothing here says either estimate is correct. Neither is validated.
"""
import math
from pathlib import Path

import pytest

from services import drift, environment as env
from services.damage import drift_vector
from services.fleet_pipeline import hindcast_over
from services.geo import haversine_km
from services.investigation import forecast

FIXTURE = Path(__file__).parent / "data" / "synthetic_environment_grid.csv"
LAT, LON, WHEN, HOURS = 28.45853, -94.78875, "2021-03-28T21:39:59Z", 4


@pytest.fixture
def varying_field():
    """The synthetic grid — a field that actually changes, which is the only
    condition under which closure is in danger."""
    env.reset_provider_cache()
    provider = env.GridFileProvider(FIXTURE)
    original = env._grid_provider
    env._grid_provider = lambda: (provider, None)
    yield
    env._grid_provider = original
    env.reset_provider_cache()


def test_a_uniform_field_reduces_to_one_straight_step():
    """N equal steps through an unchanging field must sum to the single line."""
    run = drift.integrate(LAT, LON, WHEN, HOURS, backward=True)
    assert run["environment_mode"] == "fallback"

    d = drift_vector()
    theta = math.radians(d["direction_deg"])
    distance = d["speed_kmh"] * HOURS
    one_lat = LAT - distance * math.cos(theta) / drift.KM_PER_DEG
    one_lon = LON - distance * math.sin(theta) / (drift.KM_PER_DEG
                                                  * math.cos(math.radians(LAT)))
    assert haversine_km(run["latitude"], run["longitude"], one_lat, one_lon) < 1e-9


def test_closure_holds_in_a_varying_field_at_every_step_size(varying_field):
    """
    The property the implicit backward step exists for. The naive explicit step
    left 1.28 km here, identically at 60-minute and 1-minute steps.
    """
    original = drift.STEP_MINUTES
    try:
        for step in (60, 30, 5):
            drift.STEP_MINUTES = step
            r = drift.closure_residual_km(28.5, -94.5, "2021-03-28T16:00:00Z", 4)
            assert r["environment_mode"] == "historical", "fixture must cover this"
            assert r["residual_km"] == pytest.approx(0.0, abs=1e-3)
    finally:
        drift.STEP_MINUTES = original


def test_closure_in_fallback_stays_far_inside_the_counterfactual_tolerance():
    """~10 cm, from each run holding cos(lat) at its own start latitude."""
    r = drift.closure_residual_km(LAT, LON, WHEN, HOURS)
    assert r["environment_mode"] == "fallback"
    assert r["residual_km"] < 0.01  # the counterfactual's own tolerance


def test_the_legacy_path_is_untouched_and_the_two_estimates_differ():
    """
    Both paths must remain obtainable, and they must not silently converge:
    the legacy vectors were never derived from the stated wind and current.
    """
    legacy = hindcast_over(LAT, LON, HOURS)
    aware = drift.hindcast_environmental(LAT, LON, WHEN, HOURS)

    assert legacy["drift_speed_kmh"] == 1.5 and legacy["drift_direction_deg"] == 135.0
    separation = haversine_km(legacy["latitude"], legacy["longitude"],
                              aware["latitude"], aware["longitude"])
    assert separation == pytest.approx(4.56, abs=0.01)
    # Neither is asserted to be right.
    assert aware["confirmed"] is False and aware["confidence"] is None
    assert aware["environmental_data_used"] is False  # no dataset committed


def test_forecast_horizons_are_read_off_one_path():
    """
    Each horizon must lie on the path the longest one traced — running them as
    separate integrations would let +12 h sit somewhere +24 h never passed.
    """
    aware = drift.forecast_environmental(LAT, LON, WHEN, [6, 12, 24, 48])
    assert [p["hours_ahead"] for p in aware["points"]] == [6, 12, 24, 48]
    for p in aware["points"]:
        on_path = any(abs(q["hours"] - p["hours_ahead"]) < 1e-6
                      and q["latitude"] == p["latitude"] for q in aware["path"])
        assert on_path, f"+{p['hours_ahead']}h is not a point on the integrated path"

    legacy = forecast(LAT, LON)
    apart = haversine_km(legacy["points"][-1]["latitude"], legacy["points"][-1]["longitude"],
                         aware["points"][-1]["latitude"], aware["points"][-1]["longitude"])
    assert apart == pytest.approx(18.98, abs=0.05)


def test_a_partly_covered_path_is_reported_as_fallback(varying_field):
    """
    One fallback sample mid-track makes the whole path a hybrid. Calling that
    historical would misstate the provenance of the result.
    """
    # The fixture covers 12:00-18:00 only; 8 h back from 16:00 leaves it.
    run = drift.integrate(28.5, -94.5, "2021-03-28T16:00:00Z", 8, backward=True)
    assert run["environment_mode"] == "fallback"
    assert run["environment_reason"]
    assert len(run["environment_sources"]) == 2  # both providers answered
