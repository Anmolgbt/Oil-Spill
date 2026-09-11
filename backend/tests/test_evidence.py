"""
Evidence quality, and the system's ability to decline to name anyone.

The case this layer exists for is already in the shipped demo, and both of the
interesting outcomes appear on the same pass — so both are pinned here. If a
future change quietly turns the GRAND DOLPHIN detection back into a confident
accusation, this file fails.

The load-bearing distinction throughout: a grade says HOW MUCH A STREAM CAN TELL
US, not how guilty the vessel is. UNAVAILABLE is therefore never LOW.
"""
import pytest

from services.evidence import (HIGH, LOW, MEDIUM, UNAVAILABLE, grade_behaviour,
                               grade_environment, grade_trajectory)
from services.fleet_pipeline import run_fleet_scan


@pytest.fixture(scope="module")
def t3():
    return run_fleet_scan("t3")


def test_the_weak_detection_declines_to_name_anyone(t3):
    """
    Every candidate on this detection is robustly not-consistent, while the
    ranking still shows a leader at 70.54/100. The system must say so.
    """
    assessment = t3["spills"][1]["evidence"]["assessment"]

    assert assessment["outcome"] == "NO_STRONG_CANDIDATE"
    assert assessment["consistent_count"] == 0
    assert assessment["candidate_count"] == 5
    # The score is not hidden — it is explained.
    assert assessment["leader"]["name"] == "GRAND DOLPHIN"
    assert assessment["leader"]["counterfactual_consistent"] is False
    assert any("70.54" in r for r in assessment["reasons"])
    # And declining to name is about evidence, not innocence.
    assert "innocent" in assessment["means"]


def test_the_unstable_detection_is_not_flattened_into_supported(t3):
    """
    Candidates ARE consistent here, but which one leads depends on the drift
    assumption and the leader's margin is 0.06 km. Calling that "supported"
    would bury two phases of measurement.
    """
    assessment = t3["spills"][0]["evidence"]["assessment"]

    assert assessment["outcome"] == "LEADING_CANDIDATE_UNSTABLE"
    assert assessment["consistent_count"] == 3
    assert any("MR CANOPUS" in r and "NISALAH" in r for r in assessment["reasons"]), \
        "the rank flip must be one of the stated reasons"
    assert any("0.06 km" in r for r in assessment["reasons"]), \
        "the thin margin must be one of the stated reasons"


def test_the_leaders_counterfactual_grade_reads_the_thinner_of_the_two_modes(t3):
    """
    MR CANOPUS holds its legacy verdict by 3.12 km of 6.00 and its
    environment-aware one by 0.06 km of 5.59. Reading only the legacy margin
    would grade it MEDIUM and miss the fragility entirely.
    """
    graded = {g["name"]: g for g in t3["spills"][0]["evidence"]["candidates"]}
    cf = graded["MR CANOPUS"]["streams"]["counterfactual"]

    assert cf["grade"] == LOW
    assert cf["margin_km"] == pytest.approx(3.12, abs=0.01)          # legacy
    assert cf["thinnest_margin_km"] == pytest.approx(0.06, abs=0.01)  # the one that counts
    assert "environment-aware" in cf["thinnest_margin_under"]


def test_a_model_that_could_not_answer_is_unavailable_not_low():
    """Phase 9's guarantee, carried into the grades."""
    for status, reason in [("track_too_short", "Only 1 AIS fix."),
                           ("inference_error", "The model raised."),
                           ("model_unavailable", "No artifact.")]:
        g = grade_behaviour({"behaviour_available": False, "behaviour_status": status,
                             "behaviour_reason": reason})
        assert g["grade"] == UNAVAILABLE, f"{status} must not grade LOW"
        assert g["reason"] == reason

    # A model that ran and found nothing is real evidence, not weak evidence.
    ran = grade_behaviour({"behaviour_available": True, "behaviour_status": "ok",
                           "anomalous_points": 0})
    assert ran["grade"] == HIGH


def test_environmental_coverage_is_unavailable_while_no_dataset_is_committed(t3):
    for spill in t3["spills"]:
        for graded in spill["evidence"]["candidates"]:
            assert graded["streams"]["environment"]["grade"] == UNAVAILABLE
            assert "environment" in graded["unavailable"]

    # And HIGH the moment one is loaded — the grade tracks the data, not a flag
    # someone forgot to flip.
    assert grade_environment("historical")["grade"] == HIGH


def test_trajectory_reads_score_and_status_together(t3):
    """
    A vessel that closed on the source and then left scores high while its
    status says "moving away". Reading either field alone misreports it — on t3
    GRAND DOLPHIN does exactly this at 92.35.
    """
    passed_by = grade_trajectory(92.35, "Moving away / not approaching")
    assert passed_by["grade"] == MEDIUM
    assert "passed the source" in passed_by["reason"]

    assert grade_trajectory(72.84, "Approaching source")["grade"] == HIGH
    assert grade_trajectory(0.0, "Moving away / not approaching")["grade"] == LOW


def test_every_grade_ships_the_rule_that_produced_it(t3):
    """A grade a reader cannot argue with is just another opaque number."""
    for spill in t3["spills"]:
        for graded in spill["evidence"]["candidates"]:
            for name, stream in graded["streams"].items():
                assert stream["rule"], f"{name} has no stated rule"
                assert stream["reason"], f"{name} has no stated reason"
        assert spill["evidence"]["assessment"]["rules"]


def test_the_evidence_layer_does_not_touch_the_ranking(t3):
    """It reads the ranking. A layer that reordered what it describes would be
    describing itself."""
    assert [c["rank"] for c in t3["spills"][0]["candidates"]] == list(range(1, 12))
    assert t3["spills"][0]["candidates"][0]["name"] == "MR CANOPUS"
    assert t3["spills"][0]["candidates"][0]["final_suspect_score"] == pytest.approx(81.87, abs=0.01)
    assert t3["spills"][0]["affected_area"]["radius_km"] == 5.58
    assert t3["spills"][1]["ais"]["funnel"]["within_radius"] == 5
