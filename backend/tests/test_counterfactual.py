"""
The inverse-closure tripwire.

The counterfactual runs the hindcast's drift vector FORWARD from a vessel's real
position. For that to mean anything it must be the exact inverse of the hindcast
that produced the source estimate: a probe placed at the estimated source has to
reproduce the observed spill. If it does not, every miss distance is polluted by
method mismatch rather than measuring the vessel.

This is the test that guards any change to the geodesy or the drift arithmetic.
TOLERANCE IS 0.01 km (10 m), and it is that tight on purpose — the two sides use
the identical flat-earth formula with the sign reversed, so the residual should
be floating-point noise, not an approximation error. A change that needs a looser
tolerance has broken the property, not merely perturbed it.
"""
import pytest

# Aliased: pytest would otherwise collect the imported `test_candidate`
# as a test case, because its name begins with `test_`.
from services.counterfactual import test_candidate as run_counterfactual
from services.fleet_pipeline import hindcast_over

CLOSURE_TOLERANCE_KM = 0.01


def test_probe_at_estimated_source_reproduces_the_observation():
    spill_lat, spill_lon, age = 28.4585, -94.7887, 4
    source = hindcast_over(spill_lat, spill_lon, age)
    release = "2021-03-28T17:39:59Z"

    probe = {"id": "probe", "mmsi": 1, "name": "AT-SOURCE",
             "track": [{"time": release,
                        "lat": source["latitude"], "lon": source["longitude"]}]}
    result = run_counterfactual(probe, release, spill_lat, spill_lon, age,
                            envelope_radius_km=5.58, source=source)

    assert result["available"] is True
    assert result["miss_distance_km"] == pytest.approx(0.0, abs=CLOSURE_TOLERANCE_KM)


@pytest.mark.parametrize("age_hours", [2, 4, 8])
def test_closure_holds_at_other_spill_ages(age_hours):
    """The envelope and drift distance both scale with age; closure must not."""
    spill_lat, spill_lon = 28.50, -94.90
    source = hindcast_over(spill_lat, spill_lon, age_hours)
    release = "2021-03-28T12:00:00Z"
    probe = {"id": "p", "mmsi": 2, "name": "P",
             "track": [{"time": release,
                        "lat": source["latitude"], "lon": source["longitude"]}]}
    r = run_counterfactual(probe, release, spill_lat, spill_lon, age_hours,
                       envelope_radius_km=1.0, source=source)
    assert r["miss_distance_km"] == pytest.approx(0.0, abs=CLOSURE_TOLERANCE_KM)


def test_a_distant_vessel_is_not_consistent():
    """A vessel far from the source must miss by far more than the envelope."""
    spill_lat, spill_lon, age = 28.4585, -94.7887, 4
    source = hindcast_over(spill_lat, spill_lon, age)
    far = {"id": "far", "mmsi": 3, "name": "FAR",
           "track": [{"time": "2021-03-28T17:39:59Z", "lat": 28.62, "lon": -95.15}]}
    r = run_counterfactual(far, "2021-03-28T17:39:59Z", spill_lat, spill_lon, age,
                       envelope_radius_km=5.58, source=source)
    assert r["miss_distance_km"] > 5.58
    assert r["within_envelope"] is False


def test_no_ais_fix_is_reported_not_guessed():
    empty = {"id": "e", "mmsi": 4, "name": "NO FIXES", "track": []}
    r = run_counterfactual(empty, "2021-03-28T17:39:59Z", 28.4585, -94.7887, 4)
    assert r["available"] is False
    assert "reason" in r
