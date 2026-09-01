"""
Simulated skimmer dispatch.

FICTIONAL RESPONSE ASSETS. The stations in core/config.SKIMMER_STATIONS do not
exist; they are placed around the demo AOI so that "which asset gets there
first" has a different answer for different spills. Nothing here should ever be
presented as real response capability, and the ETA is a straight-line transit
time at a constant speed — no routing, no traffic, no sea state, no
mobilisation time.

The point it demonstrates: once a spill is characterised and ranked, the
obvious next question is who responds, and that is a solvable geometry problem
against a known asset list.
"""
from core.config import SKIMMER_STATIONS, SKIMMER_TRANSIT_SPEED_KT

from .geo import bearing_deg, haversine_km

KT_TO_KMH = 1.852


def stations():
    """The response assets, as declared. Flagged simulated at every exit."""
    return [{**s, "simulated": True} for s in SKIMMER_STATIONS]


def dispatch_for(latitude, longitude, speed_kt=SKIMMER_TRANSIT_SPEED_KT):
    """
    Every station ranked by how fast it could reach (latitude, longitude).

    Straight-line distance over a constant transit speed. The first row is the
    recommended asset.
    """
    if latitude is None or longitude is None:
        return None

    speed_kmh = speed_kt * KT_TO_KMH
    options = []
    for station in SKIMMER_STATIONS:
        distance_km = haversine_km(station["latitude"], station["longitude"],
                                   latitude, longitude)
        options.append({
            "skimmer_id": station["id"],
            "name": station["name"],
            "latitude": station["latitude"],
            "longitude": station["longitude"],
            "distance_km": round(distance_km, 2),
            "eta_minutes": int(round(distance_km / speed_kmh * 60)) if speed_kmh else None,
            "bearing_to_spill_deg": round(
                bearing_deg(station["latitude"], station["longitude"], latitude, longitude), 1),
        })

    options.sort(key=lambda o: o["distance_km"])
    for i, option in enumerate(options):
        option["recommended"] = (i == 0)

    return {
        "label": "SIMULATED RESPONSE DISPATCH",
        "transit_speed_kt": speed_kt,
        "recommended": options[0],
        "options": options,
        "method": ("Great-circle distance from each station to the spill at a "
                   "constant transit speed."),
        "note": ("Fictional response assets for the demo. Straight-line ETA — no "
                 "routing, sea state, or mobilisation time is modelled."),
    }
