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
T3_OIL_MIN = 2
T3_OIL_MAX = 2

# --- forward risk / reroute simulation ---------------------------------------
# How far ahead a vessel's straight-line projected track is checked against the
# spill polygons, and how much clearance the demo detour keeps from the spill's
# buffered edge. Both are prototype constants, not navigational standards.
RISK_FORECAST_HOURS = 6
RISK_SAFETY_BUFFER_KM = 3.0

# --- assumed environment ------------------------------------------------------
# THESE ARE ASSUMPTIONS, NOT OBSERVATIONS. No wind/current/wave feed is wired
# up, so the impact envelope in services/damage.py is driven by these stated
# constants. Swapping in a real met-ocean feed means replacing these values and
# nothing else. Directions are the compass bearing the flow moves TOWARD.
ASSUMED_CURRENT_SPEED_MS = 0.5
ASSUMED_CURRENT_DIRECTION_DEG = 170.0
ASSUMED_WIND_SPEED_MS = 5.0
ASSUMED_WIND_DIRECTION_DEG = 200.0

# Standard slick-drift rule of thumb: a surface slick travels with the current
# plus roughly 3% of the wind speed. Used to size the impact envelope.
WIND_DRIFT_FACTOR = 0.03

# Weights for the response-priority score (must sum to 1.0). The score ranks
# spills against each other for response order; it is not a damage measurement.
DAMAGE_WEIGHT_AREA = 0.45
DAMAGE_WEIGHT_CONFIDENCE = 0.30
DAMAGE_WEIGHT_VESSEL_SIZE = 0.25

# --- response advisory --------------------------------------------------------
# The dashboard reports WHAT needs escalating and in what order; it does not
# model who responds or with what. Any concrete asset list (skimmers, cutters,
# ETAs) would be invented, so the output stops at "notify the authority".
# Priority-score bands used to word that advisory.
ADVISORY_URGENT_SCORE = 75.0
ADVISORY_ELEVATED_SCORE = 50.0
