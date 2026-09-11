"""
Small geographic helpers shared by the pipeline steps.

Plain trigonometry, no dependencies. Distances are great-circle kilometres.
"""
from datetime import datetime
from math import asin, atan2, cos, degrees, radians, sin, sqrt

# IUGG mean Earth radius. Used by every great-circle calculation in the
# pipeline. services/investigation.py used to carry a second haversine at
# 6371.0 for notebook fidelity; the two agreed to within 0.2 m over 148 km
# (1.4 ppm, entirely the radius) and the atan2 and asin forms are
# mathematically identical, so there is now only this one.
EARTH_RADIUS_KM = 6371.0088

# FLAT-EARTH APPROXIMATIONS.
#
# Three of them, deliberately, because they are not interchangeable and
# collapsing them would break things that currently work:
#
#   KM_PER_DEG_LAT_WGS84 / _km_per_deg_lon()
#       Used by risk.py and reroute.py, which do planar shapely geometry on
#       lat/lon and need a conversion consistent with the circles they draw.
#
#   KM_PER_DEG_NOTEBOOK
#       The flat 1/111 the notebook's hindcast used. fleet_pipeline.hindcast_over()
#       and counterfactual.py BOTH use it, and counterfactual mirrors the
#       hindcast's arithmetic exactly so that forward-then-backward closes to
#       0.00 km. Substituting the spherical destination() here leaves a residual
#       that is pure method mismatch rather than evidence. Do not "fix" it.
KM_PER_DEG_LAT_WGS84 = 110.574
KM_PER_DEG_LON_EQUATOR = 111.320
KM_PER_DEG_NOTEBOOK = 111.0


def km_per_deg_lon(lat):
    """Kilometres per degree of longitude at this latitude (planar helper)."""
    return KM_PER_DEG_LON_EQUATOR * cos(radians(lat))


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in kilometres."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, in degrees clockwise from north."""
    dlon = radians(lon2 - lon1)
    y = sin(dlon) * cos(radians(lat2))
    x = (cos(radians(lat1)) * sin(radians(lat2))
         - sin(radians(lat1)) * cos(radians(lat2)) * cos(dlon))
    return (degrees(atan2(y, x)) + 360) % 360


def angle_diff(a, b):
    """Smallest absolute difference between two bearings, 0-180 degrees."""
    return abs((a - b + 180) % 360 - 180)


def destination(lat, lon, distance_km, bearing):
    """Point reached by travelling distance_km from (lat, lon) on a bearing."""
    d = distance_km / EARTH_RADIUS_KM
    b, lat1, lon1 = radians(bearing), radians(lat), radians(lon)
    lat2 = asin(sin(lat1) * cos(d) + cos(lat1) * sin(d) * cos(b))
    lon2 = lon1 + atan2(sin(b) * sin(d) * cos(lat1), cos(d) - sin(lat1) * sin(lat2))
    return round(degrees(lat2), 5), round(degrees(lon2), 5)


def parse_time(value):
    """Parse an ISO-8601 timestamp, tolerating a trailing Z."""
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
