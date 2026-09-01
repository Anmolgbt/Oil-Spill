"""
Filesystem paths and shared constants.

Every path is resolved from this file's own location, so the app runs correctly
regardless of the working directory uvicorn was started from. Nothing here
imports the rest of the app, so any module may import it safely.
"""
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = BACKEND_DIR / "data"

# Monitored fleet: fleet.json plus the satellite passes under snapshots/.
# Served to the browser at /simulation-images.
SIMULATION_DIR = DATA_DIR / "simulation"

# Completed AI result from the Colab handoff, used as the dashboard's fallback
# when a live scan is unavailable. Its samples/ folder is served at /ai-images.
AI_OUTPUT_DIR = DATA_DIR / "ai_output"

# AIS corpus the Isolation Forest was trained and scored on. Required at runtime:
# the notebook normalises anomaly scores against dataset-wide min/max, so a single
# vessel cannot be scored on the same 0-100 scale without it.
AIS_REFERENCE_FILE = DATA_DIR / "ais_reference" / "ais_dataset.csv"

# Trained model files.
MODEL_ARTIFACTS_DIR = BACKEND_DIR / "artifacts"

# Marks a value this backend calculates itself — drift geometry, AIS distances,
# the weighted score — as opposed to one a trained model produced.
COMPUTED_PROVENANCE = {"source": "computed", "model_version": None}

# --- t3 oil/no-oil simulation -------------------------------------------------
# The t3 satellite pass is the only one where a vessel's tile may show oil. Which
# vessels get an oil tile is decided by a seeded random draw BEFORE the CNN ever
# sees an image, so the same seed always replays the same demo and the model's
# own verdict is never told the answer in advance.
SIMULATION_SEED = 42
T3_OIL_MIN = 1
T3_OIL_MAX = 3

# --- forward risk / reroute simulation ---------------------------------------
# How far ahead a vessel's straight-line projected track is checked against the
# spill polygons, and how much clearance the demo detour keeps from the spill's
# buffered edge. Both are prototype constants, not navigational standards.
RISK_FORECAST_HOURS = 6
RISK_SAFETY_BUFFER_KM = 3.0
