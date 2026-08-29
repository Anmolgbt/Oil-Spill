"""
Loader for the demo fixtures in backend/data/demo/.

These files are frozen synthetic data used only when DEMO_MODE is on. Nothing
here computes anything; it is the fallback source that real implementations
will replace. See backend/data/demo/README.md.
"""
import json

from core.config import DEMO_DATA_DIR

DATA = DEMO_DATA_DIR


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


def get_pipeline_demo():
    """Fixture backing the investigation pipeline while the models are absent."""
    return _load("pipeline_demo.json")
