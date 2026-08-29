"""
AIS traffic reconstruction around the source region and release window.

DEMO_MODE on  -> vessel records from the demo fixture (data/demo/vessels.json),
                 which carries both identity and precomputed attribution factors
DEMO_MODE off -> real historic AIS ingestion and filtering, not connected

Ship identity for the snapshot simulation lives separately in
data/simulation/ships.json and is served by simulation_service.py.
"""
import json

from core.config import DEMO_MODE, SIMULATION_DIR

from .data_store import get_vessels, get_incident, get_pipeline_demo
from .geo import haversine_km, parse_time


def load_demo_candidates():
    vessels = get_vessels()
    return {"count": len(vessels), "vessels": vessels}


def load_demo_tracks():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "vessel_id": v["vessel_id"],
                    "vessel_name": v["vessel_name"],
                    "ais_dark": v["ais_dark"],
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[p["lon"], p["lat"]] for p in v["track"]],
                },
            }
            for v in get_vessels()
        ],
    }


def get_candidates():
    """Vessels present in the source region during the release window."""
    if DEMO_MODE:
        return load_demo_candidates()

    raise NotImplementedError(
        "AIS ingestion not connected yet. Filter historic AIS to the source "
        "polygon x release-time window, then drop irrelevant traffic."
    )


def get_tracks():
    """Candidate vessel tracks as GeoJSON LineStrings."""
    if DEMO_MODE:
        return load_demo_tracks()

    raise NotImplementedError("AIS ingestion not connected yet.")


def sar_ais_consistency_check():
    """SAR ship contacts matched against AIS positions; unmatched = possibly dark."""
    if DEMO_MODE:
        return get_incident()["sar_ais_check"]

    raise NotImplementedError(
        "SAR-AIS matching not connected yet. Requires a SAR ship detector "
        "(CFAR or trained) matched against AIS positions at acquisition time."
    )


# --- step 4: historic AIS around the estimated origin -------------------------

AIS_HISTORY_FILE = SIMULATION_DIR / "ais_history.json"


def get_ais_history():
    """Per-ship position history for the simulation ships."""
    with open(AIS_HISTORY_FILE, encoding="utf-8") as f:
        return {s["ship_id"]: s["track"] for s in json.load(f)["ships"]}


def _gaps(track, window=None, interval_minutes=15):
    """
    AIS reporting gaps: consecutive points more than 1.5 intervals apart.

    When a release window is given, each gap also reports how many of its minutes
    fall inside that window. A vessel that stops reporting exactly while the oil
    was released is the case attribution cares about.
    """
    found = []
    for a, b in zip(track, track[1:]):
        start, end = parse_time(a["time"]), parse_time(b["time"])
        minutes = (end - start).total_seconds() / 60
        if minutes <= interval_minutes * 1.5:
            continue
        gap = {"from": a["time"], "to": b["time"], "minutes": round(minutes),
               "minutes_in_window": 0}
        if window:
            overlap = (min(end, window[1]) - max(start, window[0])).total_seconds() / 60
            gap["minutes_in_window"] = round(max(0.0, overlap))
        found.append(gap)
    return found


def find_vessels_near(origin, ships, radius_km=None):
    """
    Reconstruct traffic around the estimated origin during the release window.

    For each ship: keep only the AIS points inside the window, take the closest
    approach to the origin, and drop the vessel if it never came within the
    search radius. This is the "filter out irrelevant traffic" step.

    Ships are the identity records from ships.json; history comes from
    ais_history.json.
    """
    demo = get_pipeline_demo()
    radius = radius_km if radius_km is not None else demo["search_radius_km"]
    history = get_ais_history()

    start = parse_time(origin["release_window_start"])
    end = parse_time(origin["release_window_end"])

    assessed = []
    for ship in ships:
        track = history.get(ship["id"], [])
        window = [p for p in track if start <= parse_time(p["time"]) <= end]

        if not window:
            assessed.append({
                **ship, "retained": False, "reason": "no AIS position in release window",
                "min_distance_km": None, "closest_time": None,
                "window_points": 0, "gaps": _gaps(track, (start, end)), "track": track,
            })
            continue

        measured = [
            (haversine_km(origin["origin_lat"], origin["origin_lon"], p["lat"], p["lon"]), p)
            for p in window
        ]
        min_km, closest = min(measured, key=lambda m: m[0])
        first_km = measured[0][0]
        retained = min_km <= radius

        assessed.append({
            **ship,
            "retained": retained,
            "reason": (f"closest approach {round(min_km, 1)} km"
                       if retained else
                       f"{round(min_km, 1)} km away, outside {radius} km search radius"),
            "min_distance_km": round(min_km, 2),
            "first_distance_km": round(first_km, 2),
            "closest_time": closest["time"],
            "closest_point": closest,
            "window_points": len(window),
            "gaps": _gaps(track, (start, end)),
            "track": track,
        })

    retained = [v for v in assessed if v["retained"]]
    return {
        "origin": {"lat": origin["origin_lat"], "lon": origin["origin_lon"]},
        "release_window": [origin["release_window_start"], origin["release_window_end"]],
        "search_radius_km": radius,
        "searched": len(assessed),
        "retained": len(retained),
        "eliminated": len(assessed) - len(retained),
        "vessels": assessed,
        "candidates": retained,
    }
