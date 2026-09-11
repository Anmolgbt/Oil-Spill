"""
The attribution score, and the rule that applies when a term is missing.

These check arithmetic and the documented weighting rule. They say nothing about
whether the ranking is *correct* — there is no labelled spill-to-vessel dataset
to check that against, and no test here should be read as attribution accuracy.
"""
import pytest

from services.fleet_pipeline import rank_fleet, score_fleet_behaviour
from services.investigation import (WEIGHT_BEHAVIOUR, WEIGHT_PROXIMITY,
                                    WEIGHT_TRAJECTORY)

SOURCE = {"latitude": 28.55, "longitude": -94.85}
RELEASE = "2021-03-28T20:30:00Z"


def _vessel(mmsi=777):
    """A vessel closing on the source across the trajectory window."""
    return {"id": "z", "mmsi": mmsi, "name": "TESTER", "vessel_type": "Cargo",
            "track": [{"time": f"2021-03-28T{h:02d}:30:00Z",
                       "lat": 28.50 + i * 0.01, "lon": -94.83 + i * 0.01,
                       "speed_kt": 8, "course_deg": 45}
                      for i, h in enumerate((19, 20, 21))]}


def _behaviour(score):
    return {777: {"available": score is not None, "status": "ok" if score is not None else "inference_error",
                  "score": score, "anomalous_points": 1,
                  "reason": None if score is not None else "Inference error: RuntimeError."}}


def test_weights_sum_to_one():
    assert WEIGHT_PROXIMITY + WEIGHT_TRAJECTORY + WEIGHT_BEHAVIOUR == pytest.approx(1.0)


def test_score_is_the_stated_weighted_sum():
    r = rank_fleet([_vessel()], SOURCE, RELEASE, radius_km=50,
                   behaviour_by_mmsi=_behaviour(60.0))
    c = r["candidates"][0]
    expected = (WEIGHT_PROXIMITY * c["proximity_score"]
                + WEIGHT_TRAJECTORY * c["trajectory_score"]
                + WEIGHT_BEHAVIOUR * c["behaviour_score"])
    assert c["final_suspect_score"] == pytest.approx(expected, abs=0.01)
    assert c["weights_applied"] == {"proximity": 0.4, "trajectory": 0.3, "behaviour": 0.3}
    assert c["scored_on_partial_evidence"] is False


def test_unavailable_behaviour_reweights_rather_than_scoring_zero():
    """
    The rule documented in docs/MODELS.md: renormalise the remaining terms.

    Scoring a missing term as zero would assert the vessel behaved normally,
    which a failed model call does not establish.
    """
    r = rank_fleet([_vessel()], SOURCE, RELEASE, radius_km=50,
                   behaviour_by_mmsi=_behaviour(None))
    c = r["candidates"][0]

    total = WEIGHT_PROXIMITY + WEIGHT_TRAJECTORY
    expected = ((WEIGHT_PROXIMITY / total) * c["proximity_score"]
                + (WEIGHT_TRAJECTORY / total) * c["trajectory_score"])
    assert c["final_suspect_score"] == pytest.approx(expected, abs=0.01)
    assert c["weights_applied"]["behaviour"] == 0.0
    assert c["weights_applied"]["proximity"] == pytest.approx(WEIGHT_PROXIMITY / total, abs=1e-4)
    assert c["scored_on_partial_evidence"] is True
    assert c["behaviour_status"] == "inference_error"


def test_reweighting_beats_zeroing_for_the_same_vessel():
    """The old `behaviour or 0.0` cost the vessel points for a model failure."""
    with_b = rank_fleet([_vessel()], SOURCE, RELEASE, radius_km=50,
                        behaviour_by_mmsi=_behaviour(60.0))["candidates"][0]
    without = rank_fleet([_vessel()], SOURCE, RELEASE, radius_km=50,
                         behaviour_by_mmsi=_behaviour(None))["candidates"][0]
    zeroed = (WEIGHT_PROXIMITY * with_b["proximity_score"]
              + WEIGHT_TRAJECTORY * with_b["trajectory_score"])

    assert without["final_suspect_score"] > zeroed
    assert abs(without["final_suspect_score"] - with_b["final_suspect_score"]) < 5


def test_track_too_short_is_reported_not_scored():
    verdicts = score_fleet_behaviour([
        {"mmsi": 1, "id": "a", "name": "ONE FIX",
         "track": [{"time": "2021-03-28T21:00:00Z", "lat": 28.5, "lon": -94.8,
                    "speed_kt": 5, "course_deg": 90}]}])
    v = verdicts[1]
    assert v["available"] is False
    assert v["status"] == "track_too_short"
    assert v["score"] is None
    assert v["reason"]


def test_inference_error_is_surfaced_not_swallowed(monkeypatch):
    import ml.ais_inference as ai

    def boom(*args, **kwargs):
        raise RuntimeError("simulated model crash")

    monkeypatch.setattr(ai, "predict_track", boom)
    verdicts = score_fleet_behaviour([_vessel(mmsi=42)])
    v = verdicts[42]
    assert v["available"] is False
    assert v["status"] == "inference_error"
    assert v["score"] is None


def test_vessels_outside_the_radius_are_rejected():
    """The traffic filter must actually reject, not admit everything."""
    near, far = _vessel(mmsi=1), _vessel(mmsi=2)
    far["track"] = [{**p, "lat": p["lat"] + 1.5} for p in far["track"]]
    r = rank_fleet([near, far], SOURCE, RELEASE, radius_km=16.74,
                   behaviour_by_mmsi={1: _behaviour(50.0)[777], 2: _behaviour(50.0)[777]})
    assert r["funnel"]["monitored"] == 2
    assert r["funnel"]["rejected_too_far"] == 1
    assert [c["mmsi"] for c in r["candidates"]] == [1]
