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
from functools import lru_cache
from datetime import timedelta

# The assumed wind/current constants are no longer read here: the scan's
# environment block comes from services/environment.py, which reports whether
# the values are a dataset's or the stated assumptions.
from core.config import (COMPUTED_PROVENANCE, RISK_FORECAST_HOURS, SIMULATION_DIR,
                         SIMULATION_SEED)

from .drift import (closure_residual_km, forecast_environmental,
                    hindcast_environmental)
from .geo import haversine_km, parse_time
from .investigation import (FORECAST_DRIFT_DIRECTION_DEG, FORECAST_DRIFT_SPEED_KMH,
                            FORECAST_HOURS,
                            HINDCAST_DRIFT_DIRECTION_DEG, HINDCAST_DRIFT_SPEED_KMH,
                            MAX_DISTANCE_KM, SEARCH_TIME_AFTER_HOURS,
                            SEARCH_TIME_BEFORE_HOURS, TRAJECTORY_AFTER_HOURS,
                            TRAJECTORY_BEFORE_HOURS, WEIGHT_BEHAVIOUR,
                            WEIGHT_PROXIMITY, WEIGHT_TRAJECTORY, forecast,
                            fleet_search_radius_km, SEARCH_RADIUS_ENVELOPE_MULTIPLE)
from .damage import (advisory, drift_vector, impact_envelope, priority_score,
                     rank_spills)
from .risk import assess_fleet, projected_route, spill_polygons
from .reroute import suggest_detour
from .snapshots import get_available_snapshots, get_latest_snapshot

FLEET_FILE = SIMULATION_DIR / "fleet.json"
DEFAULT_PASS_INTERVAL_HOURS = 8


_CORPUS_VESSELS = None


def corpus_vessel_count():
    """
    Distinct MMSIs in the AIS corpus. Read once and cached — this is a fact
    about the file, not a per-scan computation, and it is only used to report
    the population the fleet was drawn from.
    """
    global _CORPUS_VESSELS
    if _CORPUS_VESSELS is None:
        try:
            import pandas as pd
            from core.config import AIS_REFERENCE_FILE
            _CORPUS_VESSELS = int(pd.read_csv(AIS_REFERENCE_FILE, usecols=["MMSI"])["MMSI"].nunique())
        except Exception:
            _CORPUS_VESSELS = None
    return _CORPUS_VESSELS


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


@lru_cache(maxsize=1)
def aoi_centre():
    """
    The middle of the monitored area, derived from the fleet's own AIS bbox
    rather than typed in — the AOI moves if the fleet is rebuilt, and a
    hardcoded centre would silently stop being the centre.
    """
    fleet = load_fleet()
    lats = [p["lat"] for s in fleet["ships"] for p in s["track"]]
    lons = [p["lon"] for s in fleet["ships"] for p in s["track"]]
    return (round((min(lats) + max(lats)) / 2, 5),
            round((min(lons) + max(lons)) / 2, 5))


def _environment_block(region, observed_at):
    """
    The environmental conditions reported alongside a scan.

    Sampled at the AOI centre, which is what a single figure for the whole scan
    can honestly mean — the drift is applied uniformly across an area 21 x 38 km
    across, so a per-vessel sample would imply a spatial resolution the rest of
    the pipeline does not have.
    """
    from .environment import get_conditions

    lat, lon = aoi_centre()
    env = get_conditions(lat, lon, observed_at)
    return {
        "measured": env["measured"],
        "environment_mode": env["environment_mode"],
        "environment_reason": env["environment_reason"],
        "current": {**env["current"], "assumed": not env["current"]["measured"]},
        "wind": {**env["wind"], "assumed": not env["wind"]["measured"]},
        "source": env["source"],
        "resolution": env["resolution"],
        "coverage": env["coverage"],
        "sampled_at": env["sampled_at"],
        "sampled_at_position": {"latitude": lat, "longitude": lon},
        "region": region,
    }


def hindcast_over(spill_lat, spill_lon, hours, speed_kmh=None, bearing_deg=None):
    """
    Back-project the slick along the assumed drift vector for `hours`.

    Same arithmetic as the notebook's hindcast; the window comes from the revisit
    cadence instead of being fixed at 24 h.

    `speed_kmh` / `bearing_deg` let a caller substitute a different point in the
    drift-assumption band instead of the notebook's own vector. Nothing in this
    pipeline does that except source_heatmap() below, which re-runs this exact
    arithmetic across the same band the counterfactual sensitivity sweep already
    uses, so the two never drift apart from re-implementing it twice.
    """
    import numpy as np

    speed_kmh = HINDCAST_DRIFT_SPEED_KMH if speed_kmh is None else speed_kmh
    bearing_deg = HINDCAST_DRIFT_DIRECTION_DEG if bearing_deg is None else bearing_deg

    theta = np.radians(bearing_deg)
    distance_km = speed_kmh * hours
    dx_km = distance_km * np.sin(theta)
    dy_km = distance_km * np.cos(theta)

    return {
        "latitude": float(spill_lat - dy_km * (1 / 111)),
        "longitude": float(spill_lon - dx_km * (1 / (111 * np.cos(np.radians(spill_lat))))),
        "hours_backward": hours,
        "drift_speed_kmh": speed_kmh,
        "drift_direction_deg": bearing_deg,
        "label": "Probable Source — Model Estimate",
        "confirmed": False, "confidence": None,
        "method": ("Straight-line back-projection over one satellite revisit, using "
                   "an assumed drift vector"),
        "environmental_data_used": False,
    }


def source_heatmap(spill_lat, spill_lon, hours):
    """
    Spread of the hindcast point across the drift-assumption band.

    The hindcast above commits to ONE drift vector (1.5 km/h toward 135 deg).
    That vector is not measured — no wind or current data is wired up anywhere
    in this system — so the honest companion to a single point on the map is
    not a probability surface around it (no error distribution over the drift
    is known, so nothing can honestly be weighted as more or less likely) but
    the SAME point re-evaluated across the SAME speed/bearing band
    services/counterfactual.py already uses for its sensitivity sweep
    (SWEEP_SPEED_FRACTION, SWEEP_BEARING_DEG, SWEEP_STEPS — a 0.75-2.25 km/h,
    90-180 deg, 7x7 grid). Reusing that band rather than inventing a new one
    means this layer and the counterfactual's robustness check are answering
    with the same uncertainty, not two different ones that happen to both be
    drawn in orange.

    Returns 49 points, each hindcast_over() at one grid cell. Deliberately
    unweighted: every cell is reported as equally plausible because that is
    what "no error distribution is known" actually means.
    """
    from .counterfactual import SWEEP_BEARING_DEG, SWEEP_SPEED_FRACTION, SWEEP_STEPS, _spread

    speed_offsets = _spread(HINDCAST_DRIFT_SPEED_KMH * SWEEP_SPEED_FRACTION, SWEEP_STEPS)
    bearing_offsets = _spread(SWEEP_BEARING_DEG, SWEEP_STEPS)
    speeds = [HINDCAST_DRIFT_SPEED_KMH + d for d in speed_offsets]
    bearings = [HINDCAST_DRIFT_DIRECTION_DEG + d for d in bearing_offsets]

    points = [
        {"latitude": pt["latitude"], "longitude": pt["longitude"]}
        for speed in speeds
        for bearing in bearings
        for pt in [hindcast_over(spill_lat, spill_lon, hours,
                                 speed_kmh=speed, bearing_deg=bearing)]
    ]

    return {
        "points": points,
        "grid": f"{SWEEP_STEPS}x{SWEEP_STEPS}",
        "speed_range_kmh": [round(min(speeds), 2), round(max(speeds), 2)],
        "bearing_range_deg": [round(min(bearings), 1), round(max(bearings), 1)],
        "hours": hours,
        "label": "Source Estimate Spread",
        "note": ("Not a probability surface — no drift error distribution is known. "
                 "This is the hindcast point re-evaluated across the same "
                 "speed/bearing band the counterfactual sensitivity sweep uses "
                 "elsewhere in this system, so it shows how far the estimate moves "
                 "under that uncertainty, not a likelihood ranking of locations."),
        "evidence_class": "SENSITIVITY, NOT A FINDING",
    }


def forecast_heatmap(spill_lat, spill_lon, horizons=None):
    """
    Forward-looking counterpart to source_heatmap().

    Same drift-assumption band (SWEEP_SPEED_FRACTION, SWEEP_BEARING_DEG,
    SWEEP_STEPS) — centred on the forecast's own vector (FORECAST_DRIFT_SPEED_KMH,
    FORECAST_DRIFT_DIRECTION_DEG, which forecast() already uses) instead of the
    hindcast's, and projected forward instead of backward. Same caveat as
    source_heatmap: not a probability, an unweighted re-run of the forecast
    arithmetic across the plausible band — reported separately per horizon
    because the spread genuinely widens with time and collapsing horizons
    together would hide that.
    """
    import numpy as np
    from .counterfactual import SWEEP_BEARING_DEG, SWEEP_SPEED_FRACTION, SWEEP_STEPS, _spread

    horizons = horizons or FORECAST_HOURS
    speed_offsets = _spread(FORECAST_DRIFT_SPEED_KMH * SWEEP_SPEED_FRACTION, SWEEP_STEPS)
    bearing_offsets = _spread(SWEEP_BEARING_DEG, SWEEP_STEPS)
    speeds = [FORECAST_DRIFT_SPEED_KMH + d for d in speed_offsets]
    bearings = [FORECAST_DRIFT_DIRECTION_DEG + d for d in bearing_offsets]

    def _project_forward(hours, speed_kmh, bearing_deg):
        theta = np.radians(bearing_deg)
        distance_km = speed_kmh * hours
        dx_km = distance_km * np.sin(theta)
        dy_km = distance_km * np.cos(theta)
        return {
            "latitude": float(spill_lat + dy_km * (1 / 111)),
            "longitude": float(spill_lon + dx_km * (1 / (111 * np.cos(np.radians(spill_lat))))),
        }

    by_horizon = [
        {
            "hours_ahead": h,
            "points": [_project_forward(h, speed, bearing)
                      for speed in speeds for bearing in bearings],
        }
        for h in horizons
    ]

    return {
        "by_horizon": by_horizon,
        "grid": f"{SWEEP_STEPS}x{SWEEP_STEPS}",
        "speed_range_kmh": [round(min(speeds), 2), round(max(speeds), 2)],
        "bearing_range_deg": [round(min(bearings), 1), round(max(bearings), 1)],
        "label": "Forecast Spread",
        "note": ("Not a probability surface. Same drift-assumption band as the "
                 "source estimate spread, centred on the forecast vector and "
                 "projected forward instead of backward. Spread widens with "
                 "horizon because more hours amplifies the same speed/bearing "
                 "uncertainty, not because later horizons are less likely."),
        "evidence_class": "SENSITIVITY, NOT A FINDING",
    }


def score_fleet_behaviour(ships):
    """
    The Isolation Forest's verdict on each vessel's track, once per scan.

    Two things this fixes.

    It was called once per vessel PER DETECTION, inside the loop over
    detections, but the result does not depend on which spill is being ranked —
    a vessel's track is the same track either way. At two detections that was
    double the inference for identical answers.

    More importantly, the failure path was a bare `except Exception` that set
    the score to None, which the caller then folded in as `behaviour or 0.0`. A
    model that crashed and a vessel that genuinely behaved unremarkably produced
    the same number, and the crash silently cost the vessel up to 30 of 100
    points. An unavailable signal is now reported as unavailable, with a reason,
    and the weighting is adjusted rather than the score being quietly depressed.
    """
    import logging
    log = logging.getLogger("oiltrace.behaviour")

    from ml.ais_inference import predict_track

    out = {}
    for ship in ships:
        mmsi = ship["mmsi"]
        track = ship.get("track") or []
        # build_features() differences each fix against its predecessor and drops
        # the first, so two fixes are the minimum that can yield one scored row.
        if len(track) < 2:
            out[mmsi] = {
                "available": False, "status": "track_too_short", "score": None,
                "anomalous_points": None,
                "reason": (f"{len(track)} AIS fix{'' if len(track) == 1 else 'es'} in this "
                           "pass; at least 2 are needed to derive movement features."),
            }
            continue

        records = [{"MMSI": mmsi, "BaseDateTime": p["time"],
                    "SOG": p["speed_kt"], "COG": p["course_deg"]} for p in track]
        try:
            anomaly = predict_track(records, mmsi=mmsi)
        except ValueError as exc:
            out[mmsi] = {
                "available": False, "status": "track_too_short", "score": None,
                "anomalous_points": None,
                "reason": f"Track rejected by the feature builder: {exc}",
            }
            continue
        except (ImportError, FileNotFoundError) as exc:
            log.warning("AIS model unavailable for MMSI %s: %s", mmsi, exc)
            out[mmsi] = {
                "available": False, "status": "model_unavailable", "score": None,
                "anomalous_points": None,
                "reason": "The Isolation Forest or its scaler could not be loaded.",
            }
            continue
        except Exception as exc:
            # Genuinely unexpected. Logged with the vessel so it can be chased,
            # never swallowed into a zero.
            log.exception("AIS inference failed for MMSI %s", mmsi)
            out[mmsi] = {
                "available": False, "status": "inference_error", "score": None,
                "anomalous_points": None,
                "reason": f"Inference error: {type(exc).__name__}.",
            }
            continue

        score = anomaly.get("behaviour_score")
        if score is None:
            out[mmsi] = {
                "available": False, "status": "model_declined", "score": None,
                "anomalous_points": anomaly.get("anomalous_points"),
                "reason": "The model ran but returned no behaviour score for this track.",
            }
            continue

        out[mmsi] = {
            "available": True, "status": "ok", "score": score,
            "anomalous_points": anomaly.get("anomalous_points"), "reason": None,
        }
    return out


def rank_fleet(ships, source, release_at, radius_km=MAX_DISTANCE_KM,
               behaviour_by_mmsi=None):
    """
    Rank the monitored vessels against the estimated source and release window.

    Same weighting as the notebook (0.40 proximity + 0.30 trajectory +
    0.30 behaviour). The behaviour term is the trained Isolation Forest's own
    score for that vessel's track, not a hand-set value.
    """
    behaviour_by_mmsi = behaviour_by_mmsi or {}

    release = parse_time(release_at) if isinstance(release_at, str) else release_at
    win_start = release - timedelta(hours=SEARCH_TIME_BEFORE_HOURS)
    win_end = release + timedelta(hours=SEARCH_TIME_AFTER_HOURS)
    traj_start = release - timedelta(hours=TRAJECTORY_BEFORE_HOURS)
    traj_end = release + timedelta(hours=TRAJECTORY_AFTER_HOURS)

    searched = 0
    # Vessel-level counts, so the funnel can be reported in vessels rather than
    # AIS records — "6 of 12 vessels" is the filter's actual work; "190 fixes"
    # is how much data it read.
    monitored = len(ships)
    with_fixes = 0
    assessed = []
    for ship in ships:
        track = ship.get("track") or []
        window = [p for p in track if win_start <= parse_time(p["time"]) <= win_end]
        searched += len(window)
        if not window:
            continue
        with_fixes += 1

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

        # Behaviour: the trained model's verdict, scored once per scan.
        verdict = behaviour_by_mmsi.get(ship["mmsi"]) or {
            "available": False, "status": "not_scored", "score": None,
            "anomalous_points": None, "reason": "Not scored for this pass.",
        }
        behaviour = verdict["score"]
        anomalous_points = verdict["anomalous_points"]

        proximity = max(0.0, min(100.0, (1 - min_km / radius_km) * 100))

        # SCORING RULE WHEN BEHAVIOUR IS UNAVAILABLE — re-weight, do not zero.
        #
        # The old code folded a missing behaviour score in as `behaviour or 0.0`,
        # which asserts something false: that the vessel behaved unremarkably.
        # A model that could not answer is not evidence of innocence, and at a
        # weight of 0.30 that silent zero cost a vessel up to 30 of 100 points
        # for a reason having nothing to do with the vessel.
        #
        # Instead the available terms are renormalised to sum to 1, so the score
        # means "evidence consistency across the evidence that exists" and stays
        # on the same 0-100 scale. The trade-off is that a vessel scored on two
        # terms is not strictly comparable with one scored on three — so the
        # weights actually applied travel with the candidate, and the interface
        # shows that the vessel was scored on partial evidence rather than
        # burying it.
        if behaviour is None:
            total = WEIGHT_PROXIMITY + WEIGHT_TRAJECTORY
            applied = {"proximity": WEIGHT_PROXIMITY / total,
                       "trajectory": WEIGHT_TRAJECTORY / total,
                       "behaviour": 0.0}
            final = applied["proximity"] * proximity + applied["trajectory"] * trajectory_score
        else:
            applied = {"proximity": WEIGHT_PROXIMITY, "trajectory": WEIGHT_TRAJECTORY,
                       "behaviour": WEIGHT_BEHAVIOUR}
            final = (WEIGHT_PROXIMITY * proximity
                     + WEIGHT_TRAJECTORY * trajectory_score
                     + WEIGHT_BEHAVIOUR * behaviour)

        assessed.append({
            "ship_id": ship["id"], "mmsi": ship["mmsi"], "name": ship["name"],
            "vessel_type": ship["vessel_type"], "in_fleet": True,
            "minimum_distance_km": round(min_km, 2),
            "closest_time": closest["time"],
            "proximity_score": round(proximity, 2),
            "trajectory_status": status,
            "trajectory_score": round(trajectory_score, 2),
            "behaviour_score": None if behaviour is None else round(behaviour, 2),
            "behaviour_available": verdict["available"],
            "behaviour_status": verdict["status"],
            "behaviour_reason": verdict["reason"],
            "anomalous_points": anomalous_points,
            # The weights actually used for THIS candidate. They differ from the
            # headline weights when a term was unavailable, and the interface
            # shows the arithmetic, so it has to show the real ones.
            "weights_applied": {k: round(v, 4) for k, v in applied.items()},
            "scored_on_partial_evidence": not verdict["available"],
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
        # What the irrelevant-traffic filter actually did, in vessels.
        "funnel": {
            "monitored": monitored,
            "with_fixes_in_window": with_fixes,
            "within_radius": len(assessed),
            "rejected_no_fixes": monitored - with_fixes,
            "rejected_too_far": with_fixes - len(assessed),
        },
        "search_radius_km": radius_km,
        "search_radius_basis": (
            f"{SEARCH_RADIUS_ENVELOPE_MULTIPLE} x the {round(radius_km / SEARCH_RADIUS_ENVELOPE_MULTIPLE, 2)} km "
            "drift envelope for this spill's age. A vessel that never came this close to the "
            "estimated source cannot plausibly be its origin."),
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


def _drift_divergence(spill, observed_at, hours, ships=None, release_at=None,
                      radius_km=None, behaviour_by_mmsi=None):
    """
    How far apart the legacy and environment-aware estimates land, measured.

    Reported rather than resolved. The two differ even with NO environmental
    data, because the legacy hindcast's 1.5 km/h toward 135 deg is a notebook
    constant that was never derived from the stated wind and current, while the
    environment path uses the vector those constants actually imply
    (1.394 km/h toward 181.2 deg). Same for the forecast's 1.0 km/h toward
    180 deg. This is the "three drift vectors coexist" problem made numeric; it
    is not evidence that either estimate is better.
    """
    lat, lon = spill["latitude"], spill["longitude"]
    legacy_source = hindcast_over(lat, lon, hours)
    env_source = hindcast_environmental(lat, lon, observed_at, hours)
    legacy_fc = forecast(lat, lon)
    env_fc = forecast_environmental(lat, lon, observed_at, FORECAST_HOURS)

    by_horizon = {}
    for a, b in zip(legacy_fc["points"], env_fc["points"]):
        by_horizon[a["hours_ahead"]] = round(
            haversine_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"]), 2)

    return {
        "source_separation_km": round(haversine_km(
            legacy_source["latitude"], legacy_source["longitude"],
            env_source["latitude"], env_source["longitude"]), 2),
        "forecast_separation_km": by_horizon,
        "legacy_vectors": {
            "hindcast": {"speed_kmh": HINDCAST_DRIFT_SPEED_KMH,
                         "direction_deg": HINDCAST_DRIFT_DIRECTION_DEG},
            "forecast": {"speed_kmh": FORECAST_DRIFT_SPEED_KMH,
                         "direction_deg": FORECAST_DRIFT_DIRECTION_DEG},
        },
        "environment_vector": {k: drift_vector()[k]
                               for k in ("speed_kmh", "direction_deg")},
        "environment_mode": env_source["environment_mode"],
        "closure": closure_residual_km(lat, lon, observed_at, hours),
        "ranking_change": _ranking_change(ships, legacy_source, env_source, release_at,
                                          radius_km, behaviour_by_mmsi),
        "cause": ("These differ with no environmental data loaded. The legacy "
                  "hindcast and forecast use notebook constants that were never "
                  "derived from the stated wind and current; the environment path "
                  "uses the vector those constants imply. Neither is validated, "
                  "and this separation is a disagreement between assumptions, not "
                  "a measurement of error."),
        "in_use": ("legacy — the environment-aware estimates are computed and "
                   "reported, and drive nothing"),
    }


def _ranking_change(ships, legacy_source, env_source, release_at, radius_km,
                    behaviour_by_mmsi):
    """
    Would using the environment-aware source change WHO the system ranks first?

    The most useful question this comparison can answer, and the least
    comfortable: on the t3 case it does. The same fleet, the same search radius,
    the same behaviour scores — only the estimated source moves — and the top
    candidate changes.

    This is a PARALLEL computation. The shipped `candidates` list is produced
    from the legacy source and is not touched. Both rankings are reported and
    neither is presented as the right one, because nothing here is validated
    against a known attribution.

    rank_fleet() is reused as-is rather than reimplemented, and behaviour is
    passed in already scored, so this adds no model inference — the second call
    is arithmetic over tracks the scan has already loaded.
    """
    if not ships or not release_at or radius_km is None:
        return {"available": False,
                "reason": "The ranking comparison needs a fleet, a release window "
                          "and a search radius; at least one was unavailable."}

    legacy = rank_fleet(ships, legacy_source, release_at, radius_km=radius_km,
                        behaviour_by_mmsi=behaviour_by_mmsi)["candidates"]
    aware = rank_fleet(ships, env_source, release_at, radius_km=radius_km,
                       behaviour_by_mmsi=behaviour_by_mmsi)["candidates"]
    by_mmsi = {c["mmsi"]: c for c in aware}

    rows = []
    for c in legacy:
        other = by_mmsi.get(c["mmsi"])
        rows.append({
            "mmsi": c["mmsi"],
            "name": c["name"],
            "legacy_rank": c["rank"],
            "legacy_score": c["final_suspect_score"],
            # A vessel the environment-aware source puts outside the radius is
            # dropped, not scored zero — the same distinction the behaviour term
            # makes between "unavailable" and "normal".
            "environmental_rank": other["rank"] if other else None,
            "environmental_score": other["final_suspect_score"] if other else None,
            "rank_delta": (c["rank"] - other["rank"]) if other else None,
            "dropped": other is None,
        })

    admitted_only_by_environmental = [
        {"mmsi": c["mmsi"], "name": c["name"], "environmental_rank": c["rank"]}
        for c in aware if c["mmsi"] not in {x["mmsi"] for x in legacy}
    ]

    legacy_top = legacy[0]["name"] if legacy else None
    aware_top = aware[0]["name"] if aware else None

    return {
        "available": True,
        "top_changes": legacy_top != aware_top,
        "legacy_top": legacy_top,
        "environmental_top": aware_top,
        "legacy_count": len(legacy),
        "environmental_count": len(aware),
        "rows": rows,
        "admitted_only_by_environmental": admitted_only_by_environmental,
        "in_use": "legacy",
        "meaning": ("Which vessels the system would rank first under each drift "
                    "assumption. The shipped ranking is the legacy one. A change "
                    "here is a sensitivity of the attribution to an assumption "
                    "nobody measured — the same class of thing the counterfactual "
                    "robustness sweep reports per candidate — and not a sign that "
                    "either ranking is wrong."),
    }


def _evidence(candidates, ships, spill, release_at, age_hours, environment,
              ranking_change):
    """
    Grade every candidate's evidence, and decide whether any is supported.

    Runs the counterfactual for each candidate here rather than waiting for a
    click: the outcome cannot be reached without it, and all 16 counterfactuals
    across both detections were measured at 153 ms, 3% of a scan. The on-demand
    endpoint stays for the interactive panel.

    Reads the ranking; changes nothing about it.
    """
    from .counterfactual import test_candidate
    from .evidence import assess_detection, grade_candidate
    from .narrative import build as build_narrative

    by_mmsi = {s["mmsi"]: s for s in ships}
    graded, consistent = [], set()
    for c in candidates:
        ship = by_mmsi.get(c["mmsi"])
        result = test_candidate(ship, release_at, spill["latitude"], spill["longitude"],
                                age_hours) if ship else None
        if result and result.get("available") and result.get("within_envelope"):
            consistent.add(c["mmsi"])
        graded.append(grade_candidate(
            c, (ship or {}).get("track") or [], release_at, result,
            environment.get("environment_mode"), environment.get("environment_reason")))

    # The outcome needs every candidate graded, and the narrative's opening line
    # needs the outcome — so the narrative is built on a second pass rather than
    # having grade_candidate guess at a verdict that does not exist yet.
    assessment = assess_detection(candidates, graded, consistent, ranking_change)
    for c, g in zip(candidates, graded):
        g["narrative"] = build_narrative(c, g["streams"], assessment["outcome"],
                                         c["mmsi"] in consistent)

    return {"candidates": graded, "assessment": assessment}


def _combined_risk(spills, ships):
    """
    One fleet-wide at-risk list, merged across every live spill.

    Each spill assesses the fleet against its own polygons, so a vessel can be
    flagged twice. Presenting those as separate per-spill lists meant the
    dashboard showed a different answer depending on which spill happened to be
    selected — and none at all for a spill that threatens nobody. Here the
    entries are pooled and deduplicated, keeping the SOONEST threat per vessel,
    with the spill that causes it named on the row.
    """
    worst = {}
    for entry in spills:
        spill = entry.get("spill") or {}
        for at_risk in (entry.get("risk") or {}).get("at_risk", []):
            row = {**at_risk,
                   "spill_ship_id": spill.get("ship_id"),
                   "spill_ship_name": spill.get("ship_name"),
                   "response_priority": entry.get("response_priority")}
            current = worst.get(row["ship_id"])
            if current is None or row["estimated_entry_minutes"] < current["estimated_entry_minutes"]:
                worst[row["ship_id"]] = row

    at_risk = sorted(worst.values(), key=lambda r: r["estimated_entry_minutes"])
    source_ids = {s["id"] for s in ships if s.get("oil_detected")}

    return {
        "label": "FORWARD RISK — SIMULATED PROJECTION",
        "forecast_horizon_hours": RISK_FORECAST_HOURS,
        "vessels_checked": len(ships) - len(source_ids),
        "at_risk_count": len(at_risk),
        "safe_count": len(ships) - len(source_ids) - len(at_risk),
        "at_risk": at_risk,
        "source_ship_ids": sorted(source_ids),
        "method": ("Every live spill assessed against the whole fleet, pooled and "
                   "deduplicated to the soonest threat per vessel. Vessels showing "
                   "oil themselves are excluded — they are the casualty, not "
                   "traffic to divert."),
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
        # Requirement W: what a reader needs to reproduce or dispute this run.
        # The seed is here because which vessels carry an oily tile is a SEEDED
        # SIMULATION, and a report that omitted it would let a reader take the
        # detection scenario for an observation.
        "simulation_seed": SIMULATION_SEED,
        "simulation_note": ("Which monitored vessels carry an oil-positive SAR tile is "
                            "assigned by this seed before any model runs. It is "
                            "detection-scenario ground truth, never attribution ground "
                            "truth."),
        "ais_dataset": {
            "source": "real AIS", "vessels_in_corpus": corpus_vessel_count(),
            "monitored": len(scan["ships"]),
            "co_presence": load_fleet().get("co_presence"),
        },
        "sar_input": {
            "source": "public Sentinel-1 oil-spill dataset, recycled across vessels",
            "note": "Vessels share imagery from a fixed pool; a tile is not that "
                    "vessel's own satellite capture.",
        },
        "software_mode": "live inference",
    }

    fleet_meta = load_fleet()

    # How stale the AIS is for this pass. A pass dropped in beyond the corpus's
    # coverage — which any uploaded pass will be — carries vessel positions from
    # the last fix before it, and every forward calculation (risk, entry time,
    # detour) is built on those. That is not wrong, but it is not visible from
    # the numbers either, so it is reported rather than left to be noticed.
    ais_lag_hours = None
    if scan["observed_at"] and scan["ships"]:
        times = [parse_time(sh["position_time"]) for sh in scan["ships"]
                 if sh.get("position_time")]
        if times:
            ais_lag_hours = round(
                (parse_time(scan["observed_at"]) - max(times)).total_seconds() / 3600, 2)

    base = {
        "snapshot_id": scan["snapshot_id"], "observed_at": scan["observed_at"],
        # The population the monitored fleet was drawn from. Counted from the
        # corpus itself so it cannot drift from reality; the fleet is the subset
        # that carries a SAR tile and is therefore scannable.
        "traffic": {
            "corpus_vessels": corpus_vessel_count(),
            "monitored": len(scan["ships"]),
            "co_presence": fleet_meta.get("co_presence"),
            "co_presence_reason": fleet_meta.get("co_presence_reason"),
            "note": ("The AIS corpus records this many distinct vessels across its whole "
                     "span. The monitored fleet is the subset selected for the demo; only "
                     "monitored vessels carry a SAR tile and can be classified."),
        },
        "ais_currency": {
            "newest_fix_lag_hours": ais_lag_hours,
            "stale": bool(ais_lag_hours is not None and ais_lag_hours > 1),
            "note": ("Vessel positions come from the newest AIS fix at or before the "
                     "pass. When that lag is large the forward risk, entry times and "
                     "detours are computed from positions this old, not from where the "
                     "vessels are at the pass."),
        },
        "available_snapshots": scan["available_snapshots"],
        "pass_interval_hours": scan["pass_interval_hours"],
        "region": scan["region"], "synthetic_fleet": scan["synthetic_fleet"],
        "fleet": scan["ships"], "scanned": scan["scanned"],
        "detections": scan["detections"], "provenance": provenance,
        # Answered by services/environment.py, which reports whether the
        # values came from a committed historical dataset or from the stated
        # assumptions. With none committed this reads "fallback" and says why.
        # Wave is still genuinely absent: nothing in the pipeline uses it.
        #
        # NOTE: the drift below is still drift_vector()'s assumed vector, and
        # the hindcast, forecast and envelope still use it. Switching those over
        # to the environment service is a later phase; this block reports the
        # mode without yet changing a single computed figure.
        "environment": {**_environment_block(scan["region"], scan["observed_at"]),
                        "wave": None,
                        "drift": drift_vector()},
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
    #
    # Behaviour is scored once here rather than inside the loop: a vessel's track
    # is the same track whichever spill it is being ranked against, so scoring it
    # per detection was doing identical inference twice.
    behaviour_by_mmsi = score_fleet_behaviour(scan["ships"])
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
        det_heatmap = source_heatmap(det_spill["latitude"], det_spill["longitude"], hours)
        radius_km = fleet_search_radius_km(hours)
        det_ais = (rank_fleet(scan["ships"], det_source, release_at, radius_km=radius_km,
                              behaviour_by_mmsi=behaviour_by_mmsi)
                   if release_at else None)
        spill_entry = {
            "spill": det_spill,
            "source": det_source,
            "source_heatmap": det_heatmap,
            "age": {
                "estimated_hours": hours,
                "label": "Maximum age since release",
                "basis": (f"The previous pass was clear and this one is not, so the oil "
                          f"is at most one {hours} h satellite revisit old."),
                "release_at": release_at.strftime("%Y-%m-%dT%H:%M:%SZ") if release_at else None,
            },
            "affected_area": _affected_area(hours),
            "forecast": forecast(det_spill["latitude"], det_spill["longitude"]),
            "forecast_heatmap": forecast_heatmap(det_spill["latitude"], det_spill["longitude"]),
            # BOTH drift paths, side by side. `source`/`forecast` above are the
            # legacy fixed-vector estimates and still drive every downstream
            # figure — the search radius, the candidates, the counterfactual,
            # the risk polygons. These two are the environment-aware
            # integration of the same question, computed but not yet consumed,
            # so Phase 15 can show what a real field would change without this
            # phase moving a single number.
            "source_environmental": hindcast_environmental(
                det_spill["latitude"], det_spill["longitude"],
                scan["observed_at"], hours),
            "forecast_environmental": forecast_environmental(
                det_spill["latitude"], det_spill["longitude"],
                scan["observed_at"], FORECAST_HOURS),
            "drift_divergence": _drift_divergence(
                det_spill, scan["observed_at"], hours,
                ships=scan["ships"], release_at=release_at, radius_km=radius_km,
                behaviour_by_mmsi=behaviour_by_mmsi),
            "ais": det_ais,
            "candidates": det_ais["candidates"] if det_ais else [],
        }
        # Evidence quality, and whether any candidate is supported at all. Reads
        # the ranking above; the ranking is not changed by it.
        spill_entry["evidence"] = _evidence(
            spill_entry["candidates"], scan["ships"], det_spill,
            release_at, hours, base["environment"],
            spill_entry["drift_divergence"].get("ranking_change"))

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

    risk_overview = _combined_risk(spills, scan["ships"])

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
        "source_heatmap": primary.get("source_heatmap"),
        "ais": ais,
        "candidates": candidates,
        "forecast": fc,
        "forecast_heatmap": primary.get("forecast_heatmap"),
        "top_suspect": candidates[0] if candidates else None,
        "risk": risk,
        "risk_overview": risk_overview,
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
