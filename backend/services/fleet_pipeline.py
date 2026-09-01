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

from core.config import (ASSUMED_CURRENT_DIRECTION_DEG, ASSUMED_CURRENT_SPEED_MS,
                         ASSUMED_WIND_DIRECTION_DEG, ASSUMED_WIND_SPEED_MS,
                         COMPUTED_PROVENANCE, SIMULATION_DIR)

from .geo import haversine_km, parse_time
from .investigation import (HINDCAST_DRIFT_DIRECTION_DEG, HINDCAST_DRIFT_SPEED_KMH,
                            MAX_DISTANCE_KM, SEARCH_TIME_AFTER_HOURS,
                            SEARCH_TIME_BEFORE_HOURS, TRAJECTORY_AFTER_HOURS,
                            TRAJECTORY_BEFORE_HOURS, WEIGHT_BEHAVIOUR,
                            WEIGHT_PROXIMITY, WEIGHT_TRAJECTORY, forecast)
from .damage import (advisory, drift_vector, impact_envelope, priority_score,
                     rank_spills)
from .risk import assess_fleet, projected_route, spill_polygons
from .reroute import suggest_detour
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


def _track_until(ship, when):
    """
    The vessel's fixes up to and including `when`.

    A pass only knows the AIS history that existed when it was taken. Returning
    the whole session meant the "where it has been" line ran past the vessel
    into fixes it had not reached yet, so on an early pass the historic track
    and the forward projection pointed the same way.
    """
    track = ship.get("track") or []
    if not when:
        return track
    target = parse_time(when)
    return [p for p in track if parse_time(p["time"]) <= target] or track[:1]


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
            "length_m": ship.get("length_m"), "width_m": ship.get("width_m"),
            "latitude": fix["lat"] if fix else ship["latitude"],
            "longitude": fix["lon"] if fix else ship["longitude"],
            "speed_kt": fix["speed_kt"] if fix else ship["speed_kt"],
            "course_deg": fix["course_deg"] if fix else ship["course_deg"],
            "position_time": fix["time"] if fix else None,
            # Only fixes up to THIS pass. At pass time nobody has the vessel's
            # future AIS, and drawing the whole session made the "past track"
            # run ahead of the vessel — the same direction as its projection.
            "track": _track_until(ship, observed_at),
        }
        # Where this vessel is headed next, for every vessel — the map pairs it
        # with the historic track so a click always shows past AND future.
        record["projected_track"] = projected_route(record)

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
    The sea area the oil could have reached over the revisit window.

    Sized by services/damage.py from the assumed current + windage rather than a
    single hardcoded drift constant, so stated conditions drive the envelope.
    Still a SEARCH/RESPONSE ZONE, never a measured slick: the detector
    classifies and does not segment, so `measured_area_km2` stays None.
    """
    return impact_envelope(hours)


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
        # Stated assumptions, not observations — no met-ocean feed is wired up.
        # Wave is still genuinely absent: nothing in the pipeline uses it.
        "environment": {
            "measured": False,
            "wind": {"speed_ms": ASSUMED_WIND_SPEED_MS,
                     "direction_deg": ASSUMED_WIND_DIRECTION_DEG, "assumed": True},
            "current": {"speed_ms": ASSUMED_CURRENT_SPEED_MS,
                        "direction_deg": ASSUMED_CURRENT_DIRECTION_DEG, "assumed": True},
            "wave": None,
            "drift": drift_vector(),
        },
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
        spill_entry = {
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
        }

        # FORWARD RISK — separate from the attribution above. Attribution looks
        # backward at historic AIS around the estimated source; this looks
        # forward from each vessel's CURRENT position/heading against the
        # spill's current + forecast polygons. Never merge these two.
        risk = assess_fleet(scan["ships"], spill_entry)
        polygons = spill_polygons(spill_entry, max_hours_ahead=risk["forecast_horizon_hours"])
        ships_by_id = {s["id"]: s for s in scan["ships"]}
        for entry in risk["at_risk"]:
            ship = ships_by_id.get(entry["ship_id"])
            detour = suggest_detour(ship, polygons, risk["forecast_horizon_hours"]) if ship else None
            entry["detour"] = detour
        spill_entry["risk"] = risk

        # RESPONSE — how bad is this one relative to the others, and who goes.
        # Vessel size comes from the source vessel's own recorded AIS dimensions.
        spill_entry["damage"] = priority_score(
            spill_entry["affected_area"], det["confidence"], det.get("length_m"))
        spill_entry["response"] = advisory(spill_entry["damage"]["priority_score"])

        spills.append(spill_entry)

    # Worst-first ordering across all live spills, so responders get a queue
    # rather than a pile. Separate from the suspect ranking, which is about who
    # caused a spill, not which spill to work first.
    priorities = rank_spills(spills)
    priority_by_ship = {p["ship_id"]: p for p in priorities}
    for entry in spills:
        entry["response_priority"] = priority_by_ship.get(
            entry["spill"]["ship_id"], {}).get("response_priority")
        entry["response"]["response_priority"] = entry["response_priority"]

    # The strongest detection also fills the top-level fields.
    primary = spills[0]
    top = scan["detections"][0]
    spill, source, ais = primary["spill"], primary["source"], primary["ais"]
    fc = primary["forecast"]
    candidates = primary["candidates"]
    risk = primary["risk"]

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
        "risk": risk,
        "damage": primary["damage"],
        "response": primary["response"],
        "response_priorities": priorities,
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
