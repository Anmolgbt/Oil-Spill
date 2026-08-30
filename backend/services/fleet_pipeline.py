"""
Fleet monitoring scan.

    latest satellite pass
      -> live CNN over every monitored ship's tile
      -> no oil anywhere? report CLEAR and stop
      -> oil found: strongest detection becomes the observed spill
      -> age bounded by the satellite revisit interval
      -> hindcast back over that interval to a probable source
      -> fleet AIS around that source, Isolation Forest behaviour, ranking
      -> forward kinematic forecast

Age is derived rather than assumed. A tile that was clear on the previous pass
and oily on this one holds oil at most one revisit old, so the pass interval
bounds the spill age and sets the hindcast window.

The affected area stays a DRIFT ENVELOPE - how far oil could have moved from the
probable source in that time - and never a measured slick. The classifier
produces no mask, so no true area exists.
"""
import json
import time
from datetime import timedelta

from core.config import COMPUTED_PROVENANCE, SIMULATION_DIR

from .geo import haversine_km, parse_time
from .investigation import (HINDCAST_DRIFT_DIRECTION_DEG, HINDCAST_DRIFT_SPEED_KMH,
                            MAX_DISTANCE_KM, SEARCH_TIME_AFTER_HOURS,
                            SEARCH_TIME_BEFORE_HOURS, TRAJECTORY_AFTER_HOURS,
                            TRAJECTORY_BEFORE_HOURS, WEIGHT_BEHAVIOUR,
                            WEIGHT_PROXIMITY, WEIGHT_TRAJECTORY, forecast)
from .snapshots import get_available_snapshots, get_latest_snapshot

FLEET_FILE = SIMULATION_DIR / "fleet.json"
DEFAULT_PASS_INTERVAL_HOURS = 8


def load_fleet():
    with open(FLEET_FILE, encoding="utf-8") as f:
        return json.load(f)


def _position_at(ship, when):
    """The ship's most recent AIS fix at or before `when`."""
    target = parse_time(when)
    track = ship.get("track") or []
    prior = [p for p in track if parse_time(p["time"]) <= target]
    fix = prior[-1] if prior else (track[0] if track else None)
    if not fix:
        return None
    age = (target - parse_time(fix["time"])).total_seconds() / 3600
    return {**fix, "age_hours": round(age, 2)}


def _pass_time(fleet, snapshot_id, interval_hours):
    """
    Acquisition time of a pass.

    Configured passes are looked up; anything dropped in later (t3, t4, ...) has
    its time derived from its index and the revisit interval, so adding a folder
    needs no config change.
    """
    times = fleet.get("snapshot_times", {})
    if snapshot_id in times:
        return times[snapshot_id]
    if not times:
        return None
    try:
        index = int(str(snapshot_id).lstrip("t"))
    except ValueError:
        return None
    base_id = min(times, key=lambda k: int(k.lstrip("t")))
    base = parse_time(times[base_id]) - timedelta(hours=interval_hours * int(base_id.lstrip("t")))
    return (base + timedelta(hours=interval_hours * index)).strftime("%Y-%m-%dT%H:%M:%SZ")


def scan_fleet(snapshot_id=None):
    """Run the CNN over every ship's tile in one satellite pass."""
    from ml.cnn_inference import predict_image

    from .snapshots import get_snapshot_data

    fleet = load_fleet()
    snapshot_id = snapshot_id or get_latest_snapshot()
    snapshot = get_snapshot_data(snapshot_id) if snapshot_id else None
    if snapshot is None:
        return None

    interval = fleet.get("pass_interval_hours", DEFAULT_PASS_INTERVAL_HOURS)
    observed_at = _pass_time(fleet, snapshot_id, interval)
    available = {s["id"]: s for s in snapshot["ships"]}

    ships = []
    for ship in fleet["ships"]:
        image_url = available.get(ship["id"], {}).get("image_url")
        fix = _position_at(ship, observed_at) if observed_at else None

        record = {
            "id": ship["id"], "mmsi": ship["mmsi"], "name": ship["name"],
            "vessel_type": ship["vessel_type"], "image_url": image_url,
            "latitude": fix["lat"] if fix else ship["latitude"],
            "longitude": fix["lon"] if fix else ship["longitude"],
            "speed_kt": fix["speed_kt"] if fix else ship["speed_kt"],
            "course_deg": fix["course_deg"] if fix else ship["course_deg"],
            "position_time": fix["time"] if fix else None,
            "track": ship.get("track", []),
        }

        if not image_url:
            record.update({"status": "NO IMAGE", "oil_detected": False,
                           "prediction": None, "confidence": None})
        else:
            path = SIMULATION_DIR / "snapshots" / snapshot_id / ship["image_filename"]
            result = predict_image(image_path=path)
            record.update({
                "status": "OIL DETECTED" if result["class_id"] == 1 else "CLEAR",
                "oil_detected": result["class_id"] == 1,
                "prediction": result["prediction"],
                "confidence": result["confidence"],
            })
        ships.append(record)

    detections = sorted([s for s in ships if s["oil_detected"]],
                        key=lambda s: s["confidence"], reverse=True)

    return {
        "snapshot_id": snapshot_id, "observed_at": observed_at,
        "available_snapshots": get_available_snapshots(),
        "pass_interval_hours": fleet.get("pass_interval_hours", DEFAULT_PASS_INTERVAL_HOURS),
        "scanned": len(ships), "ships": ships,
        "oil_detected": bool(detections), "detections": detections,
        "region": fleet.get("region"), "synthetic_fleet": bool(fleet.get("synthetic")),
    }


def hindcast_over(spill_lat, spill_lon, hours):
    """
    Back-project the slick along the assumed drift vector for `hours`.

    Same arithmetic as the notebook's hindcast; the window comes from the revisit
    cadence instead of being fixed at 24 h.
    """
    import numpy as np

    theta = np.radians(HINDCAST_DRIFT_DIRECTION_DEG)
    distance_km = HINDCAST_DRIFT_SPEED_KMH * hours
    dx_km = distance_km * np.sin(theta)
    dy_km = distance_km * np.cos(theta)

    return {
        "latitude": float(spill_lat - dy_km * (1 / 111)),
        "longitude": float(spill_lon - dx_km * (1 / (111 * np.cos(np.radians(spill_lat))))),
        "hours_backward": hours,
        "drift_speed_kmh": HINDCAST_DRIFT_SPEED_KMH,
        "drift_direction_deg": HINDCAST_DRIFT_DIRECTION_DEG,
        "label": "Probable Source — Model Estimate",
        "confirmed": False, "confidence": None,
        "method": ("Straight-line back-projection over one satellite revisit, using "
                   "an assumed drift vector"),
        "environmental_data_used": False,
    }


def rank_fleet(ships, source, release_at, radius_km=MAX_DISTANCE_KM):
    """
    Rank the monitored vessels against the estimated source and release window.

    Same weighting as the notebook (0.40 proximity + 0.30 trajectory +
    0.30 behaviour). The behaviour term is the trained Isolation Forest's own
    score for that vessel's track, not a hand-set value.
    """
    from ml.ais_inference import predict_track

    release = parse_time(release_at) if isinstance(release_at, str) else release_at
    win_start = release - timedelta(hours=SEARCH_TIME_BEFORE_HOURS)
    win_end = release + timedelta(hours=SEARCH_TIME_AFTER_HOURS)
    traj_start = release - timedelta(hours=TRAJECTORY_BEFORE_HOURS)
    traj_end = release + timedelta(hours=TRAJECTORY_AFTER_HOURS)

    searched = 0
    assessed = []
    for ship in ships:
        track = ship.get("track") or []
        window = [p for p in track if win_start <= parse_time(p["time"]) <= win_end]
        searched += len(window)
        if not window:
            continue

        measured = [(haversine_km(source["latitude"], source["longitude"], p["lat"], p["lon"]), p)
                    for p in window]
        min_km, closest = min(measured, key=lambda m: m[0])
        if min_km > radius_km:
            continue

        # Trajectory: how much the vessel closed on the source over a wider window.
        traj = [p for p in track if traj_start <= parse_time(p["time"]) <= traj_end] or window
        d_start = haversine_km(source["latitude"], source["longitude"], traj[0]["lat"], traj[0]["lon"])
        d_end = haversine_km(source["latitude"], source["longitude"], traj[-1]["lat"], traj[-1]["lon"])
        d_min = min(haversine_km(source["latitude"], source["longitude"], p["lat"], p["lon"])
                    for p in traj)
        status = "Approaching source" if d_end < d_start else "Moving away / not approaching"
        trajectory_score = max(0.0, min(100.0, (d_start - d_min) / d_start * 100)) if d_start else 0.0

        # Behaviour: the trained model's verdict on this vessel's movement.
        records = [{"MMSI": ship["mmsi"], "BaseDateTime": p["time"],
                    "SOG": p["speed_kt"], "COG": p["course_deg"]} for p in track]
        try:
            anomaly = predict_track(records, mmsi=ship["mmsi"])
            behaviour = anomaly.get("behaviour_score")
            anomalous_points = anomaly.get("anomalous_points")
        except Exception:
            behaviour, anomalous_points = None, None

        proximity = max(0.0, min(100.0, (1 - min_km / radius_km) * 100))
        final = (WEIGHT_PROXIMITY * proximity
                 + WEIGHT_TRAJECTORY * trajectory_score
                 + WEIGHT_BEHAVIOUR * (behaviour or 0.0))

        assessed.append({
            "ship_id": ship["id"], "mmsi": ship["mmsi"], "name": ship["name"],
            "vessel_type": ship["vessel_type"], "in_fleet": True,
            "minimum_distance_km": round(min_km, 2),
            "closest_time": closest["time"],
            "proximity_score": round(proximity, 2),
            "trajectory_status": status,
            "trajectory_score": round(trajectory_score, 2),
            "behaviour_score": None if behaviour is None else round(behaviour, 2),
            "anomalous_points": anomalous_points,
            "final_suspect_score": round(final, 2),
            "latitude": closest["lat"], "longitude": closest["lon"],
        })

    assessed.sort(key=lambda c: c["final_suspect_score"], reverse=True)
    for i, c in enumerate(assessed, start=1):
        c["rank"] = i

    return {
        "records_in_window": searched,
        "records_within_radius": len(assessed),
        "candidate_count": len(assessed),
        "candidates": assessed,
        "search_radius_km": radius_km,
        "source_time": str(release),
        "weights": {"proximity": WEIGHT_PROXIMITY, "trajectory": WEIGHT_TRAJECTORY,
                    "behaviour": WEIGHT_BEHAVIOUR},
        "model": "Isolation Forest — behavioural anomaly detection",
    }


def _affected_area(hours):
    """
    Drift envelope over the revisit window. Not a measured slick.

    `area_km2` is the area of that envelope circle - the sea area the oil could
    have reached. It is a real, computed figure, but it describes a SEARCH ZONE,
    not the size of the slick. The slick's own area is unknowable here: the
    detector classifies, it does not segment, so `measured_area_km2` stays None.
    """
    import math

    radius = HINDCAST_DRIFT_SPEED_KMH * hours
    return {
        "type": "drift_envelope",
        "radius_km": round(radius, 2),
        "area_km2": round(math.pi * radius ** 2, 1),
        "label": "Possible affected area — drift envelope",
        "basis": f"{HINDCAST_DRIFT_SPEED_KMH} km/h assumed drift over {hours} h",
        "is_measured_slick_area": False,
        "note": ("Not a measured slick boundary. The detector is a classifier and "
                 "produces no mask, so no true spill area exists."),
        "measured_area_km2": None,
    }


def run_fleet_scan(snapshot_id=None):
    """Full monitoring scan over one satellite pass."""
    started = time.perf_counter()

    scan = scan_fleet(snapshot_id)
    if scan is None:
        return {"status": "NO_SNAPSHOT", "message": "No satellite snapshots available."}

    from ml.ais_inference import model_info as ais_info
    from ml.cnn_inference import model_info as cnn_info

    provenance = {
        "oil_detection": {"source": "ml_model", "model_version": cnn_info().get("checkpoint")},
        "anomaly_detection": {"source": "ml_model", "model_version": ais_info().get("model_file")},
        "hindcast": COMPUTED_PROVENANCE, "ranking": COMPUTED_PROVENANCE,
        "forecast": COMPUTED_PROVENANCE, "live_inference": True,
        "fleet_data": "synthetic" if scan["synthetic_fleet"] else "real",
    }

    base = {
        "snapshot_id": scan["snapshot_id"], "observed_at": scan["observed_at"],
        "available_snapshots": scan["available_snapshots"],
        "pass_interval_hours": scan["pass_interval_hours"],
        "region": scan["region"], "synthetic_fleet": scan["synthetic_fleet"],
        "fleet": scan["ships"], "scanned": scan["scanned"],
        "detections": scan["detections"], "provenance": provenance,
        "environment": {"wind": None, "current": None, "wave": None},
    }

    if not scan["oil_detected"]:
        return {**base, "status": "CLEAR",
                "message": (f"No oil signature in pass {scan['snapshot_id']}. "
                            f"{scan['scanned']} vessels checked."),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}

    hours = scan["pass_interval_hours"]
    release_at = (parse_time(scan["observed_at"]) - timedelta(hours=hours)
                  if scan["observed_at"] else None)

    # Every flagged vessel is its own detection and gets its own characterisation:
    # a spill found near a second ship is a second finding, not a footnote to the
    # strongest one.
    spills = []
    for det in scan["detections"]:
        det_spill = {
            "ship_id": det["id"], "ship_name": det["name"], "mmsi": det["mmsi"],
            "latitude": det["latitude"], "longitude": det["longitude"],
            "confidence": det["confidence"], "prediction": det["prediction"],
            "image_url": det["image_url"], "detected_in_pass": scan["snapshot_id"],
            "observed_at": scan["observed_at"],
            "measured_area_km2": None, "oil_thickness": None, "oil_volume": None,
            "segmentation_mask": None,
            "note": ("Position is the vessel's last known AIS fix; the classifier "
                     "does not geolocate."),
        }
        det_source = hindcast_over(det_spill["latitude"], det_spill["longitude"], hours)
        det_ais = rank_fleet(scan["ships"], det_source, release_at) if release_at else None
        spills.append({
            "spill": det_spill,
            "source": det_source,
            "age": {
                "estimated_hours": hours,
                "label": "Maximum age since release",
                "basis": (f"The previous pass was clear and this one is not, so the oil "
                          f"is at most one {hours} h satellite revisit old."),
                "release_at": release_at.strftime("%Y-%m-%dT%H:%M:%SZ") if release_at else None,
            },
            "affected_area": _affected_area(hours),
            "forecast": forecast(det_spill["latitude"], det_spill["longitude"]),
            "ais": det_ais,
            "candidates": det_ais["candidates"] if det_ais else [],
        })

    # The strongest detection also fills the top-level fields.
    primary = spills[0]
    top = scan["detections"][0]
    spill, source, ais = primary["spill"], primary["source"], primary["ais"]
    fc = primary["forecast"]
    candidates = primary["candidates"]

    return {
        **base,
        "status": "SPILL_DETECTED",
        "message": (f"Oil signature detected near {top['name']} in pass "
                    f"{scan['snapshot_id']} at {top['confidence'] * 100:.1f}% confidence."),
        "spill": spill,
        "spills": spills,
        "age": primary["age"],
        "affected_area": primary["affected_area"],
        "source": source,
        "ais": ais,
        "candidates": candidates,
        "forecast": fc,
        "top_suspect": candidates[0] if candidates else None,
        "interpretation": {
            "vessel_causation_proven": False,
            "forecast_type": "kinematic_projection",
            "requires_environmental_drift_data": True,
            "ranking_meaning": ("This ranking indicates analytical association with the "
                                "estimated source window. It does not establish legal "
                                "responsibility."),
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
