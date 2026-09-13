"""Regression checks for disconnected zones and routes starting inside oil."""
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
from services.risk import circle_polygon
from services.reroute import suggest_detour


def ship(lat=0, lon=-0.2, heading=90):
    return {"id": "test", "latitude": lat, "longitude": lon,
            "speed_kt": 12, "course_deg": heading}


def route(result):
    return LineString([(p["longitude"], p["latitude"])
                       for p in result["detour_waypoints"]])


def test_disconnected_spill_zones():
    polygons = [{"polygon": circle_polygon(0, x, 2)} for x in (-0.04, 0.04)]
    result = suggest_detour(ship(), polygons, 2)
    assert result and result["clears_spill_zone"]
    assert not route(result).intersects(unary_union([p["polygon"] for p in polygons]))


def test_inside_route_exits_without_crossing_back():
    polygon = circle_polygon(0, 0, 5)
    result = suggest_detour(ship(lon=-0.02), [{"polygon": polygon}], 2)
    assert result["already_inside_zone"]
    assert not result["clears_spill_zone"]
    assert len(result["detour_waypoints"]) == 2
    endpoint = result["detour_waypoints"][-1]
    assert not polygon.covers(Point(endpoint["longitude"], endpoint["latitude"]))
    assert endpoint["longitude"] < -0.02


def test_destination_at_obstacle_center():
    from services.geo import destination
    vessel = ship()
    lat, lon = destination(0, -0.2, 12 * 1.852, 90)
    polygon = circle_polygon(lat, lon, 2)
    result = suggest_detour(vessel, [{"polygon": polygon}], 1)
    assert result and result["clears_spill_zone"]
    assert not route(result).intersects(polygon)
