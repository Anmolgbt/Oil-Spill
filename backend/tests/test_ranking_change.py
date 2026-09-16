"""
Does the drift assumption change WHO the system ranks first?

On the shipped t3 case it does, on one of the two detections. That is the most
useful thing this comparison reports and the least comfortable, so it is pinned
here: a silent change to either ranking, or to the drift constants behind them,
should fail this file rather than quietly alter what the panel claims.

The other half is the guarantee that makes the first half safe to show — the
comparison is a PARALLEL computation and the shipped candidate list is
untouched by it.

Nothing here asserts that either ranking is right. There is no labelled
spill-to-vessel dataset, so neither can be checked.
"""
import pytest

from services.fleet_pipeline import run_fleet_scan


@pytest.fixture(scope="module")
def scan():
    return run_fleet_scan("t3")


def test_the_top_candidate_changes_on_the_first_detection(scan):
    """
    Same fleet, same search radius, same behaviour scores. Only the estimated
    source moves — and it moves because the legacy hindcast's 1.5 km/h toward
    135 deg was never derived from the stated wind and current.
    """
    change = scan["spills"][0]["drift_divergence"]["ranking_change"]

    assert change["available"] is True
    assert change["top_changes"] is True
    assert change["legacy_top"] == "MR CANOPUS"
    assert change["environmental_top"] == "NISALAH"

    by_name = {r["name"]: r for r in change["rows"]}
    assert by_name["MR CANOPUS"]["legacy_rank"] == 1
    assert by_name["MR CANOPUS"]["environmental_rank"] == 3
    assert by_name["NISALAH"]["legacy_rank"] == 2
    assert by_name["NISALAH"]["environmental_rank"] == 1
    # The largest single move, and the one worth noticing.
    assert by_name["ACHILLEAS"]["rank_delta"] == 4


def test_the_second_detection_is_steady(scan):
    """
    Having one detection that flips and one that does not is the honest picture:
    the sensitivity is real but not universal.
    """
    change = scan["spills"][1]["drift_divergence"]["ranking_change"]
    assert change["top_changes"] is False
    assert change["legacy_top"] == change["environmental_top"] == "GRAND DOLPHIN"


def test_a_vessel_outside_the_environmental_radius_is_dropped_not_zeroed(scan):
    """
    Same distinction the behaviour term makes: unavailable is not the same as
    scoring badly, and a dropped vessel must not read as a low score.
    """
    rows = scan["spills"][0]["drift_divergence"]["ranking_change"]["rows"]
    dropped = [r for r in rows if r["dropped"]]
    assert dropped, "the measured case has one vessel outside the environment-aware radius"
    for r in dropped:
        assert r["environmental_rank"] is None
        assert r["environmental_score"] is None
        assert r["rank_delta"] is None


def test_the_shipped_ranking_is_untouched_by_the_comparison(scan):
    """
    The comparison must be parallel. If computing it could reorder the real
    candidate list, the panel would be describing a ranking it had itself
    changed.
    """
    for spill in scan["spills"]:
        change = spill["drift_divergence"]["ranking_change"]
        assert change["in_use"] == "legacy"
        shipped = [(c["rank"], c["mmsi"], c["final_suspect_score"])
                   for c in spill["candidates"]]
        legacy_side = [(r["legacy_rank"], r["mmsi"], r["legacy_score"])
                       for r in change["rows"]]
        assert shipped == legacy_side

    # And the figures every driver script asserts are where they were.
    assert scan["spills"][0]["affected_area"]["radius_km"] == 5.58
    assert scan["spills"][0]["ais"]["funnel"]["within_radius"] == 11
    assert scan["spills"][1]["ais"]["funnel"]["within_radius"] == 5
