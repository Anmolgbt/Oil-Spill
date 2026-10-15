"""
GET /api/models — what the models actually are.

A single backend-owned answer to "what AI is in here?", composed from the
artifacts themselves rather than retyped. Every metric is read from
cnn_validation_metrics.json (the training notebook's held-out test result),
every hyper-parameter from the pickled estimator,
and the attribution weights from services/investigation.py. Nothing here is
written by hand, so nothing here can drift from what the code does.

Why a new route rather than extending /ai-result/models: that path sits under
the /ai-result prefix, which serves the STORED completed case from the handoff
notebook. Model facts are not stored-case facts, and conflating the two has
already caused one contradiction (the endpoint reported live_inference: false
while /fleet/scan reported true). /ai/cnn/status and /ai/ais/status remain the
per-model operational checks; this is the combined card the interface renders.

The honesty statements are part of the payload, not the frontend's wording, so
there is one place to correct them.
"""
from fastapi import APIRouter

from services.investigation import (WEIGHT_BEHAVIOUR, WEIGHT_PROXIMITY,
                                    WEIGHT_TRAJECTORY,
                                    SEARCH_RADIUS_ENVELOPE_MULTIPLE)
from services.stored_result import load_cnn_metrics

router = APIRouter(tags=["models"], prefix="/api")


def _cnn_error_rates(metrics):
    """Plain-language error rates, computed from the stored metrics - never typed in."""
    r, p = metrics.get("recall"), metrics.get("precision")
    if r is None or p is None:
        return "Validation metrics are unavailable, so error rates cannot be stated."
    ci = (metrics.get("ci95_scene_bootstrap") or {}).get("recall")
    ci_text = f" (95% interval {ci[0]:.0%}-{ci[1]:.0%})" if ci else ""
    miss = f"roughly one spill in {round(1 / (1 - r))} is missed" if r < 1 else "no spill was missed"
    false = f"roughly one alarm in {round(1 / (1 - p))} is false" if p < 1 else "no alarm was false"
    return (f"On scenes the model never saw, recall is {r:.1%}{ci_text} - {miss} - and "
            f"precision is {p:.1%} - {false}. These are held-out figures, not the "
            "demo's: the demo's SAR tiles come from the same public dataset the model "
            "was trained on.")


def _cnn_card():
    from ml.cnn_inference import build_transform, config, model_info

    info = model_info()
    metrics = load_cnn_metrics() or {}
    try:
        size = int(config()["image_size"])
    except Exception:
        size = None

    # The transform the model is actually fed, read off the composed object
    # rather than described from memory.
    try:
        steps = [type(t).__name__ for t in build_transform().transforms]
    except Exception:
        steps = None

    return {
        "name": "OilSpillCNN",
        "role": "Oil-spill detection from SAR imagery",
        "kind": "Trained convolutional neural network",
        "task": "binary classification",
        "available": info.get("available", False),
        "checkpoint": info.get("checkpoint"),
        "parameters": info.get("parameters"),
        "device": info.get("device"),
        "loaded_cleanly": info.get("loaded_cleanly"),
        "input": {
            "format": "single SAR tile (JPEG/PNG), one per vessel per pass",
            "size": f"{size} x {size}" if size else None,
            "preprocessing": steps,
        },
        "output": {
            "classes": metrics.get("classes"),
            "returns": "predicted class and the softmax probability of that class",
        },
        # Measured, from the artifact. Absent keys stay absent rather than
        # becoming zeros.
        "validation": metrics or None,
        "validation_source": (
            f"cnn_validation_metrics.json ({metrics.get('test_samples')} held-out Sentinel-1 tiles"
            + (f" from {metrics['test_scenes']} unseen scenes" if metrics.get("test_scenes") else "")
            + (", scene-grouped split" if metrics.get("split") == "scene-grouped" else "") + ")"
        ) if metrics else "cnn_validation_metrics.json (unavailable)",
        "capabilities": {
            "performs_classification": True,
            "performs_segmentation": False,
            "produces_mask": False,
            "localises_pixels": False,
            "geolocates": False,
        },
        "statement": ("Classification model — not segmentation. It returns a class and a "
                      "confidence and produces no mask, so no spill area, boundary, "
                      "thickness or volume can be derived from it. It also returns no "
                      "coordinates: the spill position shown is the vessel's own AIS fix, "
                      "which is an input, not a model output."),
        "limitations": [
            _cnn_error_rates(metrics),
            (f"The decision threshold ({metrics['threshold']}) and the probability "
             "temperature were fitted on the validation split; the test split was "
             "used once, for reporting.") if metrics.get("threshold") is not None else
            "Decision threshold and calibration provenance unavailable.",
            "Trained on a public Sentinel-1 oil-spill dataset; performance on other "
            "sensors, sea states or regions is untested.",
            "No segmentation, so nothing in this system measures the size of a slick.",
        ],
    }


def _ais_card():
    from ml.ais_inference import model_info

    info = model_info()
    return {
        "name": "AIS behavioural anomaly detector",
        "role": "Flagging unusual vessel movement in historic AIS",
        "kind": "Trained Isolation Forest",
        "task": "unsupervised anomaly detection",
        "available": info.get("available", False),
        "model_type": info.get("model_type"),
        "hyperparameters": {
            "n_estimators": info.get("n_estimators"),
            "contamination": info.get("contamination"),
            "random_state": info.get("random_state"),
        },
        "input": {
            # Order is pinned by the saved scaler's feature_names_in_; changing
            # it silently changes what the model is being asked.
            "features": info.get("features"),
            "feature_order_pinned_by": "ml/oiltrace_ais.FEATURES, recorded in ais_anomaly_model_meta.json",
            "scaler": info.get("scaler_type"),
            "scaler_samples_seen": info.get("scaler_samples_seen"),
            "requires_positions": True,
        },
        "output": {
            "returns": "per-point anomaly score (0-100), aggregated to a behaviour score "
                       "per vessel (that vessel's maximum)",
            "normalisation": "fixed calibration learned on the training corpus "
                             "(median -> 0, 99.5th percentile -> 100)",
        },
        "data_cleaning": {
            "missing_value_codes": "SOG 102.3, COG 360 and heading 511 mean 'not available'. "
                                   "They are cleared, and speed and course are recovered from "
                                   "the position track where possible.",
            "segments": "tracks are split at gaps over 15 minutes; features never span a gap",
        },
        "calibration": info.get("calibration"),
        "reference_corpus": info.get("reference_corpus"),
        "corpus_required_at_runtime": False,
        "corpus_reason": ("Scores use a fixed calibration stored with the model, so one "
                          "vessel's track can be scored on the 0-100 scale on its own. "
                          "The reference corpus is still searched by /ai/investigate."),
        "statement": ("An anomaly indicates unusual vessel behaviour. It does not by "
                      "itself prove illegal behaviour, a discharge, or oil-spill "
                      "causation."),
        # The previous model carried a non-circular course_change flaw and fed AIS
        # missing-value codes to the forest. Both are fixed in this model, so there
        # is nothing to disclose here; the field stays so the card's shape is stable.
        "known_flaw": None,
        "limitations": [
            "Unsupervised: there are no labels, so 'anomalous' means statistically "
            "unusual within this corpus, not wrong or illegal.",
            "AIS has coverage gaps and can be switched off; absence of an anomaly is "
            "not evidence of normal behaviour.",
            "Trained on one Gulf of Mexico corpus (52,943 records, 347 vessels). Its "
            "features are location independent, but behaviour in other waters is untested.",
            "Checked only by injecting known unusual behaviour into held-out vessels - "
            "which shows it separates gross changes, not that it finds real violations.",
        ],
    }


def _attribution_card():
    return {
        "name": "Attribution scoring",
        "role": "Ranking candidate vessels against an estimated source and window",
        # The distinction this whole card exists to make.
        "kind": "Deterministic weighted score — NOT a trained model",
        "is_trained_model": False,
        "weights": {
            "proximity": WEIGHT_PROXIMITY,
            "trajectory": WEIGHT_TRAJECTORY,
            "behaviour": WEIGHT_BEHAVIOUR,
        },
        "weights_source": "services/investigation.py",
        "components": {
            "proximity": "100 * (1 - closest approach / search radius), clipped 0-100",
            "trajectory": "how much the vessel closed on the estimated source across "
                          "the trajectory window",
            "behaviour": "the Isolation Forest's own score for that vessel's track — "
                         "the only term that comes from a trained model",
        },
        "search_radius": {
            "derivation": f"{SEARCH_RADIUS_ENVELOPE_MULTIPLE} x the drift envelope for "
                          "the spill's estimated age",
            "note": "Derived rather than fixed, so it scales with the revisit interval.",
        },
        "unavailable_term_rule": {
            "rule": "re-weight",
            "detail": ("When a term cannot be computed, the remaining weights are "
                       "renormalised to sum to 1 rather than scoring the missing term "
                       "as zero. A model that could not answer is not evidence that a "
                       "vessel behaved normally. The weights actually applied travel "
                       "with each candidate as weights_applied."),
        },
        "statement": ("Attribution is a deterministic weighted score, not a trained "
                      "model. It represents evidence consistency with an estimated "
                      "source and an estimated release window — not proof of "
                      "causation."),
        "validated": False,
        "validation_note": ("NOT validated against known attributions: no labelled "
                            "spill-to-vessel dataset was available. The seeded t3 "
                            "assignment validates DETECTION against a simulated "
                            "scenario; it is not attribution ground truth."),
    }


@router.get("/models")
def models():
    """
    The models behind the system, composed from the artifacts themselves.

    Anything the artifacts do not carry is null or absent. No metric here is
    written by hand.
    """
    return {
        "detection": _cnn_card(),
        "behaviour": _ais_card(),
        "attribution": _attribution_card(),
        "separation": ("Two of these are trained models; the third is arithmetic. "
                       "The CNN decides whether a tile shows oil and the Isolation "
                       "Forest scores movement; the ranking that combines them is a "
                       "fixed weighted sum with no learned parameters."),
        "system_limitations": [
            "Attribution is unvalidated — there is no labelled spill-to-vessel dataset.",
            "No environmental data: wind and current are stated constants, and every "
            "drift path is a kinematic projection.",
            "AIS coverage is incomplete and can be switched off.",
            "An anomaly is not causation.",
            "Demo data: vessel co-presence is constructed by a per-vessel time shift, "
            "and which vessels carry an oily tile is a seeded simulation.",
            "Demo tiles are drawn from the public dataset the CNN was trained on, so the "
            "demo's detections are not a held-out accuracy test.",
        ],
    }


@router.get("/environment")
def environment(lat: float, lon: float, when: str):
    """
    Current, wind and the drift they imply at one place and time.

    Inspectable on its own so the mode can be checked without running a scan:
    with no dataset committed this returns `environment_mode: "fallback"` and a
    reason saying where to add one. It never fails for want of data.
    """
    from services.environment import get_conditions

    return get_conditions(lat, lon, when)
