"""
Live inference for the trained AIS behavioural-anomaly model.

Reproduced verbatim from the authoritative Colab notebook. The notebook contains
TWO parallel AIS pipelines; the saved artifacts are from the FIRST one, which the
artifacts themselves prove:

    saved model   IsolationForest(n_estimators=200, contamination=0.02,
                                  random_state=42), n_features_in_ = 5
                  -> notebook cell 14  (cell 19's variant used 300 estimators
                     and 4 features, and was NOT saved)
    saved scaler  StandardScaler, n_samples_seen_ = 52596
                  -> 52943 raw records - 347 vessels dropped by the first-row
                     dropna in cell 13. Confirms cells 12/13 as the feature path.
    feature order carried on the scaler as feature_names_in_:
                  ["SOG", "speed_change", "COG", "course_change",
                   "time_gap_minutes"]

Feature engineering (cells 12-13), applied here exactly:

    BaseDateTime      pd.to_datetime(..., errors="coerce")
    sort              sort_values(["MMSI", "BaseDateTime"])
    speed_change      groupby("MMSI")["SOG"].diff().abs()
    course_change     groupby("MMSI")["COG"].diff().abs()     <- naive, see below
    time_gap_minutes  groupby("MMSI")["BaseDateTime"].diff().dt.total_seconds()/60
    dropna            on the three derived columns (drops each vessel's first row)

KNOWN LIMITATION, reproduced deliberately: cell 13 takes the naive absolute
course difference, so 359 deg -> 1 deg is recorded as 358, not 2. The notebook's
other pipeline (cell 18) corrects this with min(diff, 360-diff), but that
pipeline's model was not saved. Reproducing the naive form is required for
compatibility with the saved scaler's mean_/scale_. Do not "fix" it here without
retraining.

Scoring (cell 15, then cells 52/53):

    anomaly_raw    model.decision_function(X_scaled)
    anomaly_score  100 * (max_raw - anomaly_raw) / (max_raw - min_raw)
    is_anomaly     model.predict(X_scaled) == -1        (-1 = anomalous, 1 = normal)
    behaviour_score  per vessel: max(anomaly_score) over its records, clipped 0-100

CRITICAL: anomaly_score is normalised against the DATASET-WIDE min and max of
decision_function. It is therefore not computable from a single vessel's records
in isolation - the same track yields a different score depending on the corpus it
is normalised against. The reference corpus the notebook used is bundled at
data/ais_reference/ais_dataset.csv and its min/max are computed once here, so a
single-vessel request is scored on the same scale the completed case used.
"""
import time

from core.config import AIS_REFERENCE_FILE, MODEL_ARTIFACTS_DIR

MODEL_FILE = MODEL_ARTIFACTS_DIR / "ais_isolation_forest.pkl"
SCALER_FILE = MODEL_ARTIFACTS_DIR / "ais_scaler.pkl"

# Notebook cell 14. Also carried on the saved scaler as feature_names_in_.
FEATURES = ["SOG", "speed_change", "COG", "course_change", "time_gap_minutes"]
REQUIRED_COLUMNS = ["MMSI", "BaseDateTime", "SOG", "COG"]

_bundle = None
_norm = None


def _load():
    """Load scaler + model once and keep them."""
    global _bundle
    if _bundle is None:
        import joblib
        _bundle = (joblib.load(SCALER_FILE), joblib.load(MODEL_FILE))
    return _bundle


def build_features(records):
    """
    Derive the notebook's movement features for one or more vessels.

    Returns the frame after the cell-13 dropna, which removes each vessel's first
    record because it has no predecessor to difference against.
    """
    import pandas as pd

    df = pd.DataFrame(records)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    df["BaseDateTime"] = pd.to_datetime(df["BaseDateTime"], errors="coerce")
    for col in ("SOG", "COG"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(["MMSI", "BaseDateTime"]).reset_index(drop=True)

    df["speed_change"] = df.groupby("MMSI")["SOG"].diff().abs()
    # Naive absolute difference, exactly as cell 13. No circular wrapping.
    df["course_change"] = df.groupby("MMSI")["COG"].diff().abs()
    df["time_gap_minutes"] = (
        df.groupby("MMSI")["BaseDateTime"].diff().dt.total_seconds() / 60
    )

    return df.dropna(subset=["speed_change", "course_change", "time_gap_minutes"])


def _reference_normalisation():
    """
    Dataset-wide min/max of decision_function over the notebook's AIS corpus.

    Computed once. Without this, anomaly_score (and therefore behaviour_score)
    cannot be placed on the same 0-100 scale the completed case used.
    """
    global _norm
    if _norm is not None:
        return _norm
    if not AIS_REFERENCE_FILE.is_file():
        return None

    import pandas as pd

    scaler, model = _load()
    raw = pd.read_csv(AIS_REFERENCE_FILE)
    df = build_features(raw)
    scores = model.decision_function(scaler.transform(df[FEATURES]))
    _norm = {
        "min_raw": float(scores.min()),
        "max_raw": float(scores.max()),
        "records": int(len(df)),
        "source": AIS_REFERENCE_FILE.name,
    }
    return _norm


_corpus = None


def scored_corpus():
    """
    The full AIS corpus with per-record anomaly scores, exactly as notebook
    cell 15 produces them.

    The notebook scores every record once over the whole dataset and then slices
    that scored frame per candidate, so the corpus is built once and cached here
    rather than rescored per request.
    """
    global _corpus
    if _corpus is not None:
        return _corpus
    if not AIS_REFERENCE_FILE.is_file():
        return None

    import pandas as pd

    scaler, model = _load()
    df = build_features(pd.read_csv(AIS_REFERENCE_FILE))
    X_scaled = scaler.transform(df[FEATURES])

    df = df.copy()
    df["anomaly_raw"] = model.decision_function(X_scaled)
    min_raw = df["anomaly_raw"].min()
    max_raw = df["anomaly_raw"].max()
    df["anomaly_score"] = 100 * (max_raw - df["anomaly_raw"]) / (max_raw - min_raw)
    df["is_anomaly"] = model.predict(X_scaled) == -1

    _corpus = df
    return _corpus


def predict_track(records, mmsi=None):
    """
    Score one vessel's AIS history.

    Returns the raw Isolation Forest output alongside the notebook's derived
    scores. behaviour_score is None when no reference corpus is available,
    because it cannot be honestly computed from one vessel alone.
    """
    if not records:
        raise ValueError("No AIS records supplied.")

    scaler, model = _load()
    df = build_features(records)
    if df.empty:
        raise ValueError(
            "Not enough usable records. Each vessel's first fix is dropped "
            "(no predecessor to difference against), so at least two valid, "
            "time-ordered records per vessel are required."
        )

    started = time.perf_counter()
    X_scaled = scaler.transform(df[FEATURES])          # transform only, never fit
    anomaly_raw = model.decision_function(X_scaled)
    raw_prediction = model.predict(X_scaled)           # -1 anomalous, 1 normal
    elapsed_ms = (time.perf_counter() - started) * 1000

    is_anomaly = raw_prediction == -1
    total = int(len(df))
    anomalous = int(is_anomaly.sum())

    norm = _reference_normalisation()
    if norm and norm["max_raw"] > norm["min_raw"]:
        span = norm["max_raw"] - norm["min_raw"]
        anomaly_score = 100 * (norm["max_raw"] - anomaly_raw) / span
        behaviour_score = float(min(100.0, max(0.0, anomaly_score.max())))
        mean_anomaly = float(anomaly_score.mean())
    else:
        anomaly_score = None
        behaviour_score = None
        mean_anomaly = None

    return {
        "mmsi": str(mmsi if mmsi is not None else df["MMSI"].iloc[0]),
        "is_anomalous": bool(anomalous > 0),
        "anomalous_points": anomalous,
        "total_points": total,
        "anomaly_ratio": round(anomalous / total, 6) if total else None,
        "behaviour_score": None if behaviour_score is None else round(behaviour_score, 2),
        "mean_anomaly_score": None if mean_anomaly is None else round(mean_anomaly, 2),
        "raw_prediction": int(raw_prediction[int(anomaly_raw.argmin())]),
        "decision_score_min": round(float(anomaly_raw.min()), 6),
        "decision_score_mean": round(float(anomaly_raw.mean()), 6),
        "records_dropped_first_fix": len(records) - total,
        "inference_ms": round(elapsed_ms, 2),
        "normalisation": norm,
        "features": FEATURES,
        "model": "IsolationForest — behavioural anomaly detection",
        "provenance": {"source": "ml_model", "model_version": MODEL_FILE.name},
    }


def model_info():
    """Artifact status and the parameters the saved model actually carries."""
    try:
        import sklearn
        scaler, model = _load()
        names = getattr(scaler, "feature_names_in_", None)
        return {
            "available": True,
            "model_file": MODEL_FILE.name,
            "scaler_file": SCALER_FILE.name,
            "model_type": type(model).__name__,
            "scaler_type": type(scaler).__name__,
            "n_estimators": int(model.n_estimators),
            "contamination": model.contamination,
            "random_state": model.random_state,
            "n_features": int(model.n_features_in_),
            "features": FEATURES,
            "scaler_feature_names": list(names) if names is not None else None,
            "scaler_samples_seen": int(scaler.n_samples_seen_),
            "sklearn_version": sklearn.__version__,
            "pickled_with_sklearn": "1.6.1",
            "reference_corpus": AIS_REFERENCE_FILE.name if AIS_REFERENCE_FILE.is_file() else None,
            "course_change_is_circular": False,
            "live_inference": True,
        }
    except Exception as exc:
        return {
            "available": False,
            "model_present": MODEL_FILE.is_file(),
            "scaler_present": SCALER_FILE.is_file(),
            "error": f"{type(exc).__name__}: {exc}",
            "live_inference": False,
        }
