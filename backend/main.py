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

from routes import incident, spill, hindcast, forecast, ais, attribution, report

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

app.mount("/demo-images", StaticFiles(directory="data/images"), name="demo-images")

app.include_router(incident.router)
app.include_router(spill.router)
app.include_router(hindcast.router)
app.include_router(forecast.router)
app.include_router(ais.router)
app.include_router(attribution.router)
app.include_router(report.router)


@app.get("/")
def root():
    return {
        "service": "OILTRACE AI API",
        "status": "ok",
        "mode": "DEMO / SYNTHETIC DATA",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
