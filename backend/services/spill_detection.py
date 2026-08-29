from .data_store import get_incident

def run_detection(scene_id=None):
    inc = get_incident()
    return {
        "scene_id": scene_id or inc["satellite"]["scene_id"],
        "sensor": inc["satellite"]["sensor"],
        "image_original": inc["satellite"]["image_original"],
        "image_mask": inc["satellite"]["image_mask"],
        "image_overlay": inc["satellite"]["image_overlay"],
        "oil_probability": inc["kpis"]["spill_probability"],
        "estimated_area_km2": inc["kpis"]["estimated_area_km2"],
        "confidence": inc["spill_metrics"]["confidence"],
        "decision": inc["lookalike"]["decision"],
    }
