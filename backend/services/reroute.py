"""
SIMULATED ROUTE AVOIDANCE — a hackathon detour demonstration.

This is NOT maritime navigation guidance. It buffers the union of the spill's
current + forecast polygons by a configurable safety margin, treats that
buffered obstacle as a circle (its centroid and its farthest boundary point),
and computes the two geometric tangent lines from the at-risk vessel's current
position to that circle — the classic "go around the left or right side of an
obstacle" construction. It picks whichever tangent gives the shorter total
path back to the vessel's original projected destination.

Every number returned (heading, waypoints, heading change) comes from that
geometry — nothing here is a fixed offset.
"""
from math import asin, degrees, radians, sqrt

from shapely.ops import unary_union

from core.config import RISK_SAFETY_BUFFER_KM
from .geo import bearing_deg, destination, haversine_km

KT_TO_KMH = 1.852
KM_PER_DEG_LAT = 110.574


def _buffer_deg(lat, radius_km):
    """A safety-buffer distance in degrees, at this latitude, for shapely's
    planar .buffer() — consistent with the flat lat/lon circles risk.py uses."""
    return radius_km / KM_PER_DEG_LAT


def _obstacle_circle(polygons, buffer_km=RISK_SAFETY_BUFFER_KM):
    """
    Treat the (buffered) union of the spill's polygons as a single circle: its
    centroid, and the distance to its farthest boundary point (a circle that
    fully encloses the buffered obstacle, safe to route around).
    """
    if not polygons:
        return None
    union = unary_union([p["polygon"] for p in polygons])
    lat0 = union.centroid.y
    buffered = union.buffer(_buffer_deg(lat0, buffer_km))
    centroid = buffered.centroid
    center_lat, center_lon = centroid.y, centroid.x
    radius_km = max(
        haversine_km(center_lat, center_lon, y, x)
        for x, y in buffered.exterior.coords
    )
    return {"lat": center_lat, "lon": center_lon, "radius_km": radius_km}


def _tangent_points(vessel_lat, vessel_lon, obstacle):
    """The two points where a straight line from the vessel is tangent to the
    obstacle circle — the two ways to just clear it, left and right."""
    d_km = haversine_km(vessel_lat, vessel_lon, obstacle["lat"], obstacle["lon"])
    r_km = obstacle["radius_km"]
    if d_km <= r_km:
        # Vessel already inside the safety buffer: point it straight away
        # from the obstacle's centre rather than computing a tangent.
        away = bearing_deg(obstacle["lat"], obstacle["lon"], vessel_lat, vessel_lon)
        point = destination(vessel_lat, vessel_lon, r_km, away)
        return [point, point]

    tangent_km = sqrt(d_km ** 2 - r_km ** 2)
    alpha_deg = degrees(asin(r_km / d_km))
    bearing_to_center = bearing_deg(vessel_lat, vessel_lon, obstacle["lat"], obstacle["lon"])

    points = []
    for sign in (1, -1):
        tangent_bearing = (bearing_to_center + sign * alpha_deg) % 360
        points.append(destination(vessel_lat, vessel_lon, tangent_km, tangent_bearing))
    return points


def suggest_detour(ship, polygons, horizon_hours, buffer_km=RISK_SAFETY_BUFFER_KM):
    """
    A simple left/right detour waypoint around the buffered spill polygons for
    one at-risk vessel, plus the resulting heading change. Returns None if
    there is no obstacle to route around.
    """
    obstacle = _obstacle_circle(polygons, buffer_km)
    if obstacle is None:
        return None

    lat, lon = ship["latitude"], ship["longitude"]
    speed_kmh = (ship.get("speed_kt") or 0) * KT_TO_KMH
    original_heading = ship.get("course_deg") or 0.0
    destination_km = speed_kmh * horizon_hours
    original_destination = (destination(lat, lon, destination_km, original_heading)
                             if destination_km > 0 else (lat, lon))

    left, right = _tangent_points(lat, lon, obstacle)

    def path_length(waypoint):
        return (haversine_km(lat, lon, *waypoint)
                + haversine_km(*waypoint, *original_destination))

    waypoint = min((left, right), key=path_length)

    suggested_heading = bearing_deg(lat, lon, *waypoint)
    heading_change = (suggested_heading - original_heading + 540) % 360 - 180

    return {
        "ship_id": ship["id"], "mmsi": ship.get("mmsi"), "name": ship.get("name"),
        "label": "SIMULATED ROUTE AVOIDANCE",
        "original_heading_deg": round(original_heading, 1),
        "suggested_heading_deg": round(suggested_heading, 1),
        "heading_change_deg": round(heading_change, 1),
        "safety_buffer_km": buffer_km,
        "detour_waypoints": [
            {"latitude": lat, "longitude": lon, "label": "current position"},
            {"latitude": waypoint[0], "longitude": waypoint[1], "label": "detour waypoint"},
            {"latitude": original_destination[0], "longitude": original_destination[1],
             "label": "rejoin original heading"},
        ],
        "reason": "Projected route intersects the current or forecast spill zone.",
        "note": ("Prototype route-avoidance demonstration, not maritime "
                 "navigation guidance."),
    }
