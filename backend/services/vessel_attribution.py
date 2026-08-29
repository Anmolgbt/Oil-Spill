from .data_store import get_vessels

WEIGHTS = {
    "time_match": .20, "source_overlap": .25, "trajectory": .20,
    "distance_score": .15, "behaviour": .10, "ais_consistency": .05, "relevance": .05
}

def explain(vessel_id):
    for v in get_vessels():
        if v["vessel_id"] == vessel_id:
            contributions = {k: round(v["factors"][k]*w, 2) for k,w in WEIGHTS.items()}
            return {
                "vessel_id": v["vessel_id"], "vessel_name": v["vessel_name"],
                "score": v["attribution_score"], "confidence": v["confidence"],
                "assessment": v["assessment"], "evidence": v["evidence"],
                "factors": v["factors"], "weights": WEIGHTS, "contributions": contributions,
                "ais_dark": v["ais_dark"], "vessel_type": v["vessel_type"], "flag": v["flag"]
            }
    return None

def rank_candidates():
    return sorted(get_vessels(), key=lambda v:v["attribution_score"], reverse=True)
