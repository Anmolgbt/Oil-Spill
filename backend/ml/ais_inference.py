"""
Live inference for the trained AIS behavioural-anomaly model.

The cleaning, the features and the model all come from the AIS notebook
(OILTRACE_AIS_Final.ipynb) through ONE shared implementation, ml/oiltrace_ais.py -
the same file the notebook wrote and trained with. What this module adds is only
the shape the rest of the backend already expects (predict_track, scored_corpus,
model_info, warm_up).

    saved model    artifacts/ais_anomaly_model.joblib   IsolationForest(300 trees,
                                                        contamination 0.02) + its
                                                        StandardScaler + calibration
    metadata       artifacts/ais_anomaly_model_meta.json

What changed from the previous model, and why it matters:

1. AIS "not available" codes are not data. SOG 102.3, COG 360 and heading 511 mean
   "no value". The previous model fed 102.3 knots straight into the forest, so a
   missing-value flag was scored as the most extreme behaviour in the corpus.
   They are now cleared, and speed and course are RECOVERED from the position
   track where possible.
2. Features are computed inside a track segment only (a gap over 15 minutes starts
   a new segment), so a vessel's absence between two visits is not "behaviour".
3. Features are location independent - speed, acceleration, turn rate and the
   disagreement between reported speed and the speed the positions imply. The
   previous model also used raw course and latitude-free gaps, which let shipping
   lane direction masquerade as anomaly.
4. The 0-100 score uses a FIXED calibration learned on the training corpus (0 =
   median unusualness, 100 = its 99.5th percentile). It no longer depends on
   re-scoring a reference corpus at request time, so any single vessel's track can
   be scored on the same scale.

Scoring:

    anomaly_score    calibrated 0-100, per record
    is_anomaly       IsolationForest.predict == -1
    behaviour_score  per vessel: max(anomaly_score) over its records (unchanged)

Because the model needs positions (reported speed is cross-checked against the
speed the positions imply), records must carry LAT and LON as well as the four
fields the previous model needed.

The model is UNSUPERVISED. "Anomalous" means statistically unusual compared with
the training traffic. It is not a finding that anything was done wrong.
"""
import time

from core.config import AIS_REFERENCE_FILE, MODEL_ARTIFACTS_DIR

MODEL_FILE = MODEL_ARTIFACTS_DIR / "ais_anomaly_model.joblib"
META_FILE = MODEL_ARTIFACTS_DIR / "ais_anomaly_model_meta.json"

REQUIRED_COLUMNS = ["MMSI", "BaseDateTime", "SOG", "COG", "LAT", "LON"]

_model = None
_corpus = None


def _shared():
    """The cleaning / feature / model implementation shared with the notebook."""
    from ml import oiltrace_ais
    return oiltrace_ais


def _load():
    """Load the fitted model once and keep it."""
    global _model
    if _model is None:
        _model = _shared().AISAnomalyModel.load(str(MODEL_FILE))
    return _model


def features():
    """The behaviour features, in the order the saved scaler was fitted on."""
    return list(_shared().FEATURES)


def scored_corpus():
    """
    The full AIS reference corpus with per-record anomaly scores.

    Built once and cached. Columns keep the names the rest of the backend uses
    (MMSI, BaseDateTime, LAT, LON, SOG, COG) plus anomaly_score and is_anomaly.
    SOG and COG are the CLEANED values - missing-value codes cleared, recovered from
    the track where possible. A vessel's first fix in each track segment has no
    predecessor to difference against and is dropped, as before.
    """
    global _corpus
    if _corpus is not None:
        return _corpus
    if not AIS_REFERENCE_FILE.is_file():
        return None

    import pandas as pd

    A = _shared()
    model = _load()
    clean, _ = A.clean_ais(pd.read_csv(AIS_REFERENCE_FILE))
    feat = A.build_features(clean)
    scored = feat.join(model.score(feat))
    scored = scored[scored["anomaly_score"].notna()]

    _corpus = pd.DataFrame({
        "MMSI": scored["mmsi"].astype("int64"),
        "BaseDateTime": scored["time"],
        "LAT": scored["lat"],
        "LON": scored["lon"],
        "SOG": scored["sog"],
        "COG": scored["cog"],
        "anomaly_score": scored["anomaly_score"].astype(float),
        "is_anomaly": scored["is_anomaly"].astype(bool),
    }).reset_index(drop=True)
    return _corpus


def predict_track(records, mmsi=None):
    """
    Score one vessel's AIS history.

    `records` are dicts with MMSI, BaseDateTime, SOG, COG, LAT and LON. Returns the
    model's per-record verdicts aggregated to the vessel, plus the derived scores.
    """
    if not records:
        raise ValueError("No AIS records supplied.")

    import numpy as np
    import pandas as pd

    A = _shared()
    model = _load()

    df = pd.DataFrame(records)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    clean, report = A.clean_ais(df)
    feat = A.build_features(clean)
    started = time.perf_counter()
    scored = feat.join(model.score(feat))
    scored = scored[scored["anomaly_score"].notna()]
    elapsed_ms = (time.perf_counter() - started) * 1000

    if scored.empty:
        raise ValueError(
            "Not enough usable records. The first fix of every track segment is dropped "
            "(no predecessor to difference against), so at least two valid, time-ordered "
            "records with positions, no more than 15 minutes apart, are required."
        )

    total = int(len(scored))
    anomalous = int(scored["is_anomaly"].sum())
    scores = scored["anomaly_score"].to_numpy(dtype=float)
    behaviour = float(min(100.0, max(0.0, scores.max())))

    raw = -model.detector.decision_function(model.scaler.transform(scored[A.FEATURES].values))

    return {
        "mmsi": str(mmsi if mmsi is not None else scored["mmsi"].iloc[0]),
        "is_anomalous": bool(anomalous > 0),
        "anomalous_points": anomalous,
        "total_points": total,
        "anomaly_ratio": round(anomalous / total, 6) if total else None,
        "behaviour_score": round(behaviour, 2),
        "mean_anomaly_score": round(float(scores.mean()), 2),
        "raw_prediction": -1 if bool(scored["is_anomaly"].iloc[int(np.argmax(scores))]) else 1,
        "decision_score_max_unusualness": round(float(raw.max()), 6),
        "decision_score_mean_unusualness": round(float(raw.mean()), 6),
        "records_dropped_first_fix": len(records) - total,
        "sog_recovered_from_track": int(report.get("sog_recovered_from_track", 0)),
        "sog_missing_value_codes_cleared": int(report.get("sog_sentinel_or_invalid", 0)),
        "inference_ms": round(elapsed_ms, 2),
        "normalisation": {"type": "fixed calibration", **model.calib,
                          "source": "training corpus (median -> 0, 99.5th percentile -> 100)"},
        "features": list(A.FEATURES),
        "model": "IsolationForest — behavioural anomaly detection",
        "provenance": {"source": "ml_model", "model_version": MODEL_FILE.name},
    }


def model_info():
    """Artifact status and the parameters the saved model actually carries."""
    try:
        import sklearn
        model = _load()
        det, scaler = model.detector, model.scaler
        meta = model.meta
        return {
            "available": True,
            "model_file": MODEL_FILE.name,
            "scaler_file": MODEL_FILE.name,        # scaler and model are saved together
            "model_type": type(det).__name__,
            "scaler_type": type(scaler).__name__,
            "n_estimators": int(det.n_estimators),
            "contamination": det.contamination,
            "random_state": det.random_state,
            "n_features": int(det.n_features_in_),
            "features": features(),
            "scaler_feature_names": features(),
            "scaler_samples_seen": int(scaler.n_samples_seen_),
            "training_rows": meta.get("n_training_rows"),
            "calibration": meta.get("calibration"),
            "sklearn_version": sklearn.__version__,
            "pickled_with_sklearn": meta.get("sklearn_version"),
            "reference_corpus": AIS_REFERENCE_FILE.name if AIS_REFERENCE_FILE.is_file() else None,
            "live_inference": True,
        }
    except Exception as exc:
        return {
            "available": False,
            "model_present": MODEL_FILE.is_file(),
            "error": f"{type(exc).__name__}: {exc}",
            "live_inference": False,
        }


def warm_up():
    """
    Load the model and score the reference corpus ahead of the first request.

    Scoring the corpus is only needed by /ai/investigate (it searches that corpus);
    doing it at boot keeps that cost away from whoever triggers the first request.
    Returns a short summary so the caller can log what was actually warmed.
    """
    result = {"models": False, "corpus_records": None, "calibration": None}
    try:
        _load()
        result["models"] = True
        result["calibration"] = _load().calib
    except Exception:
        return result
    corpus = scored_corpus()
    if corpus is not None:
        result["corpus_records"] = int(len(corpus))
    return result
