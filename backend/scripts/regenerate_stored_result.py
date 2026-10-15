"""
Regenerate the stored completed case (data/ai_output/*) from the CURRENT models.

The dashboard falls back to oiltrace_ai_output_final.json when a live scan is
unavailable, and /ai-result serves it. Those two files must describe the models
that are actually installed, so after swapping a model run:

    cd backend && python scripts/regenerate_stored_result.py

It runs the same pipeline as POST /ai/investigate on the bundled sample scene with
the documented default inputs, and writes the result in the stored schema. The CNN
metrics are copied from the training notebook's cnn_test_metrics.json - they are
measurements, so nothing here computes or invents them.

Usage:  python scripts/regenerate_stored_result.py [path/to/cnn_test_metrics.json]
        (defaults to the copy kept in handoff/)
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from core.config import AI_OUTPUT_DIR  # noqa: E402
from services.investigation import run_live_investigation  # noqa: E402

DEFAULT_METRICS = BACKEND.parent / "handoff" / "cnn_test_metrics.json"


def metrics_file(src):
    m = json.loads(Path(src).read_text())
    cfg = json.loads((BACKEND / "artifacts" / "cnn_config.json").read_text())
    return {
        "test_samples": m["n_test"],
        "test_scenes": cfg["evaluation"]["n_test_scenes"],
        "accuracy": round(m["accuracy"], 4),
        "precision": round(m["precision"], 4),
        "recall": round(m["recall"], 4),
        "f1_score": round(m["f1"], 4),
        "specificity": round(m["specificity"], 4),
        "roc_auc": round(m["roc_auc"], 4),
        "average_precision": round(m["average_precision"], 4),
        "ece": round(m["ece_test"], 4),
        "confusion_matrix": {"true_negative": m["tn"], "false_positive": m["fp"],
                             "false_negative": m["fn"], "true_positive": m["tp"]},
        "classes": {"0": "NO OIL SPILL", "1": "OIL SPILL"},
        "threshold": m["threshold"],
        "temperature": round(m["temperature"], 4),
        "split": m["split"],
        "ci95_scene_bootstrap": {k: [round(v[0], 4), round(v[1], 4)]
                                 for k, v in m["ci95_scene_bootstrap"].items()},
    }


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_METRICS
    metrics = metrics_file(src)

    sample = AI_OUTPUT_DIR / "samples" / "class_1.jpg"
    run = run_live_investigation(image_path=sample)
    if run.get("status") != "SPILL_CONFIRMED":
        raise SystemExit(f"The sample scene was not classified as oil ({run.get('message')}); "
                         "refusing to write a completed case that would not describe a spill.")

    top = run["ais"]["candidates"][0]
    out = {
        "system": "OILTRACE",
        "version": "2.0",
        "detection": {"prediction": run["detection"]["prediction"],
                      "class": run["detection"]["class_id"],
                      "confidence": round(run["detection"]["confidence"], 4)},
        "spill": {"latitude": run["spill"]["latitude"], "longitude": run["spill"]["longitude"]},
        "hindcast": {"latitude": run["source"]["latitude"], "longitude": run["source"]["longitude"],
                     "hours_backward": run["source"]["hours_backward"]},
        "ais": {"candidate_count": run["ais"]["candidate_count"], "top_mmsi": top["mmsi"],
                "minimum_distance_km": top["minimum_distance_km"],
                "trajectory_status": top["trajectory_status"],
                "trajectory_score": top["trajectory_score"],
                "behaviour_score": top["behaviour_score"],
                "final_suspect_score": top["final_suspect_score"]},
        "forecast": [{"hours_ahead": p["hours_ahead"], "latitude": round(p["latitude"], 6),
                      "longitude": round(p["longitude"], 6)} for p in run["forecast"]["points"]],
        "interpretation": {"vessel_causation_proven": False,
                           "forecast_type": "kinematic_projection",
                           "requires_environmental_drift_data": True},
        "cnn_validation": metrics,
        "model_status": {"cnn_validated": True, "test_samples": metrics["test_samples"],
                         "roc_auc": metrics["roc_auc"], "f1_score": metrics["f1_score"]},
    }
    (AI_OUTPUT_DIR / "oiltrace_ai_output_final.json").write_text(json.dumps(out, indent=4) + "\n")
    (AI_OUTPUT_DIR / "cnn_validation_metrics.json").write_text(json.dumps(metrics, indent=4) + "\n")
    print("wrote oiltrace_ai_output_final.json and cnn_validation_metrics.json")
    print("  detection:", out["detection"])
    print("  ais:", out["ais"])


if __name__ == "__main__":
    main()
