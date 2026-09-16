"""
Determinism, the CLEAR path, and the reroute's one real promise.

Slower than the unit tests — these run the CNN over the fleet — but they are the
ones that would catch a broken demo.
"""
import pytest

from core.config import SIMULATION_SEED
from services.fleet_pipeline import run_fleet_scan
from services.risk import spill_polygons
from services.t3_simulation import assign_t3_images


def test_same_seed_gives_the_same_oil_assignment():
    """The demo must replay identically, or a rehearsed walkthrough is worthless."""
    ships = [f"ship{i}" for i in range(1, 13)]
    a = assign_t3_images(ships, seed=SIMULATION_SEED, oil_eligible_ids=["ship1", "ship2"])
    b = assign_t3_images(ships, seed=SIMULATION_SEED, oil_eligible_ids=["ship1", "ship2"])
    assert a == b

    oil = sorted(r["ship_id"] for r in a
                 if r["ground_truth_for_simulation"] == "oil")
    assert oil, "the seeded draw must flag at least one vessel"
    # Ground truth for the SIMULATION's assignment. Not attribution ground truth.
    assert all(s in ("ship1", "ship2") for s in oil)


def test_a_different_seed_can_differ():
    ships = [f"ship{i}" for i in range(1, 13)]
    a = assign_t3_images(ships, seed=SIMULATION_SEED, oil_eligible_ids=ships)
    b = assign_t3_images(ships, seed=SIMULATION_SEED + 1, oil_eligible_ids=ships)
    assert a != b


@pytest.mark.slow
def test_scan_is_deterministic_across_runs():
    one, two = run_fleet_scan("t3"), run_fleet_scan("t3")
    assert one["status"] == two["status"] == "SPILL_DETECTED"
    names = lambda s: [c["name"] for c in s["spills"][0]["candidates"]]
    scores = lambda s: [c["final_suspect_score"] for c in s["spills"][0]["candidates"]]
    assert names(one) == names(two)
    assert scores(one) == scores(two)


@pytest.mark.slow
def test_clear_pass_carries_no_spill_fields():
    """A clean pass must not leak spill-shaped keys that would render as findings."""
    scan = run_fleet_scan("t1")
    assert scan["status"] == "CLEAR"
    for key in ("spill", "spills", "source", "age", "candidates", "ais",
                "forecast", "affected_area", "response_priorities"):
        assert key not in scan, f"CLEAR pass leaked {key!r}"
    assert scan["scanned"] > 0
    assert scan["detections"] == []


@pytest.mark.slow
def test_detour_clears_the_spill_polygons():
    """
    The reroute's only real promise. It is a demo, not navigation guidance —
    but a route drawn to avoid the zone must avoid it.

    A vessel ALREADY inside the zone is the documented exception: there is no
    route out that does not start inside, so reroute.py returns a shortest-way-
    out flagged `already_inside_zone`. That case is asserted separately rather
    than excused.
    """
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    scan = run_fleet_scan("t3")
    at_risk = [r for r in scan["risk_overview"]["at_risk"] if r.get("detour")]
    assert at_risk, "no at-risk vessel with a detour to check"

    checked_outside = False
    for entry in at_risk:
        detour = entry["detour"]
        spill = next(sp for sp in scan["spills"]
                     if sp["spill"]["ship_id"] == entry["spill_ship_id"])
        keep_out = unary_union([p["polygon"] for p in spill_polygons(spill)])
        route = LineString([(w["longitude"], w["latitude"])
                            for w in detour["detour_waypoints"]])

        if detour["already_inside_zone"]:
            # Must be honest about it rather than claiming a clear route.
            assert detour["clears_spill_zone"] is False
            assert "inside" in (detour.get("reason", "") + detour.get("note", "")).lower()
        else:
            assert detour["clears_spill_zone"] is True
            assert not route.intersects(keep_out), (
                f"{entry['name']}'s detour crosses the zone it avoids")
            checked_outside = True

    assert checked_outside, "no vessel started outside the zone, so nothing was proven"
