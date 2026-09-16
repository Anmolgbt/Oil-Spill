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
    assert len(result["detour_waypoints"]) >= 3
    exit_point = result["detour_waypoints"][1]
    assert not polygon.covers(Point(exit_point["longitude"], exit_point["latitude"]))
    onward = LineString([(p["longitude"], p["latitude"])
                          for p in result["detour_waypoints"][1:]])
    assert not onward.intersects(polygon)


def test_nearby_inside_routes_can_fan_to_opposite_sides():
    polygon = circle_polygon(0, 0, 5)
    left = suggest_detour(ship(lon=-0.02), [{"polygon": polygon}], 2, exit_side=-1)
    right = suggest_detour(ship(lon=-0.02), [{"polygon": polygon}], 2, exit_side=1)
    left_exit = left["detour_waypoints"][1]
    right_exit = right["detour_waypoints"][1]

    assert left["already_inside_zone"] and right["already_inside_zone"]
    assert left_exit["longitude"] < 0
    assert right_exit["longitude"] > 0
    assert not polygon.covers(Point(left_exit["longitude"], left_exit["latitude"]))
    assert not polygon.covers(Point(right_exit["longitude"], right_exit["latitude"]))


def test_destination_at_obstacle_center():
    from services.geo import destination
    vessel = ship()
    lat, lon = destination(0, -0.2, 12 * 1.852, 90)
    polygon = circle_polygon(lat, lon, 2)
    result = suggest_detour(vessel, [{"polygon": polygon}], 1)
    assert result and result["clears_spill_zone"]
    assert not route(result).intersects(polygon)
