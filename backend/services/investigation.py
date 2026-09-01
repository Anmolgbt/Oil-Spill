"""
End-to-end investigation using the two trained models.

    satellite image -> live CNN classification        (ml/cnn_inference.py)
      oil detected? -> hindcast to a probable source  (notebook cell 41)
                    -> AIS candidate search           (notebook cells 52/53)
                    -> live Isolation Forest scoring  (ml/ais_inference.py)
                    -> vessel ranking                 (notebook cell 54)
                    -> kinematic forecast             (notebook cell 57)

Every numeric step below is the notebook's own arithmetic, kept as-is so a live
run matches the completed case. Constants carry the cell they come from.

Scientific limits, unchanged from the static integration and enforced here:

* The CNN is a binary classifier. It yields a class and a confidence, and no
  mask, boundary, area, thickness or volume. It also produces no geolocation,
  so the spill coordinate is an INPUT to this pipeline, not a model output
  (the notebook sets it by hand in cells 41/57).
* The hindcast is a straight-line back-projection using an assumed drift vector
  (1.5 km/h toward 135 deg). It is a model estimate, never a confirmed source.
* The forecast is a kinematic projection (1.0 km/h toward 180 deg), not drift
  physics. No wind, current, wave or oil-property data is involved anywhere.
* The vessel ranking is an analytical association, not proof of causation.
"""
import time
from math import atan2, cos, radians, sin, sqrt

from core.config import COMPUTED_PROVENANCE

# --- notebook constants ------------------------------------------------------

# cell 41 - backward drift assumption
HINDCAST_DRIFT_SPEED_KMH = 1.5
HINDCAST_DRIFT_DIRECTION_DEG = 135.0
HINDCAST_HOURS = 24

# cells 52/53 - candidate search
SEARCH_TIME_BEFORE_HOURS = 2
SEARCH_TIME_AFTER_HOURS = 2
MAX_DISTANCE_KM = 50

# cell 54 - trajectory window and final weights
TRAJECTORY_BEFORE_HOURS = 6
TRAJECTORY_AFTER_HOURS = 2
WEIGHT_PROXIMITY = 0.40
WEIGHT_TRAJECTORY = 0.30
WEIGHT_BEHAVIOUR = 0.30

# cell 57 - forward kinematic projection
FORECAST_DRIFT_SPEED_KMH = 1.0
FORECAST_DRIFT_DIRECTION_DEG = 180.0
FORECAST_HOURS = [6, 12, 24, 48]

# The notebook's own defaults for the completed case (cells 41/52/57). These are
# inputs, not model outputs; callers may override them.
DEFAULT_SPILL_LAT = 28.57
DEFAULT_SPILL_LON = -94.80
DEFAULT_SOURCE_TIME = "2021-02-17 08:00:00"

KM_PER_DEGREE_LAT = 111.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Notebook cells 52/53, verbatim."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


# --- step 2: hindcast (cell 41) ----------------------------------------------

def hindcast(spill_lat, spill_lon, hours=HINDCAST_HOURS):
    """Back-project the slick along the assumed drift vector."""
    import numpy as np

    theta = np.radians(HINDCAST_DRIFT_DIRECTION_DEG)
    distance_km = HINDCAST_DRIFT_SPEED_KMH * hours
    dx_km = distance_km * np.sin(theta)
    dy_km = distance_km * np.cos(theta)

    lat_per_km = 1 / 111
    lon_per_km = 1 / (111 * np.cos(np.radians(spill_lat)))

    return {
        "latitude": float(spill_lat - dy_km * lat_per_km),
        "longitude": float(spill_lon - dx_km * lon_per_km),
        "hours_backward": hours,
        "drift_speed_kmh": HINDCAST_DRIFT_SPEED_KMH,
        "drift_direction_deg": HINDCAST_DRIFT_DIRECTION_DEG,
        "label": "Probable Source — Model Estimate",
        "confirmed": False,
        "confidence": None,
        "method": "Straight-line back-projection using an assumed drift vector",
        "environmental_data_used": False,
        "evidence_class": "MODEL ESTIMATE",
    }


# --- steps 3-5: AIS search, behaviour, trajectory, ranking (cells 52-54) -----

def rank_candidates(source_lat, source_lon, source_time):
    """
    Reconstruct traffic around the estimated source and rank it.

    Uses the corpus scored once by the saved Isolation Forest, then applies the
    notebook's proximity / trajectory / behaviour arithmetic.
    """
    import pandas as pd

    from ml.ais_inference import scored_corpus

    corpus = scored_corpus()
    if corpus is None:
        return None

    source_time = pd.Timestamp(source_time)
    before = pd.Timedelta(hours=SEARCH_TIME_BEFORE_HOURS)
    after = pd.Timedelta(hours=SEARCH_TIME_AFTER_HOURS)

    # 1. records inside the search window
    window = corpus[
        (corpus["BaseDateTime"] >= source_time - before)
        & (corpus["BaseDateTime"] <= source_time + after)
    ].copy()
    records_in_window = int(len(window))

    # 2. distance to the estimated source
    window["distance_km"] = window.apply(
        lambda r: haversine_km(source_lat, source_lon, r["LAT"], r["LON"]), axis=1
    )

    # 3. drop irrelevant traffic
    candidates = window[window["distance_km"] <= MAX_DISTANCE_KM].copy()

    if candidates.empty:
        return {
            "records_in_window": records_in_window,
            "records_within_radius": 0,
            "candidate_count": 0,
            "candidates": [],
            "search_radius_km": MAX_DISTANCE_KM,
            "source_time": str(source_time),
        }

    # 4. vessel-level statistics
    ranking = (
        candidates.groupby("MMSI")
        .agg(
            records=("MMSI", "size"),
            min_distance_km=("distance_km", "min"),
            avg_distance_km=("distance_km", "mean"),
            avg_anomaly=("anomaly_score", "mean"),
            max_anomaly=("anomaly_score", "max"),
            anomaly_records=("is_anomaly", "sum"),
            avg_speed=("SOG", "mean"),
            avg_course=("COG", "mean"),
        )
        .reset_index()
    )

    # 5. proximity and behaviour scores
    ranking["proximity_score"] = (
        100 * (1 - ranking["min_distance_km"] / MAX_DISTANCE_KM)
    ).clip(0, 100)
    ranking["behaviour_score"] = ranking["max_anomaly"].clip(0, 100)

    # 6. trajectory analysis over a wider window
    traj_before = pd.Timedelta(hours=TRAJECTORY_BEFORE_HOURS)
    traj_after = pd.Timedelta(hours=TRAJECTORY_AFTER_HOURS)
    traj = corpus[
        (corpus["BaseDateTime"] >= source_time - traj_before)
        & (corpus["BaseDateTime"] <= source_time + traj_after)
        & (corpus["MMSI"].isin(ranking["MMSI"].tolist()))
    ].copy()
    traj["distance_to_source_km"] = traj.apply(
        lambda r: haversine_km(source_lat, source_lon, r["LAT"], r["LON"]), axis=1
    )
    traj = traj.sort_values(["MMSI", "BaseDateTime"])

    rows = []
    for mmsi, vessel in traj.groupby("MMSI"):
        vessel = vessel.sort_values("BaseDateTime")
        start_distance = vessel["distance_to_source_km"].iloc[0]
        end_distance = vessel["distance_to_source_km"].iloc[-1]
        min_distance = vessel["distance_to_source_km"].min()
        closest = vessel.loc[vessel["distance_to_source_km"].idxmin()]

        movement = ("Approaching source" if end_distance < start_distance
                    else "Moving away / not approaching")
        approach = ((start_distance - min_distance) / start_distance * 100
                    if start_distance > 0 else 0)

        rows.append({
            "MMSI": mmsi,
            "start_distance_km": float(start_distance),
            "closest_distance_km": float(min_distance),
            "end_distance_km": float(end_distance),
            "closest_time": str(closest["BaseDateTime"]),
            "trajectory_status": movement,
            "trajectory_score": float(min(max(approach, 0), 100)),
        })

    ranking = ranking.merge(pd.DataFrame(rows), on="MMSI", how="left")

    # 7. final weighted score
    ranking["final_suspect_score"] = (
        WEIGHT_PROXIMITY * ranking["proximity_score"]
        + WEIGHT_TRAJECTORY * ranking["trajectory_score"]
        + WEIGHT_BEHAVIOUR * ranking["behaviour_score"]
    )
    ranking = ranking.sort_values("final_suspect_score", ascending=False)

    out = []
    for rank, (_, r) in enumerate(ranking.iterrows(), start=1):
        out.append({
            "rank": rank,
            "mmsi": int(r["MMSI"]),
            "records": int(r["records"]),
            "minimum_distance_km": round(float(r["min_distance_km"]), 2),
            "proximity_score": round(float(r["proximity_score"]), 2),
            "trajectory_status": r.get("trajectory_status"),
            "trajectory_score": None if pd.isna(r.get("trajectory_score")) else round(float(r["trajectory_score"]), 2),
            "behaviour_score": round(float(r["behaviour_score"]), 2),
            "final_suspect_score": round(float(r["final_suspect_score"]), 2),
            "anomalous_records": int(r["anomaly_records"]),
            "latitude": None,      # the ranking is vessel-level; no single fix
            "longitude": None,
        })

    return {
        "records_in_window": records_in_window,
        "records_within_radius": int(len(candidates)),
        "candidate_count": int(len(out)),
        "candidates": out,
        "search_radius_km": MAX_DISTANCE_KM,
        "source_time": str(source_time),
        "weights": {
            "proximity": WEIGHT_PROXIMITY,
            "trajectory": WEIGHT_TRAJECTORY,
            "behaviour": WEIGHT_BEHAVIOUR,
        },
        "model": "IsolationForest — behavioural anomaly detection",
        "evidence_class": "ANALYTICAL RANKING",
    }


# --- step 6: forward kinematic projection (cell 57) --------------------------

def forecast(spill_lat, spill_lon, hours=None):
    """Project the slick forward. Kinematic only — no environmental data."""
    import numpy as np

    horizons = hours or FORECAST_HOURS
    direction_rad = np.radians(FORECAST_DRIFT_DIRECTION_DEG)
    points = []

    for h in horizons:
        distance_km = FORECAST_DRIFT_SPEED_KMH * h
        km_per_degree_lon = 111.0 * np.cos(np.radians(spill_lat))
        delta_lat = distance_km * np.cos(direction_rad) / KM_PER_DEGREE_LAT
        delta_lon = distance_km * np.sin(direction_rad) / km_per_degree_lon
        points.append({
            "hours_ahead": h,
            "latitude": float(spill_lat + delta_lat),
            "longitude": float(spill_lon + delta_lon),
        })

    return {
        "type": "kinematic_projection",
        "label": "Kinematic Movement Projection",
        "requires_environmental_drift_data": True,
        "warning": ("Environmental wind, currents, waves and oil properties are "
                    "not currently incorporated."),
        "drift_speed_kmh": FORECAST_DRIFT_SPEED_KMH,
        "drift_direction_deg": FORECAST_DRIFT_DIRECTION_DEG,
        "points": points,
        "wind": None, "current": None, "wave": None,
        "evidence_class": "PREDICTION",
    }


# --- orchestration -----------------------------------------------------------

def run_live_investigation(image_bytes=None, image_path=None, spill_lat=None,
                           spill_lon=None, source_time=None):
    """
    Run the full pipeline with both trained models.

    `spill_lat` / `spill_lon` are required inputs because the classifier cannot
    geolocate; they default to the notebook's completed-case coordinates. The run
    stops after classification when no oil is detected.
    """
    from ml.ais_inference import model_info as ais_info
    from ml.cnn_inference import model_info as cnn_info
    from ml.cnn_inference import predict_image

    started = time.perf_counter()

    spill_lat = DEFAULT_SPILL_LAT if spill_lat is None else float(spill_lat)
    spill_lon = DEFAULT_SPILL_LON if spill_lon is None else float(spill_lon)
    source_time = source_time or DEFAULT_SOURCE_TIME

    # 1. live CNN classification
    detection = predict_image(image_bytes=image_bytes, image_path=image_path)
    steps = {"detection": detection}

    provenance = {
        "oil_detection": {"source": "ml_model",
                          "model_version": cnn_info().get("checkpoint")},
        "anomaly_detection": {"source": "ml_model",
                              "model_version": ais_info().get("model_file")},
        "hindcast": COMPUTED_PROVENANCE,
        "ranking": COMPUTED_PROVENANCE,
        "forecast": COMPUTED_PROVENANCE,
        "live_inference": True,
    }

    spill = {
        "latitude": spill_lat,
        "longitude": spill_lon,
        "source": "supplied_input",
        "note": "The classifier does not geolocate; this coordinate is an input.",
        "estimated_area_km2": None,
        "oil_thickness": None,
        "oil_volume": None,
        "segmentation_mask": None,
        "evidence_class": "SUPPLIED INPUT",
    }

    if detection["class_id"] != 1:
        return {
            "status": "CLEAR",
            "mode": "LIVE_INFERENCE",
            "message": (f"CNN classified the image as {detection['prediction']} "
                        f"({detection['confidence'] * 100:.2f}%). "
                        "No investigation run."),
            "detection": detection,
            "spill": spill,
            "steps": steps,
            "provenance": provenance,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    # 2. hindcast to a probable source
    source = hindcast(spill_lat, spill_lon)
    steps["hindcast"] = source

    # 3-5. AIS search + Isolation Forest behaviour + ranking
    ais = rank_candidates(source["latitude"], source["longitude"], source_time)
    steps["ais"] = ais

    # 6. forward kinematic projection
    fc = forecast(spill_lat, spill_lon)
    steps["forecast"] = fc

    top = ais["candidates"][0] if ais and ais["candidates"] else None

    return {
        "status": "SPILL_CONFIRMED",
        "mode": "LIVE_INFERENCE",
        "detection": detection,
        "spill": spill,
        "source": source,
        "ais": ais,
        "forecast": fc,
        "top_suspect": top,
        "steps": steps,
        "provenance": provenance,
        "interpretation": {
            "vessel_causation_proven": False,
            "forecast_type": "kinematic_projection",
            "requires_environmental_drift_data": True,
            "ranking_meaning": (
                "This ranking indicates analytical association with the estimated "
                "source window. It does not establish legal responsibility."
            ),
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
