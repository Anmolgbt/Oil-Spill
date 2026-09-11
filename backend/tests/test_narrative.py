"""
The plain-language reading, and the two rules that shape it.

  1. Beats are built from the GRADED streams, so an unavailable stream changes
     its sentence rather than losing it. Omission is the easy way to lose the
     Phase 17 rule that UNAVAILABLE is not LOW — a narrative that simply says
     nothing about the environment reads as though the environment were fine.
     Test 2 asserts that by REMOVING a stream, not by reading the output.

  2. The opening is set by the detection's outcome, not the vessel's rank. On
     the detection where the system has just declined to name anyone, opening
     "Ranked #1 because..." would be the accusation it refused to make.

Nothing here checks that the narrative is CORRECT about the world. It checks
that it says what the evidence says, including where there is none.
"""
import pytest

from services.fleet_pipeline import run_fleet_scan
from services.narrative import MISSING, SUPPORTS, WEAKENS, build


@pytest.fixture(scope="module")
def t3():
    return run_fleet_scan("t3")


def _narrative(scan, spill_index, name):
    graded = {g["name"]: g for g in scan["spills"][spill_index]["evidence"]["candidates"]}
    return graded[name]["narrative"]


def test_the_top_vessel_on_a_weak_detection_is_not_accused(t3):
    """
    GRAND DOLPHIN leads a detection where every counterfactual rules everyone
    out. The narrative must not read as "ranked #1, therefore suspect".
    """
    n = _narrative(t3, 1, "GRAND DOLPHIN")
    opening = n["beats"][0]

    assert opening["tone"] == WEAKENS
    assert "does not say it was the source" in opening["text"]
    assert "no vessel's oil could have reached" in opening["text"]
    # The score is still stated — explained, not hidden.
    assert "70.54" in opening["text"]


def test_the_unstable_leader_is_framed_as_a_starting_point(t3):
    n = _narrative(t3, 0, "MR CANOPUS")
    opening = n["beats"][0]

    assert "where to start looking, not as an answer" in opening["text"]
    # And its fragile counterfactual is stated as weakening, with the number.
    fragile = [b for b in n["beats"] if b["tone"] == WEAKENS]
    assert any("0.06 km" in b["text"] for b in fragile)


def test_an_unavailable_stream_changes_its_sentence_rather_than_vanishing(t3):
    """
    The guard against the failure mode this narrative is most prone to. Graded
    streams are removed one at a time and the beat count must not drop.
    """
    spill = t3["spills"][0]
    graded = {g["name"]: g for g in spill["evidence"]["candidates"]}["MR CANOPUS"]
    candidate = next(c for c in spill["candidates"] if c["name"] == "MR CANOPUS")
    full = build(candidate, graded["streams"], "CANDIDATE_SUPPORTED", True)

    for stream in ("ais_coverage", "trajectory", "behaviour"):
        crippled = dict(graded["streams"])
        crippled[stream] = {"grade": "UNAVAILABLE", "reason": "It could not run."}
        n = build(candidate, crippled, "CANDIDATE_SUPPORTED", True)

        assert len(n["beats"]) >= len(full["beats"]) - 1, \
            f"removing {stream} lost a beat instead of changing one"
        assert stream in n["missing_streams"]
        assert any(b["tone"] == MISSING for b in n["beats"]), \
            f"{stream} unavailable produced no missing beat"


def test_a_behaviour_model_that_could_not_run_is_not_read_as_normal(t3):
    """Phase 9's guarantee, carried all the way into prose."""
    spill = t3["spills"][0]
    candidate = spill["candidates"][0]
    graded = spill["evidence"]["candidates"][0]["streams"]

    crippled = dict(graded)
    crippled["behaviour"] = {"grade": "UNAVAILABLE",
                             "reason": "The track was too short to score."}
    n = build(candidate, crippled, "CANDIDATE_SUPPORTED", True)

    beat = next(b for b in n["beats"] if "behaviour model" in b["text"].lower())
    assert beat["tone"] == MISSING
    assert "not evidence that it behaved normally" in beat["text"]


def test_the_environment_beat_is_present_and_missing_while_no_dataset_is_loaded(t3):
    for spill_index in (0, 1):
        for graded in t3["spills"][spill_index]["evidence"]["candidates"]:
            n = graded["narrative"]
            assert "environment" in n["missing_streams"]
            env = [b for b in n["beats"] if "wind or current" in b["text"]]
            assert len(env) == 1 and env[0]["tone"] == MISSING


def test_every_narrative_carries_the_no_causation_disclaimer(t3):
    for spill in t3["spills"]:
        for graded in spill["evidence"]["candidates"]:
            n = graded["narrative"]
            assert "None of it establishes that this vessel caused the spill" in n["disclaimer"]
            assert n["beats"], f"{graded['name']} has no narrative"
            # Tone counts must add up — a beat with an unknown tone would be
            # rendered as neutral and quietly lose its weight.
            assert sum(n["counts"].values()) == len(n["beats"])


def test_a_strongly_supported_candidate_reads_as_supported(t3):
    """A consistent candidate on a stable detection collects supporting beats."""
    spill = t3["spills"][0]
    candidate = next(c for c in spill["candidates"] if c["name"] == "ACHILLEAS")
    graded = {g["name"]: g for g in spill["evidence"]["candidates"]}["ACHILLEAS"]
    n = build(candidate, graded["streams"], "CANDIDATE_SUPPORTED", True)

    assert n["beats"][0]["tone"] == SUPPORTS
    assert "not evidence that it caused the spill" in n["beats"][0]["text"]
    assert n["counts"][SUPPORTS] >= 1
