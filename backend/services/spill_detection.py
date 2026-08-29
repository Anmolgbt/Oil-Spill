"""
Step 1-2 of the pipeline: oil detection and spill characterisation.

DEMO_MODE on  -> per-ship probabilities from data/demo/pipeline_demo.json
DEMO_MODE off -> the trained model via ml/spill_model.py

Both paths return the same shapes, so routes and the frontend are unaffected by
the switch.
"""
from core.config import (COMPUTED_PROVENANCE, DEMO_MODE, FIXTURE_PROVENANCE,
                         SPILL_MODEL_PATH, model_provenance)

from .data_store import get_incident, get_pipeline_demo


def oil_provenance():
    """Whether oil probabilities came from the trained model or the demo stub."""
    return model_provenance(SPILL_MODEL_PATH)


# --- step 1: scan a snapshot -------------------------------------------------

def _demo_scores(snapshot_id):
    demo = get_pipeline_demo()
    return demo["snapshot_detections"].get(snapshot_id, {}), demo


def detect_oil(image_path, ship_id=None, snapshot_id=None):
    """
    Run the oil model on one ship image.

    Returns {"ship_id", "oil_detected", "oil_probability", "mask_pixels"}.
    """
    if DEMO_MODE:
        scores, demo = _demo_scores(snapshot_id)
        entry = scores.get(ship_id, {})
        probability = entry.get("oil_probability", 0.0)
        return {
            "ship_id": ship_id,
            "oil_detected": probability >= demo["detection_threshold"],
            "oil_probability": probability,
            "mask_pixels": entry.get("mask_pixels"),
            "provenance": oil_provenance(),
        }

    from ml.spill_model import get_model
    result = get_model().predict(image_path)
    return {
        "ship_id": ship_id,
        "oil_detected": result["oil_detected"],
        "oil_probability": result["oil_probability"],
        "mask_pixels": result.get("mask_pixels"),
        "provenance": oil_provenance(),
    }


def scan_snapshot(snapshot):
    """
    Run the oil model across every ship image in one satellite pass.

    `snapshot` is the dict returned by simulation_service.get_snapshot_data().
    Ships whose image is missing are reported as skipped rather than scored, so
    one absent file never aborts the pass.
    """
    results, detections = [], []
    for ship in snapshot["ships"]:
        if not ship["image_available"]:
            results.append({
                "ship_id": ship["id"], "ship_name": ship["name"],
                "status": "SKIPPED", "reason": "image not available",
                "oil_probability": None, "oil_detected": False,
            })
            continue

        found = detect_oil(ship["image_url"], ship["id"], snapshot["snapshot_id"])
        record = {
            "ship_id": ship["id"], "ship_name": ship["name"],
            "status": "OIL SIGNATURE DETECTED" if found["oil_detected"] else "CLEAR",
            "oil_probability": found["oil_probability"],
            "oil_detected": found["oil_detected"],
            "image_url": ship["image_url"],
            "latitude": ship["latitude"], "longitude": ship["longitude"],
        }
        if found["oil_detected"]:
            record["mask_pixels"] = found.get("mask_pixels")
            detections.append(record)
        results.append(record)

    detections.sort(key=lambda r: r["oil_probability"], reverse=True)
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "provenance": oil_provenance(),
        "scanned": len(results),
        "results": results,
        "oil_detected": bool(detections),
        "detections": detections,
    }


# --- step 2: characterise ----------------------------------------------------

def characterize(detection):
    """
    Geometric properties of a confirmed detection.

    Area comes from the mask: oil pixels x the ground area each pixel covers.
    Location is the ship position the snapshot was taken around.
    """
    demo = get_pipeline_demo()
    pixels = detection.get("mask_pixels")
    area = round(pixels * demo["pixel_area_km2"], 2) if pixels else None

    return {
        "ship_id": detection["ship_id"],
        "oil_probability": detection["oil_probability"],
        "estimated_area_km2": area,
        # Area is computed here, but from a mask the oil model supplies.
        "provenance": dict(COMPUTED_PROVENANCE, mask_source=oil_provenance()["source"]),
        "latitude": detection["latitude"],
        "longitude": detection["longitude"],
        "mask_pixels": pixels,
        "pixel_area_km2": demo["pixel_area_km2"],
    }


# --- existing /detect-spill contract (unchanged) -----------------------------

def load_demo_detection(scene_id=None):
    """Detection result read from the incident fixture. No values computed here."""
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
        "provenance": FIXTURE_PROVENANCE,
    }


def detect_spill(image_path=None, scene_id=None):
    """Single-scene detection, backing the existing POST /detect-spill route."""
    if DEMO_MODE:
        return load_demo_detection(scene_id)

    raise NotImplementedError(
        "ML spill detector not connected yet. Implement ml/spill_model.py, "
        "then map its output onto the keys returned by load_demo_detection()."
    )
