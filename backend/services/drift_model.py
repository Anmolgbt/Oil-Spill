"""
Backward hindcast and forward forecast of the slick.

DEMO_MODE on  -> replays the prerecorded particle ensemble and forecast polygons
                 from data/demo/ (generated once from current + 3% wind)
DEMO_MODE off -> real drift integration (OpenDrift or equivalent), not connected

The prerecorded data lives only in data/demo/; nothing is duplicated here.
"""
import random
from datetime import timedelta

from core.config import DEMO_MODE

from .data_store import get_hindcast, get_geojson, get_incident, get_pipeline_demo
from .geo import destination, parse_time


def load_demo_hindcast(hours=4, n_particles=40):
    """Prerecorded backward particle paths from the demo fixture."""
    data = get_hindcast()
    particles = data["particles"][:max(1, min(n_particles or 40, len(data["particles"])))]
    paths = [{"id": p["id"], "path": p["path"][:hours + 1]} for p in particles]
    inc = get_incident()
    return {
        "particles": paths,
        "steps": min(hours, data["steps"] - 1),
        "drift_speed_kmh": inc["source_reconstruction"]["drift_speed_kmh"],
        "drift_bearing_deg": inc["source_reconstruction"]["drift_bearing_deg"],
    }


def load_demo_forecast(hours=None):
    """Prerecorded forward drift envelopes from the demo fixture."""
    geo = get_geojson("forecast_polygons.geojson")
    wanted = hours or [6, 12, 24, 36, 48]
    features = [f for f in geo["features"] if f.get("properties", {}).get("hours") in wanted]
    return {"type": "FeatureCollection", "features": features}


def run_hindcast(hours=4, n_particles=40):
    """Trace the slick backward toward its probable origin point and time."""
    if DEMO_MODE:
        return load_demo_hindcast(hours, n_particles)

    raise NotImplementedError(
        "Backward drift model not connected yet. Seed particles from the detected "
        "mask and integrate with a negative time step using wind + current fields."
    )


def run_forecast(hours=None):
    """Project the slick forward over the requested horizons."""
    if DEMO_MODE:
        return load_demo_forecast(hours)

    raise NotImplementedError(
        "Forward drift model not connected yet. Expected return shape: "
        "a GeoJSON FeatureCollection with an 'hours' property per feature."
    )


# --- step 3: trace the slick back to a probable origin ------------------------

def estimate_origin(spill, observed_at):
    """
    Trace an observed slick backward to a probable release point and time.

    The slick is carried by current + wind, so where it is seen is not where it
    was released. Moving back along the drift vector for the hindcast period
    gives the probable origin; the particle spread around it expresses that the
    answer is a region, not a point.

    Returns origin lat/lon, the release window, and a particle cloud for the map.
    """
    drift = get_pipeline_demo()["drift"]
    hours = drift["hindcast_hours"]
    distance = drift["speed_kmh"] * hours
    back_bearing = (drift["bearing_deg"] + 180) % 360

    origin_lat, origin_lon = destination(
        spill["latitude"], spill["longitude"], distance, back_bearing
    )

    observed = parse_time(observed_at)
    origin_time = observed - timedelta(hours=hours)
    half = timedelta(hours=drift["release_window_half_hours"])

    # Particle cloud: the same backward vector with per-particle spread, so the
    # UI can show convergence rather than a single deterministic point.
    rng = random.Random(1729)
    spread = drift["spread_km"]
    particles = []
    for i in range(drift["n_particles"]):
        path = []
        jitter_b = rng.uniform(-18, 18)
        jitter_s = rng.uniform(0.75, 1.25)
        for step in range(int(hours) + 1):
            lat, lon = destination(
                spill["latitude"], spill["longitude"],
                drift["speed_kmh"] * step * jitter_s,
                (back_bearing + jitter_b) % 360,
            )
            path.append({"lat": lat, "lon": lon})
        particles.append({"id": f"p{i:02d}", "path": path})

    return {
        "origin_lat": origin_lat,
        "origin_lon": origin_lon,
        "estimated_time": origin_time.strftime("%H:%M"),
        "release_window_start": (origin_time - half).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "release_window_end": (origin_time + half).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "confidence": drift["confidence"],
        "drift_speed_kmh": drift["speed_kmh"],
        "drift_bearing_deg": drift["bearing_deg"],
        "hindcast_hours": hours,
        "spread_km": spread,
        "particles": particles,
        "steps": int(hours),
    }


# --- step 7: forward forecast from the detected spill -------------------------

def forecast_from_spill(spill, hours=None):
    """
    Project the detected slick forward along the same drift vector.

    Each horizon is an envelope around the drifted centre; the envelope grows
    with time because drift uncertainty compounds. Returned as GeoJSON so it
    drops into the existing map layer unchanged.
    """
    drift = get_pipeline_demo()["drift"]
    horizons = hours or drift["forecast_hours"]
    features = []

    for h in horizons:
        lat, lon = destination(
            spill["latitude"], spill["longitude"],
            drift["speed_kmh"] * h, drift["bearing_deg"],
        )
        radius = drift["spread_km"] + drift["speed_kmh"] * h * 0.22
        ring = [list(reversed(destination(lat, lon, radius, b * 15))) for b in range(25)]
        features.append({
            "type": "Feature",
            "properties": {
                "hours": h,
                "centre": [lat, lon],
                "radius_km": round(radius, 2),
            },
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })

    return {"type": "FeatureCollection", "features": features}
