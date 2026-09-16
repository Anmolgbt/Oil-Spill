"""
The counterfactual, run both ways — and the threshold correction that came with
it.

Three things are pinned:

  1. The environment-aware run closes at the environment-aware source, the way
     the legacy pair closes at the legacy one. Without that the two modes are
     not answering the same question and the comparison is meaningless.
  2. Each mode is judged against the envelope ITS OWN drift implies. The shipped
     test used to be judged against the map's affected-area circle, which is
     sized by a different vector — a parcel of oil moved one way and measured
     against how far it could have gone another way.
  3. That correction changes no verdict on t3. Pinned so a future edit to the
     threshold that DOES change one cannot pass quietly.

Neither mode is asserted to be right. With no dataset committed the
environment-aware run is a different assumption, not an observation, and
agreement between two unmeasured assumptions is not corroboration.
"""
import pytest

from services.counterfactual import (consistency_radius_km,
                                     test_candidate as run_counterfactual)
from services.fleet_pipeline import load_fleet, run_fleet_scan
from services.investigation import HINDCAST_DRIFT_SPEED_KMH

CLOSURE_TOLERANCE_KM = 0.01


@pytest.fixture(scope="module")
def t3():
    scan = run_fleet_scan("t3")
    ships = {s["mmsi"]: s for s in load_fleet()["ships"]}
    return scan, ships


def _run(t3, spill_index, name):
    scan, ships = t3
    sp = scan["spills"][spill_index]
    candidate = next(c for c in sp["candidates"] if c["name"] == name)
    return run_counterfactual(
        ships[candidate["mmsi"]], sp["age"]["release_at"],
        sp["spill"]["latitude"], sp["spill"]["longitude"],
        sp["age"]["estimated_hours"],
        affected_area_radius_km=sp["affected_area"]["radius_km"])


def test_the_environment_aware_run_closes_at_the_environment_aware_source(t3):
    """A probe on that source must reproduce the observation, as the legacy
    pair does on its own source. Otherwise the two modes disagree about what
    question is being asked."""
    scan, _ = t3
    sp = scan["spills"][0]
    lat, lon = sp["spill"]["latitude"], sp["spill"]["longitude"]
    src = sp["source_environmental"]

    probe = {"id": "p", "mmsi": 1, "name": "AT-ENV-SOURCE",
             "track": [{"time": sp["age"]["release_at"],
                        "lat": src["latitude"], "lon": src["longitude"]}]}
    env = run_counterfactual(probe, sp["age"]["release_at"], lat, lon,
                             sp["age"]["estimated_hours"])["environmental"]
    assert env["miss_distance_km"] == pytest.approx(0.0, abs=CLOSURE_TOLERANCE_KM)


def test_each_mode_is_judged_against_its_own_drift(t3):
    """
    The correction. The legacy threshold is now the hindcast's own reach, not
    the map's circle, and the two are genuinely different numbers.
    """
    r = _run(t3, 0, "MR CANOPUS")
    assert r["consistency_radius_km"] == consistency_radius_km(4) == 6.0
    assert r["consistency_radius_km"] == HINDCAST_DRIFT_SPEED_KMH * 4
    # The map circle is still reported, and is still the other number.
    assert r["affected_area_radius_km"] == 5.58
    assert r["consistency_radius_km"] != r["affected_area_radius_km"]
    # The environment-aware run has its own, from its own drift.
    assert r["environmental"]["consistency_radius_km"] != r["consistency_radius_km"]


def test_the_threshold_correction_changed_no_verdict(t3):
    """
    Measured before the change and pinned after it. 6.26 and 6.23 km sat outside
    5.58 and still sit outside 6.00; nothing crossed.
    """
    scan, ships = t3
    for sp in scan["spills"]:
        for c in sp["candidates"]:
            r = run_counterfactual(ships[c["mmsi"]], sp["age"]["release_at"],
                                   sp["spill"]["latitude"], sp["spill"]["longitude"],
                                   sp["age"]["estimated_hours"])
            old = r["miss_distance_km"] <= 5.58     # the pre-correction threshold
            assert r["within_envelope"] == old, (
                f"{c['name']} changed verdict when the threshold moved to 6.00 km")


def test_both_modes_agree_on_t3_while_the_margins_invert(t3):
    """
    The finding this phase exists to surface. Same verdict, opposite confidence:
    the shipped top candidate is consistent by 3.12 km one way and 0.06 km the
    other, and the vessel that best reproduces the observation changes.
    """
    canopus = _run(t3, 0, "MR CANOPUS")
    achilleas = _run(t3, 0, "ACHILLEAS")

    for r in (canopus, achilleas):
        assert r["mode_comparison"]["verdicts_agree"] is True
        assert r["within_envelope"] is True and r["environmental"]["within_envelope"] is True

    assert canopus["miss_distance_km"] == pytest.approx(2.88, abs=0.01)
    assert canopus["environmental"]["miss_distance_km"] == pytest.approx(5.53, abs=0.01)
    assert canopus["mode_comparison"]["legacy"]["margin_km"] == pytest.approx(3.12, abs=0.01)
    assert canopus["environmental"]["margin_km"] == pytest.approx(0.06, abs=0.01)

    # Legacy says MR CANOPUS reproduces the observation best; the other way round
    # it is ACHILLEAS. Neither is validated.
    assert achilleas["miss_distance_km"] > canopus["miss_distance_km"]
    assert achilleas["environmental"]["miss_distance_km"] < canopus["environmental"]["miss_distance_km"]


def test_no_dataset_is_reported_as_an_assumption_not_a_measurement(t3):
    env = _run(t3, 0, "MR CANOPUS")["environmental"]
    assert env["environment_mode"] == "fallback"
    assert env["environment_reason"]
    assert "not a measured field" in env["note"]
