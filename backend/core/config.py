"""
Central configuration and filesystem paths.

DEMO_MODE is the single switch between the bundled demo fixtures and the real
computation that will replace them:

    DEMO_MODE=1 (default) -> services read backend/data/demo/ fixtures
    DEMO_MODE=0           -> services raise NotImplementedError until the real
                             ML / drift / AIS implementations are connected

Nothing here imports the rest of the app, so any module may import it safely.
"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = BACKEND_DIR / "data"
DEMO_DATA_DIR = DATA_DIR / "demo"          # frozen synthetic fixtures
SIMULATION_DIR = DATA_DIR / "simulation"   # snapshot simulation (future ML input)
RUNTIME_DIR = DATA_DIR / "runtime"         # computed results, written at run time
IMAGES_DIR = DATA_DIR / "images"           # served at /demo-images


def _flag(name, default="1"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


DEMO_MODE = _flag("DEMO_MODE")

# Set when trained models are available; read by the adapters in ml/.
SPILL_MODEL_PATH = os.getenv("SPILL_MODEL_PATH")
ANOMALY_MODEL_PATH = os.getenv("ANOMALY_MODEL_PATH")


def model_provenance(model_path):
    """
    Where a model-backed result actually came from.

    Lets a caller tell a real inference apart from a demo placeholder without
    inspecting the value itself:

        {"source": "demo_stub", "model_version": None}
        {"source": "ml_model",  "model_version": "oil_detector_v1.pt"}
    """
    if DEMO_MODE or not model_path:
        return {"source": "demo_stub", "model_version": None}
    return {"source": "ml_model", "model_version": Path(model_path).name}


# Results read straight from a bundled fixture, with no model behind them and
# none planned for now.
FIXTURE_PROVENANCE = {"source": "demo_fixture", "model_version": None}

# Results this backend genuinely computes in both modes (drift, AIS geometry,
# the weighted score) — neither a model nor a fixture.
COMPUTED_PROVENANCE = {"source": "computed", "model_version": None}
