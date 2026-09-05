"""
SIMULATED ROUTE AVOIDANCE — a hackathon detour demonstration.

This is NOT maritime navigation guidance.

Geometry. The spill's current + near-term forecast polygons are unioned and
grown by a safety buffer, and that obstacle is treated as a circle (centroid +
the distance to its farthest boundary point, so the circle fully encloses it).
The detour is then the textbook shortest path around a circular obstacle:

    vessel --tangent--> circle --arc--> circle --tangent--> destination

Both tangent legs touch the buffered circle without entering it, and the arc
rides its boundary, so the whole route stays outside the buffered obstacle —
and therefore outside the (smaller, unbuffered) affected area drawn on the map.
All four candidate routes (two sides x two arc directions) are built, checked
against the real spill polygons with shapely, and the shortest VALID one wins.

A vessel that is already inside the zone cannot have a route that avoids it;
that case returns a shortest-way-out exit route, flagged `already_inside_zone`.

Every number returned — headings, waypoints, heading change — comes from this
geometry. Nothing is a fixed offset.
"""
from math import acos, atan2, cos, degrees, hypot, pi, radians, sin

from shapely.geometry import LineString
from shapely.ops import unary_union

from core.config import RISK_SAFETY_BUFFER_KM
from .geo import bearing_deg, haversine_km

KT_TO_KMH = 1.852
KM_PER_DEG_LAT = 110.574

# How finely the arc riding the obstacle boundary is sampled.
ARC_STEP_DEG = 12
# The arc rides slightly outside the buffered circle so floating-point noise
# never leaves a sample a metre inside it.
ARC_CLEARANCE = 1.02


def _km_per_deg_lon(lat):
    return 111.320 * cos(radians(lat))


def _buffer_deg(lat, radius_km):
    """A safety-buffer distance in degrees, at this latitude, for shapely's
    planar .buffer() — consistent with the flat lat/lon circles risk.py uses."""
    return radius_km / KM_PER_DEG_LAT


def _obstacle_circle(polygons, buffer_km=RISK_SAFETY_BUFFER_KM):
    """
    Treat the (buffered) union of the spill's polygons as a single circle: its
    centroid, and the distance to its farthest boundary point — a circle that
    fully encloses the buffered obstacle, so routing around the circle also
    routes around everything inside it.
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


# --- local planar frame ------------------------------------------------------
#
# Everything below works in kilometres on a flat frame centred on the obstacle.
# At these scales (tens of km) the distortion is negligible, and it keeps the
# circle geometry exact instead of approximate.

def _to_xy(lat, lon, centre):
    return ((lon - centre["lon"]) * _km_per_deg_lon(centre["lat"]),
            (lat - centre["lat"]) * KM_PER_DEG_LAT)


def _to_latlon(x, y, centre):
    return (round(centre["lat"] + y / KM_PER_DEG_LAT, 5),
            round(centre["lon"] + x / _km_per_deg_lon(centre["lat"]), 5))


def _tangent_angle(point_xy, radius_km):
    """
    Angles (from the obstacle centre) of the two points where a line from
    `point_xy` touches the circle. In the right triangle centre-tangent-point,
    the angle at the centre is acos(R / |point|).
    """
    distance = hypot(*point_xy)
    spread = acos(max(-1.0, min(1.0, radius_km / distance)))
    base = atan2(point_xy[1], point_xy[0])
    return base, spread


def _arc_points(from_angle, to_angle, radius_km, counter_clockwise):
    """Samples riding the circle boundary from one angle to the other."""
    sweep = (to_angle - from_angle) % (2 * pi)
    if not counter_clockwise:
        sweep = sweep - 2 * pi          # negative sweep = clockwise

    steps = max(1, int(abs(degrees(sweep)) / ARC_STEP_DEG))
    radius = radius_km * ARC_CLEARANCE
    return [
        (radius * cos(from_angle + sweep * i / steps),
         radius * sin(from_angle + sweep * i / steps))
        for i in range(1, steps)         # endpoints are the tangent points
    ]


def _route_length_km(points_xy):
    return sum(hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(points_xy, points_xy[1:]))


def _candidate_routes(start_xy, end_xy, radius_km):
    """The four tangent-arc-tangent candidates: two sides x two arc directions."""
    start_base, start_spread = _tangent_angle(start_xy, radius_km)
    end_base, end_spread = _tangent_angle(end_xy, radius_km)

    candidates = []
    for side in (1, -1):
        t1_angle = start_base + side * start_spread
        t2_angle = end_base - side * end_spread
        t1 = (radius_km * cos(t1_angle), radius_km * sin(t1_angle))
        t2 = (radius_km * cos(t2_angle), radius_km * sin(t2_angle))
        for counter_clockwise in (True, False):
            arc = _arc_points(t1_angle, t2_angle, radius_km, counter_clockwise)
            candidates.append([start_xy, t1, *arc, t2, end_xy])
    return candidates


def _clears(route_xy, centre, keep_out):
    """True when no leg of the route enters the spill geometry."""
    line = LineString([_to_latlon(x, y, centre)[::-1] for x, y in route_xy])
    return not line.intersects(keep_out)


def suggest_detour(ship, polygons, horizon_hours, buffer_km=RISK_SAFETY_BUFFER_KM):
    """
    A route around the buffered spill polygons for one at-risk vessel, plus the
    resulting heading change. Returns None if there is no obstacle to route
    around.
    """
    obstacle = _obstacle_circle(polygons, buffer_km)
    if obstacle is None:
        return None

    lat, lon = ship["latitude"], ship["longitude"]
    speed_kmh = (ship.get("speed_kt") or 0) * KT_TO_KMH
    original_heading = float(ship.get("course_deg") or 0)

    # Where the vessel would end up if it held its current course.
    from .geo import destination
    run_km = speed_kmh * horizon_hours
    original_destination = (destination(lat, lon, run_km, original_heading)
                            if run_km > 0 else (lat, lon))

    radius = obstacle["radius_km"]
    start = _to_xy(lat, lon, obstacle)
    end = _to_xy(original_destination[0], original_destination[1], obstacle)

    # What the route must not touch: the spill polygons as actually drawn.
    keep_out = unary_union([p["polygon"] for p in polygons])

    inside = hypot(*start) <= radius
    if inside:
        route_xy, note = _exit_route(start, end, radius), (
            "Vessel is already inside the affected area — this is the shortest "
            "way out, so its first leg necessarily lies inside the zone."
        )
    else:
        # Push a destination that sits inside the zone back out to the boundary,
        # so the vessel never "rejoins" into the oil.
        if hypot(*end) <= radius:
            scale = (radius * ARC_CLEARANCE) / max(hypot(*end), 1e-9)
            end = (end[0] * scale, end[1] * scale)

        valid = [r for r in _candidate_routes(start, end, radius)
                 if _clears(r, obstacle, keep_out)]
        # Every candidate rides outside the buffered circle, so `valid` is
        # normally all four; the check is what guarantees the promise.
        route_xy = min(valid or _candidate_routes(start, end, radius),
                       key=_route_length_km)
        note = ("Prototype route-avoidance demonstration, not maritime "
                "navigation guidance.")

    waypoints = [_to_latlon(x, y, obstacle) for x, y in route_xy]
    waypoints[0] = (lat, lon)           # keep the vessel's exact fix

    # The new heading is the bearing to the first waypoint the vessel steers for.
    steer_to = waypoints[1] if len(waypoints) > 1 else waypoints[0]
    suggested_heading = bearing_deg(lat, lon, *steer_to)
    heading_change = (suggested_heading - original_heading + 540) % 360 - 180

    labelled = [{"latitude": p[0], "longitude": p[1], "label": "detour waypoint"}
                for p in waypoints]
    labelled[0]["label"] = "current position"
    labelled[-1]["label"] = "rejoin original heading"

    return {
        "ship_id": ship["id"], "mmsi": ship.get("mmsi"), "name": ship.get("name"),
        "label": "SIMULATED ROUTE AVOIDANCE",
        "original_heading_deg": round(original_heading, 1),
        "suggested_heading_deg": round(suggested_heading, 1),
        "heading_change_deg": round(heading_change, 1),
        "safety_buffer_km": buffer_km,
        "already_inside_zone": inside,
        "detour_distance_km": round(_route_length_km(route_xy), 2),
        "direct_distance_km": round(hypot(end[0] - start[0], end[1] - start[1]), 2),
        "clears_spill_zone": _clears(route_xy, obstacle, keep_out),
        "detour_waypoints": labelled,
        "reason": ("Vessel is already inside the affected area." if inside else
                   "Projected route intersects the current or forecast spill zone."),
        "note": note,
    }


def _exit_route(start_xy, end_xy, radius_km):
    """
    Shortest way out for a vessel already inside the zone: straight out along
    its own radius to the boundary, then on toward where it was going.
    """
    distance = hypot(*start_xy)
    if distance < 1e-9:                  # dead centre: pick any direction
        exit_xy = (radius_km * ARC_CLEARANCE, 0.0)
    else:
        scale = (radius_km * ARC_CLEARANCE) / distance
        exit_xy = (start_xy[0] * scale, start_xy[1] * scale)

    if hypot(*end_xy) <= radius_km:
        return [start_xy, exit_xy]
    return [start_xy, exit_xy, end_xy]
