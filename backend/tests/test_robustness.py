"""
Counterfactual robustness — sensitivity to an assumption, not accuracy.

Three things are worth pinning:

  1. The sweep's baseline reproduces the verdict the counterfactual already
     reported. If the grid's centre disagreed with the answer it is annotating,
     every margin below it would be measured from the wrong place.
  2. The label discriminates. A vessel sitting on the estimated source keeps its
     verdict across the band; one parked on the envelope boundary does not.
  3. Nothing here is dressed up as a probability or an accuracy, and the whole
     sweep is not returned.

None of this says the verdict is CORRECT. It says how much the verdict depends
on a drift vector nobody measured.
"""
import pytest

from services.counterfactual import (MODERATE_AGREEMENT, ROBUST_AGREEMENT,
                                     test_candidate as run_counterfactual)
from services.fleet_pipeline import hindcast_over
from services.geo import destination

SPILL_LAT, SPILL_LON, AGE = 28.4585, -94.7887, 4
ENVELOPE_KM = 5.58
RELEASE = "2021-03-28T17:39:59Z"
SOURCE = hindcast_over(SPILL_LAT, SPILL_LON, AGE)


def _probe(lat, lon, name="PROBE"):
    return {"id": "p", "mmsi": 99, "name": name,
            "track": [{"time": RELEASE, "lat": lat, "lon": lon}]}


def _run(lat, lon):
    return run_counterfactual(_probe(lat, lon), RELEASE, SPILL_LAT, SPILL_LON,
                              AGE, envelope_radius_km=ENVELOPE_KM, source=SOURCE)


def test_sweep_baseline_reproduces_the_reported_verdict():
    """The grid's centre must be the answer the counterfactual already gave."""
    for lat, lon in [(SOURCE["latitude"], SOURCE["longitude"]),   # consistent
                     (28.62, -95.15)]:                            # not consistent
        r = _run(lat, lon)
        expected = "consistent" if r["within_envelope"] else "not consistent"
        assert r["robustness"]["baseline_verdict"] == expected


def test_a_vessel_on_the_source_holds_its_verdict_across_the_band():
    """Miss ~0 km: the verdict cannot turn on getting the drift exactly right."""
    r = _run(SOURCE["latitude"], SOURCE["longitude"])
    rb = r["robustness"]
    assert r["miss_distance_km"] < 0.01
    assert rb["agreement_fraction"] >= ROBUST_AGREEMENT
    assert rb["classification"] == "robust"


def test_a_vessel_on_the_envelope_boundary_does_not():
    """
    Placed so the simulated slick lands almost exactly ENVELOPE_KM from the
    observation — the verdict is then decided by the drift vector, and a small
    perturbation of it flips the answer.
    """
    lat, lon = destination(SOURCE["latitude"], SOURCE["longitude"], ENVELOPE_KM, 270)
    r = _run(lat, lon)
    rb = r["robustness"]
    assert r["miss_distance_km"] == pytest.approx(ENVELOPE_KM, abs=0.2)
    assert rb["agreement_fraction"] < ROBUST_AGREEMENT
    assert rb["classification"] in ("moderately sensitive", "highly sensitive")
    # A boundary case must flip on the drift vector itself, not only on age.
    assert (rb["flips_at"]["drift_speed_kmh"] or rb["flips_at"]["drift_bearing_deg"])


def test_the_summary_is_a_summary_and_claims_nothing_statistical():
    rb = _run(SOURCE["latitude"], SOURCE["longitude"])["robustness"]
    assert rb["interpretation"] == {"is_accuracy": False, "is_probability": False,
                                    "meaning": rb["interpretation"]["meaning"]}
    # The sweep itself is never returned — only its bounds and the outcome.
    assert set(rb["sweep"]) == {"combinations", "over", "drift_speed_kmh",
                                "drift_bearing_deg", "basis", "not_swept"}
    assert 0.0 <= rb["agreement_fraction"] <= 1.0
    # The thresholds the label was derived from travel with it.
    assert f"{ROBUST_AGREEMENT:.0%}" in rb["rule"]
    assert f"{MODERATE_AGREEMENT:.0%}" in rb["rule"]


def test_the_threshold_is_derived_rather_than_left_to_the_caller():
    """
    This used to assert that omitting the envelope left the verdict and the
    robustness unavailable. That was true, and it was also how the shipped test
    came to be judged against the map's circle — a radius sized by a different
    drift vector than the one it moves oil with. The counterfactual now derives
    its own threshold from its own drift, so there is no caller-shaped hole to
    fall through, and a verdict is always answerable.
    """
    r = run_counterfactual(_probe(SOURCE["latitude"], SOURCE["longitude"]),
                           RELEASE, SPILL_LAT, SPILL_LON, AGE)
    assert r["consistency_radius_km"] == 6.0        # 1.5 km/h x 4 h
    assert r["within_envelope"] is not None
    assert r["robustness"]["available"] is True


def test_robustness_is_unavailable_rather_than_invented_without_a_track():
    """The remaining way it can genuinely have nothing to perturb."""
    empty = {"id": "e", "mmsi": 5, "name": "NO FIXES", "track": []}
    r = run_counterfactual(empty, RELEASE, SPILL_LAT, SPILL_LON, AGE)
    assert r["available"] is False
    assert "reason" in r
