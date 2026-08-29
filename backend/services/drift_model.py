import random
from .data_store import get_hindcast, get_geojson, get_incident

def run_hindcast(hours=4, n_particles=40):
    data = get_hindcast()
    particles = data["particles"][:max(1, min(n_particles or 40, len(data["particles"])))]
    # The bundled ensemble is deterministic demo output generated from
    # current + 3% wind. Reverse each path so the UI can animate from
    # observed slick toward inferred source.
    paths = []
    for p in particles:
        path = p["path"][:hours+1]
        paths.append({"id": p["id"], "path": path})
    inc = get_incident()
    return {
        "particles": paths,
        "steps": min(hours, data["steps"]-1),
        "drift_speed_kmh": inc["source_reconstruction"]["drift_speed_kmh"],
        "drift_bearing_deg": inc["source_reconstruction"]["drift_bearing_deg"],
    }

def run_forecast(hours=None):
    geo = get_geojson("forecast_polygons.geojson")
    wanted = hours or [6,12,24,36,48]
    features = [f for f in geo["features"] if f.get("properties",{}).get("hours") in wanted]
    return {"type":"FeatureCollection","features":features}
