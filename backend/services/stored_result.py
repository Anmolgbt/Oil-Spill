"""
Adapter for the completed AI results handed off from Colab.

`data/ai_output/oiltrace_ai_output_final.json` is the canonical stored result and
the single source of truth for the real investigation. Nothing in this module
computes, derives or substitutes a value: fields the AI did not produce are
reported as unavailable so the dashboard can say "Not available" instead of
showing an invented number.

Known limits of the supplied system, encoded here so the UI cannot overstate it:

* The CNN is a BINARY CLASSIFIER (0 = no oil spill, 1 = oil spill). It performs
  no segmentation, so there is no mask, no boundary, no area, no thickness and
  no volume. Those are reported unavailable, not estimated.
* The hindcast is a kinematic back-projection using an assumed drift vector
  (notebook cell 41: 1.5 km/h toward 135 degrees, marked "replace with real
  wind/current data later"). It is a model estimate, never a confirmed source.
* The forecast is `kinematic_projection`, not drift physics. The output itself
  sets `requires_environmental_drift_data: true`.
* No wind, current, wave or oil-property data exists anywhere in the output.
"""
import json

from core.config import AI_OUTPUT_DIR, MODEL_ARTIFACTS_DIR

AI_OUTPUT_FILE = AI_OUTPUT_DIR / "oiltrace_ai_output_final.json"
CNN_METRICS_FILE = AI_OUTPUT_DIR / "cnn_validation_metrics.json"

# Served at /ai-images (see main.py). class_1 is the OIL SPILL sample the
# completed case was run on; class_0 is the NO OIL SPILL counter-sample.
SAMPLE_IMAGE_URL = "/ai-images/class_1.jpg"

UNAVAILABLE = None

# Capabilities the supplied system does not have. Listed explicitly so the UI
# renders "Not available" from data rather than from hardcoded frontend strings.
NOT_AVAILABLE_FIELDS = [
    "spill_area_km2", "oil_thickness", "oil_volume", "segmentation_mask",
    "spill_boundary", "wind", "current", "wave", "source_confidence",
    "vessel_coordinates",
]


def load_ai_output():
    """The canonical AI result, exactly as produced. Never mutated."""
    with open(AI_OUTPUT_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_cnn_metrics():
    """Standalone validation metrics file (same numbers as `cnn_validation`)."""
    with open(CNN_METRICS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _artifact(name):
    path = MODEL_ARTIFACTS_DIR / name
    return {"file": name, "present": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None}


def model_artifacts():
    """Trained files preserved in the repo. Present, but not loaded for inference."""
    return {
        "cnn": _artifact("oilspill_cnn.pth"),
        "ais_isolation_forest": _artifact("ais_isolation_forest.pkl"),
        "ais_scaler": _artifact("ais_scaler.pkl"),
        "live_inference": False,
        "note": ("Weights are preserved for future live inference. The dashboard "
                 "currently serves the completed stored result."),
    }


def evidence_provenance():
    """
    Evidence class per section, so the UI can distinguish what was observed from
    what was modelled, predicted or merely ranked.
    """
    return {
        "satellite_image": "OBSERVED / INPUT",
        "cnn_classification": "MODEL OUTPUT",
        "spill_location": "SUPPLIED RESULT",
        "probable_source": "MODEL ESTIMATE",
        "ais_records": "OBSERVED / INPUT DATA",
        "behaviour_anomaly": "MODEL OUTPUT",
        "final_suspect_score": "ANALYTICAL RANKING",
        "forecast": "PREDICTION",
    }


def get_investigation():
    """
    The completed AI case, adapted for the dashboard.

    Every value below is copied from the stored result. Keys whose value is None
    were not produced by the AI system and must render as "Not available".
    """
    ai = load_ai_output()
    detection = ai["detection"]
    spill = ai["spill"]
    hindcast = ai["hindcast"]
    ais = ai["ais"]
    interpretation = ai.get("interpretation", {})

    return {
        "system": ai.get("system", "OILTRACE"),
        "version": ai.get("version"),
        "mode": "AI_RESULT",

        "detection": {
            "prediction": detection["prediction"],
            "oil_detected": detection["class"] == 1,
            "class": detection["class"],
            "confidence": detection["confidence"],
            "model": "OilSpillCNN — binary classifier",
            "task": "classification",
            "performs_segmentation": False,
            "image_url": SAMPLE_IMAGE_URL,
            # No mask exists, so no area can be derived from one.
            "estimated_area_km2": UNAVAILABLE,
            "mask_url": UNAVAILABLE,
            "oil_thickness": UNAVAILABLE,
            "oil_volume": UNAVAILABLE,
            "evidence_class": "MODEL OUTPUT",
        },

        "spill": {
            "latitude": spill["latitude"],
            "longitude": spill["longitude"],
            "evidence_class": "SUPPLIED RESULT",
        },

        "source": {
            "latitude": hindcast["latitude"],
            "longitude": hindcast["longitude"],
            "hours_backward": hindcast["hours_backward"],
            "label": "Probable Source — Model Estimate",
            "confirmed": False,
            # The notebook's drift vector is an assumption, not measured data,
            # so no confidence figure is claimed for it.
            "confidence": UNAVAILABLE,
            "method": "Kinematic back-projection using an assumed drift vector",
            "environmental_data_used": False,
            "evidence_class": "MODEL ESTIMATE",
        },

        "ais": {
            "candidate_count": ais["candidate_count"],
            "model": "Isolation Forest — behavioural anomaly detection",
            # Only the top candidate is detailed in the AI output. The others are
            # counted but not described, and are not invented here.
            "detailed_candidates": 1,
            "candidates": [{
                "rank": 1,
                "mmsi": ais["top_mmsi"],
                "minimum_distance_km": ais["minimum_distance_km"],
                "trajectory_status": ais["trajectory_status"],
                "trajectory_score": ais["trajectory_score"],
                "behaviour_score": ais["behaviour_score"],
                "final_suspect_score": ais["final_suspect_score"],
                # No per-vessel coordinates exist in the output, so this
                # candidate cannot be placed on the map.
                "latitude": UNAVAILABLE,
                "longitude": UNAVAILABLE,
                "track": UNAVAILABLE,
            }],
            "note": (f"{ais['candidate_count']} candidates were found; the AI output "
                     f"details only the top-ranked vessel."),
            "evidence_class": "ANALYTICAL RANKING",
        },

        "forecast": {
            "type": interpretation.get("forecast_type", "kinematic_projection"),
            "label": "Kinematic Movement Projection",
            "requires_environmental_drift_data": interpretation.get(
                "requires_environmental_drift_data", True),
            "warning": ("Environmental wind, currents, waves and oil properties are "
                        "not currently incorporated."),
            "points": ai.get("forecast", []),
            "wind": UNAVAILABLE,
            "current": UNAVAILABLE,
            "wave": UNAVAILABLE,
            "evidence_class": "PREDICTION",
        },

        "cnn_validation": ai.get("cnn_validation", load_cnn_metrics()),
        "model_status": ai.get("model_status", {}),
        "model_artifacts": model_artifacts(),
        "evidence_provenance": evidence_provenance(),
        "not_available": NOT_AVAILABLE_FIELDS,

        "interpretation": {
            **interpretation,
            "ranking_meaning": (
                "This ranking indicates analytical association with the estimated "
                "source window. It does not establish legal responsibility."
            ),
        },

        "provenance": {
            "source": "ai_result_stored",
            "detail": "Completed AI output from the Colab handoff, served verbatim.",
            "live_inference": False,
        },
    }
