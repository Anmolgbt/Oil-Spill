"""
OILTRACE — API entrypoint.

Run with:
    uvicorn main:app --reload --port 8000

Two trained models do the work, both loaded from backend/artifacts/:

    oilspill_cnn.pth          binary SAR classifier (oil / no oil)
    ais_isolation_forest.pkl  behavioural anomaly detector over AIS tracks

Everything between them - drift hindcast, the AIS search, the suspect ranking and
the forward projection - is computed here. Nothing is hardcoded; anything the
models cannot produce is reported as unavailable rather than estimated.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import AI_OUTPUT_DIR, SIMULATION_DIR
from routes import ais, cnn, fleet, investigate, stored_result

app = FastAPI(
    title="OILTRACE API",
    description=(
        "Satellite + AIS oil-spill monitoring. Detects spills in SAR imagery, "
        "traces them back to a probable source, and ranks nearby vessels by "
        "analytical association — never by proof of responsibility."
    ),
    version="1.0.0",
)

# The Vite dev server runs on another port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Absolute paths from core.config, so the mounts work regardless of the directory
# uvicorn was started from.
app.mount(
    "/simulation-images",
    StaticFiles(directory=SIMULATION_DIR / "snapshots"),
    name="simulation-images",
)
app.mount(
    "/ai-images",
    StaticFiles(directory=AI_OUTPUT_DIR / "samples"),
    name="ai-images",
)

app.include_router(fleet.router)
app.include_router(stored_result.router)
app.include_router(cnn.router)
app.include_router(ais.router)
app.include_router(investigate.router)


@app.get("/")
def root():
    """Service banner and the routes worth knowing about."""
    return {
        "service": "OILTRACE",
        "status": "ok",
        "endpoints": {
            "fleet_scan": "POST /fleet/scan",
            "fleet": "GET /fleet",
            "stored_result": "GET /ai-result",
            "cnn_status": "GET /ai/cnn/status",
            "ais_status": "GET /ai/ais/status",
            "single_investigation": "POST /ai/investigate",
        },
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
