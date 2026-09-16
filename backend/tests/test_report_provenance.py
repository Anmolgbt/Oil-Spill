"""
What the report has to be able to say about itself.

The report is the take-away artefact: read after the screen is gone, by someone
who did not watch the investigation. Two things it must carry, and both live in
the backend so the report cannot restate them into something else.

  1. Provenance a reader could use to reproduce or dispute the run — including
     the SIMULATION SEED, because which vessels carry an oil-positive tile is a
     seeded assignment and a report that omitted it would let a reader take the
     detection scenario for an observation.
  2. Enough per-candidate counterfactual detail to list EVERY test, not only the
     ones someone happened to click. An omitted exculpatory result is
     indistinguishable from an absent one.
"""
import pytest

from services.fleet_pipeline import run_fleet_scan


@pytest.fixture(scope="module")
def t3():
    return run_fleet_scan("t3")


def test_provenance_carries_what_a_reader_needs_to_reproduce_the_run(t3):
    p = t3["provenance"]

    assert p["simulation_seed"] == 42
    assert "never attribution ground truth" in p["simulation_note"]
    assert p["ais_dataset"]["vessels_in_corpus"] == 347
    assert p["ais_dataset"]["monitored"] == 12
    # The demo's weakest claim, stated rather than left for a reader to discover.
    assert p["ais_dataset"]["co_presence"] == "constructed"
    assert "recycled" in p["sar_input"]["source"]
    assert p["oil_detection"]["model_version"] and p["anomaly_detection"]["model_version"]


def test_every_candidate_carries_its_counterfactual_verdict(t3):
    """
    The report builds its counterfactual section from these, so a candidate
    missing one would be silently dropped from the record.
    """
    for spill in t3["spills"]:
        assert spill["candidates"], "the demo detections both have candidates"
        for graded in spill["evidence"]["candidates"]:
            cf = graded["streams"]["counterfactual"]
            assert cf["grade"] != "UNAVAILABLE", f"{graded['name']} has no counterfactual"
            assert cf["miss_km"] is not None
            assert cf["threshold_km"]
            assert cf["verdict"] in ("consistent", "not consistent")


def test_the_weak_detection_lists_only_exculpatory_verdicts(t3):
    """
    Every candidate on this detection is ruled out. The report must be able to
    show that for all five rather than for whichever ones were clicked.
    """
    graded = t3["spills"][1]["evidence"]["candidates"]
    verdicts = [g["streams"]["counterfactual"]["verdict"] for g in graded]

    assert len(verdicts) == 5
    assert set(verdicts) == {"not consistent"}


def test_the_environment_section_has_a_mode_and_a_reason_to_report(t3):
    env = t3["environment"]
    assert env["environment_mode"] == "fallback"
    assert env["environment_reason"]
    assert env["measured"] is False
