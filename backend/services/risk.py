"""
Forward risk: which monitored vessels are projected to enter the spill area.

This is deliberately the mirror image of the existing attribution pipeline
(services/fleet_pipeline.rank_fleet / services/investigation.rank_candidates),
and must never be confused with it:

    ATTRIBUTION (hindcast)   "who may have caused this spill?"
                             uses HISTORIC AIS around the estimated origin/time.

    RISK (this module)       "who may run into this spill next?"
                             uses each vessel's CURRENT position, speed and
                             heading, projected forward, against the spill's
                             current and forecast polygons.

The projection is a straight line at constant speed and course — the same
kinematic-only philosophy already used for the spill's own forward forecast
(services/investigation.forecast). It is a prototype trajectory, not a
navigational prediction.
"""
from math import cos, pi, radians, sin

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from core.config import RISK_FORECAST_HOURS
from .geo import haversine_km

KM_PER_DEG_LAT = 110.574
KT_TO_KMH = 1.852

# How finely the projected track is sampled when looking for the entry point.
SAMPLE_MINUTES = 5

# Risk banding on estimated time-to-entry, within the forecast horizon.
HIGH_RISK_MINUTES = 120


def km_per_deg_lon(lat):
    return 111.320 * cos(radians(lat))


def circle_polygon(lat, lon, radius_km, points=48):
    """A circle of `radius_km` around (lat, lon), in the same flat lat/lon
    approximation the rest of this app already uses for drift envelopes."""
    dlat = radius_km / KM_PER_DEG_LAT
    dlon = radius_km / km_per_deg_lon(lat)
    ring = [
        (lon + dlon * sin(2 * pi * i / points), lat + dlat * cos(2 * pi * i / points))
        for i in range(points)
    ]
    return Polygon(ring)


def spill_polygons(spill_entry, max_hours_ahead=None):
    """
    Polygons associated with one detected spill: the current drift-envelope
    circle, plus one circle per forward forecast horizon. Each is tagged with
    the hours-ahead it represents so callers can label which zone a vessel hits.

    `max_hours_ahead` drops forecast horizons beyond that many hours — a
    vessel's own projection only runs `horizon_hours` out, so comparing it
    against, say, the spill's 48 h envelope when the vessel is only checked
    6 h ahead would flag risk against a zone the vessel's projection never
    actually reaches on the same timescale.
    """
    polys = []
    spill = spill_entry.get("spill") or {}
    area = spill_entry.get("affected_area") or {}
    lat, lon = spill.get("latitude"), spill.get("longitude")
    if lat is None or lon is None:
        return polys

    if area.get("radius_km"):
        polys.append({"hours_ahead": 0, "kind": "current",
                      "polygon": circle_polygon(lat, lon, area["radius_km"])})

    forecast = spill_entry.get("forecast") or {}
    for p in forecast.get("points", []):
        if max_hours_ahead is not None and p["hours_ahead"] > max_hours_ahead:
            continue
        # The forecast point is the envelope's projected centre; its own
        # distance from the spill is a reasonable radius for how far the
        # uncertainty has spread by that horizon.
        radius_km = max(haversine_km(lat, lon, p["latitude"], p["longitude"]), 1.0)
        polys.append({"hours_ahead": p["hours_ahead"], "kind": "forecast",
                      "polygon": circle_polygon(p["latitude"], p["longitude"], radius_km)})
    return polys


def project_track(ship, horizon_hours, sample_minutes=SAMPLE_MINUTES):
    """
    Straight-line projected positions for one vessel, at constant speed and
    course, from now out to `horizon_hours`. Returns a list of
    (minutes_elapsed, lat, lon).
    """
    lat, lon = ship["latitude"], ship["longitude"]
    speed_kmh = (ship.get("speed_kt") or 0) * KT_TO_KMH
    course = ship.get("course_deg") or 0
    theta = radians(course)

    steps = int(horizon_hours * 60 / sample_minutes) + 1
    points = []
    for i in range(steps):
        minutes = i * sample_minutes
        distance_km = speed_kmh * (minutes / 60)
        dlat = distance_km * cos(theta) / KM_PER_DEG_LAT
        dlon = distance_km * sin(theta) / km_per_deg_lon(lat)
        points.append((minutes, lat + dlat, lon + dlon))
    return points


def assess_vessel(ship, polygons, horizon_hours=RISK_FORECAST_HOURS):
    """
    Does this vessel's projected track enter any of the spill's polygons?

    Returns None for a vessel that stays clear (per the spec: safe vessels are
    not flagged), or a risk record with the entry time and which zone it hits.
    """
    if not polygons:
        return None

    union = unary_union([p["polygon"] for p in polygons])
    track = project_track(ship, horizon_hours)
    line = LineString([(lon, lat) for _, lat, lon in track])

    if not line.intersects(union):
        return None

    entry_minutes = None
    entry_kind = None
    for minutes, lat, lon in track:
        if Point(lon, lat).within(union):
            entry_minutes = minutes
            entry_kind = next((p["kind"] for p in polygons
                               if Point(lon, lat).within(p["polygon"])), "forecast")
            break
    if entry_minutes is None:
        # The path crosses the union between samples but no sample landed
        # inside it (e.g. clips a thin edge) — still a real geometric hit.
        entry_minutes = horizon_hours * 60
        entry_kind = "forecast"

    risk = "HIGH" if entry_minutes <= HIGH_RISK_MINUTES else "MEDIUM"
    start_minutes, start_lat, start_lon = track[0]
    end_minutes, end_lat, end_lon = track[-1]

    return {
        "ship_id": ship["id"], "mmsi": ship.get("mmsi"), "name": ship.get("name"),
        "risk": risk,
        "will_intersect_spill": True,
        "estimated_entry_minutes": int(entry_minutes),
        "entry_zone": entry_kind,
        "forecast_horizon_hours": horizon_hours,
        "original_heading_deg": ship.get("course_deg"),
        "projected_route": [
            {"latitude": start_lat, "longitude": start_lon},
            {"latitude": end_lat, "longitude": end_lon},
        ],
        "note": ("Straight-line kinematic projection at current speed and "
                 "course — a prototype trajectory, not a navigational prediction."),
    }


def assess_fleet(fleet, spill_entry, horizon_hours=RISK_FORECAST_HOURS):
    """
    Vessels-at-risk for one detected spill.

    `fleet` is the scanned ship list (current position/speed/course per
    vessel); `spill_entry` is one entry from run_fleet_scan()'s `spills` list.
    """
    polygons = spill_polygons(spill_entry, max_hours_ahead=horizon_hours)
    at_risk, safe_ids = [], []
    for ship in fleet:
        result = assess_vessel(ship, polygons, horizon_hours)
        if result:
            at_risk.append(result)
        else:
            safe_ids.append(ship["id"])

    at_risk.sort(key=lambda r: r["estimated_entry_minutes"])
    return {
        "forecast_horizon_hours": horizon_hours,
        "vessels_checked": len(fleet),
        "at_risk_count": len(at_risk),
        "safe_count": len(safe_ids),
        "at_risk": at_risk,
        "safe_ship_ids": safe_ids,
        "polygon_count": len(polygons),
        "method": ("Each vessel's current AIS fix projected forward at constant "
                   "speed/course, tested against the spill's current drift "
                   "envelope and forward forecast circles within the same "
                   "horizon."),
        "label": "FORWARD RISK — SIMULATED PROJECTION",
    }
