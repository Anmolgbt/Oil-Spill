import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)

def get_incident():
    return _load("incident.json")

def get_vessels():
    return _load("vessels.json")["vessels"]

def get_hindcast():
    return _load("hindcast_particles.json")

def get_source_points():
    return _load("source_probability_points.json")

def get_geojson(name):
    return _load(name)
