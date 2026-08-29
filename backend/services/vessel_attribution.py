"""
Explainable vessel attribution.

Two stages, deliberately kept separate:

    1. FACTOR CALCULATION  - how well a vessel matches the spill, per criterion.
                             Demo mode reads precomputed factors from the fixture;
                             real mode will derive them from AIS geometry.
    2. WEIGHTED SCORE      - the ranking formula. Pure and data-source agnostic:
                             it accepts a factor dict and returns a score, so it
                             works unchanged once real factors arrive.

The scoring weights are the model, not demo data, so they live here.
"""
from core.config import ANOMALY_MODEL_PATH, DEMO_MODE, model_provenance

from .data_store import get_vessels, get_pipeline_demo
from .geo import haversine_km

WEIGHTS = {
    "time_match": .20, "source_overlap": .25, "trajectory": .20,
    "distance_score": .15, "behaviour": .10, "ais_consistency": .05, "relevance": .05
}

FACTOR_NAMES = tuple(WEIGHTS)


# --- stage 2: weighted score -------------------------------------------------

def score_from_factors(factors):
    """
    Weighted attribution score from a factor dict.

    Each factor is 0-100. Returns (score, contributions) where contributions maps
    each factor to its weighted share, which is what the UI renders as evidence.
    Missing factors count as 0 rather than raising, so a partial real-mode result
    still ranks.
    """
    contributions = {
        name: round(factors.get(name, 0) * weight, 2)
        for name, weight in WEIGHTS.items()
    }
    return round(sum(contributions.values())), contributions


# --- stage 1: factor calculation ---------------------------------------------

def load_demo_factors(vessel):
    """Precomputed factors from the demo fixture. No values are computed here."""
    return vessel["factors"]


def compute_factors(vessel, source_region=None, release_window=None):
    """
    Derive the seven factors for one vessel from its AIS track.

    Real mode will compute proximity, trajectory alignment, time overlap with the
    release window, behavioural anomalies and AIS continuity here, then hand the
    result to score_from_factors() unchanged.
    """
    if DEMO_MODE:
        return load_demo_factors(vessel)

    raise NotImplementedError(
        "AIS-derived factor calculation not connected yet. Must return a dict "
        f"with keys: {', '.join(FACTOR_NAMES)}"
    )


# --- public interface (unchanged response shapes) ----------------------------

def _scored(vessel):
    """Vessel record with its score recomputed from its factors."""
    factors = compute_factors(vessel)
    score, contributions = score_from_factors(factors)
    return {**vessel, "attribution_score": score}, factors, contributions


def explain(vessel_id):
    """Full evidence breakdown for one vessel, or None if unknown."""
    for vessel in get_vessels():
        if vessel["vessel_id"] != vessel_id:
            continue
        scored, factors, contributions = _scored(vessel)
        return {
            "vessel_id": scored["vessel_id"], "vessel_name": scored["vessel_name"],
            "score": scored["attribution_score"], "confidence": scored["confidence"],
            "assessment": scored["assessment"], "evidence": scored["evidence"],
            "factors": factors, "weights": WEIGHTS, "contributions": contributions,
            "ais_dark": scored["ais_dark"], "vessel_type": scored["vessel_type"],
            "flag": scored["flag"],
        }
    return None


def rank_candidates():
    """All candidate vessels, highest attribution score first."""
    scored = [_scored(v)[0] for v in get_vessels()]
    return sorted(scored, key=lambda v: v["attribution_score"], reverse=True)


# --- step 5: behavioural anomaly ---------------------------------------------

def anomaly_provenance():
    """Whether anomaly scores came from the trained model or the demo stub."""
    return model_provenance(ANOMALY_MODEL_PATH)


def score_anomaly(ship_id, track):
    """
    Behavioural anomaly for one vessel track.

    DEMO_MODE on  -> scores from data/demo/pipeline_demo.json
    DEMO_MODE off -> the trained model via ml/anomaly_model.py
    """
    if DEMO_MODE:
        demo = get_pipeline_demo()
        entry = demo["anomaly_scores"].get(ship_id, {"anomaly_score": 0.0, "reason": "no signal"})
        return {
            "ship_id": ship_id,
            "anomaly_score": entry["anomaly_score"],
            "is_anomaly": entry["anomaly_score"] >= demo["anomaly_threshold"],
            "reason": entry["reason"],
            "provenance": anomaly_provenance(),
        }

    from ml.anomaly_model import get_model
    result = get_model().predict(track)
    return {"ship_id": ship_id, **result, "provenance": anomaly_provenance()}


# --- step 6: factors from AIS geometry ---------------------------------------

def factors_from_ais(vessel, origin, anomaly, search_radius_km):
    """
    Derive the seven scoring factors for one candidate from its AIS track.

    Each is 0-100 and is a plain, inspectable formula:

      source_overlap  how far inside the search radius its closest approach fell
      distance_score  max(0, 100 - km x 10), the existing distance curve
      time_match      share of its in-window fixes that sat inside the radius
      trajectory      convergence: how much it closed on the origin in-window
      behaviour       anomaly model score x 100
      ais_consistency AIS *suspicion*: 100 - continuity. A vessel reporting
                      normally scores low; one that went dark across the release
                      window scores high. Every factor in this model raises
                      suspicion, so continuity had to be inverted to sit here --
                      rewarding an unbroken track would have made going dark
                      lower a vessel's score, which is backwards for attribution.
      relevance       vessel type's relevance to an oil release
    """
    km = vessel["min_distance_km"]
    first = vessel.get("first_distance_km") or km

    source_overlap = max(0.0, min(100.0, (1 - km / search_radius_km) * 100))
    distance_score = max(0.0, 100 - km * 10)

    inside = sum(
        1 for p in vessel["track"]
        if haversine_km(origin["origin_lat"], origin["origin_lon"], p["lat"], p["lon"]) <= search_radius_km
    )
    time_match = 100.0 if vessel["window_points"] and inside else 0.0

    trajectory = max(0.0, min(100.0, (first - km) / first * 100)) if first else 0.0

    # Gaps overlapping the release window count double: going dark at the moment
    # of release is materially more suspicious than a gap hours away.
    dark_minutes = sum(g["minutes"] for g in vessel["gaps"])
    dark_in_window = sum(g.get("minutes_in_window", 0) for g in vessel["gaps"])
    ais_continuity_score = max(0.0, 100 - (dark_minutes + dark_in_window) * 1.1)
    ais_suspicion = 100 - ais_continuity_score

    oily = ("tanker" in vessel["vessel_type"].lower())
    relevance = 90.0 if oily else 55.0

    return {
        "time_match": round(time_match, 1),
        "source_overlap": round(source_overlap, 1),
        "trajectory": round(trajectory, 1),
        "distance_score": round(distance_score, 1),
        "behaviour": round(anomaly["anomaly_score"] * 100, 1),
        # Field name kept for API compatibility; it now carries AIS suspicion.
        "ais_consistency": round(ais_suspicion, 1),
        "ais_continuity_score": round(ais_continuity_score, 1),
        "ais_dark_minutes": dark_minutes,
        "ais_dark_minutes_in_window": dark_in_window,
        "relevance": relevance,
        "distance_km": km,
    }


def _evidence(vessel, anomaly, factors):
    lines = [
        f"Closest approach {vessel['min_distance_km']} km from the estimated origin",
        f"Present in the release window at {vessel['closest_time'][11:16]} UTC",
    ]
    if factors["trajectory"] >= 50:
        lines.append(f"Track converged on the origin ({factors['trajectory']:.0f}% closure)")
    if anomaly["is_anomaly"]:
        lines.append(f"Behavioural anomaly: {anomaly['reason']}")
    for gap in vessel["gaps"]:
        if gap.get("minutes_in_window"):
            lines.append(
                f"AIS went dark for {gap['minutes']} min from {gap['from'][11:16]} UTC, "
                f"{gap['minutes_in_window']} min of it inside the probable release "
                f"window - the vessel cannot be placed during the release"
            )
        else:
            lines.append(
                f"AIS gap of {gap['minutes']} min from {gap['from'][11:16]} UTC, "
                f"outside the release window"
            )
    if not vessel["gaps"]:
        lines.append("AIS reporting continuous through the release window")
    if factors["relevance"] >= 90:
        lines.append(f"Vessel type relevant to an oil release ({vessel['vessel_type']})")
    return lines


def rank_ships(candidates, origin, search_radius_km):
    """
    Score and rank the candidates that survived the AIS filter.

    Reuses score_from_factors(), so the weighting is identical to the existing
    engine; only the source of the factors is new.
    """
    ranked = []
    for vessel in candidates:
        anomaly = score_anomaly(vessel["id"], vessel["track"])
        factors = factors_from_ais(vessel, origin, anomaly, search_radius_km)
        score, contributions = score_from_factors(factors)
        confidence = "High" if score >= 80 else "Medium" if score >= 55 else "Low"
        ranked.append({
            "ship_id": vessel["id"], "name": vessel["name"],
            "mmsi": vessel["mmsi"], "imo": vessel["imo"],
            "vessel_type": vessel["vessel_type"],
            "attribution_score": score,
            "confidence": confidence,
            "assessment": ("POTENTIAL SUSPECT VESSEL" if score >= 80
                           else "CANDIDATE UNDER REVIEW"),
            "factors": factors, "weights": WEIGHTS, "contributions": contributions,
            "anomaly": anomaly,
            "min_distance_km": vessel["min_distance_km"],
            "closest_time": vessel["closest_time"],
            "ais_dark": bool(vessel["gaps"]),
            "evidence": _evidence(vessel, anomaly, factors),
        })
    return sorted(ranked, key=lambda v: v["attribution_score"], reverse=True)
