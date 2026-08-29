from .data_store import get_incident
from .vessel_attribution import rank_candidates

def get_report():
    inc = get_incident()
    candidates = rank_candidates()
    return {
        "incident": inc,
        "top_candidates": [
            {"vessel_id":v["vessel_id"],"vessel_name":v["vessel_name"],
             "score":v["attribution_score"],"confidence":v["confidence"],
             "assessment":v["assessment"],"evidence":v["evidence"]}
            for v in candidates[:3]
        ],
        "disclaimer": inc["disclaimer"]
    }
