"""
OILTRACE AI — backend entrypoint.

Run with:
    uvicorn main:app --reload --port 8000

The app is fully self-contained: on startup it serves the bundled demo
dataset (backend/data/) so it never depends on an external satellite, AIS,
or metocean API to run. See routes/ for REAL DATA MODE placeholders.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import DEMO_MODE, IMAGES_DIR, SIMULATION_DIR
from services.pipeline import pipeline_provenance
from routes import (incident, spill, hindcast, forecast, ais, attribution,
                    report, pipeline)

app = FastAPI(
    title="OILTRACE AI API",
    description="Explainable Maritime Forensics for Oil-Spill Source Attribution (Hackathon MVP)",
    version="0.1.0",
)

# Hackathon MVP: allow the Vite dev server (and any origin) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Both mounts use absolute paths from core.config, so they work regardless of the
# directory uvicorn was started from.
app.mount("/demo-images", StaticFiles(directory=IMAGES_DIR), name="demo-images")
app.mount(
    "/simulation-images",
    StaticFiles(directory=SIMULATION_DIR / "snapshots"),
    name="simulation-images",
)

app.include_router(incident.router)
app.include_router(spill.router)
app.include_router(hindcast.router)
app.include_router(forecast.router)
app.include_router(ais.router)
app.include_router(attribution.router)
app.include_router(report.router)
app.include_router(pipeline.router)


@app.get("/")
def root():
    return {
        "service": "OILTRACE AI API",
        "status": "ok",
        "mode": "DEMO / SYNTHETIC DATA" if DEMO_MODE else "REAL",
        "demo_mode": DEMO_MODE,
        "provenance": pipeline_provenance(),
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
