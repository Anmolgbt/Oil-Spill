# OILTRACE AI
**Explainable Maritime Forensics for Oil-Spill Source Attribution**

Smart India Hackathon 2026 — hackathon MVP.

> **DEMO / SYNTHETIC DATA:** This build contains no real vessel, company, or spill event.


## Core story

**SATELLITE → SPILL → BACKTRACK → SOURCE + TIME → AIS → CANDIDATES → EVIDENCE SCORE → FORECAST → REPORT**

The dashboard turns an observed SAR dark patch into an investigation starting point. It:
- displays a prepared Sentinel-1 SAR scene and spill mask/overlay;
- checks oil vs. look-alike classes;
- visualizes backward particle hindcast and a probabilistic source region;
- reconstructs synthetic AIS traffic around the **source region + release window**;
- performs a SAR–AIS consistency check and flags one AIS-inconsistent contact;
- ranks six synthetic vessels using an explainable weighted score;
- shows the evidence behind the top candidate;
- visualizes a 48-hour forecast;
- replays the incident timeline;
- generates a printable investigation report.

The attribution result is **never presented as proof or legal responsibility**.

## Quick start

Requirements:
- Python 3.10+
- Node.js 18+

### Terminal 1 — backend

```bash
cd backend
python3 -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend:
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health

### Terminal 2 — frontend

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL, normally:
**http://localhost:5173**

### Fastest presentation setup

The frontend has static fallback data. If the backend is not running:

```bash
cd frontend
npm install
npm run dev
```

The header will show **LOCAL DEMO DATA**, but the investigation remains usable.

## Project structure

```text
oiltrace-ai/
├── backend/
│   ├── main.py
│   ├── models/
│   │   └── schemas.py
│   ├── routes/
│   │   ├── incident.py
│   │   ├── spill.py
│   │   ├── hindcast.py
│   │   ├── forecast.py
│   │   ├── ais.py
│   │   ├── attribution.py
│   │   └── report.py
│   ├── services/
│   │   ├── data_store.py
│   │   ├── spill_detection.py
│   │   ├── lookalike_filter.py
│   │   ├── drift_model.py
│   │   ├── ais_service.py
│   │   ├── vessel_attribution.py
│   │   └── report_service.py
│   ├── data/
│   └── scripts/
├── frontend/
│   ├── package.json
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── lib/api.ts
│   │   └── styles.css
│   └── public/
│       ├── demo-data/
│       └── demo-images/
├── ARCHITECTURE.md
├── DEMO_SCRIPT.md
└── README.md
```

## Demo dataset

Incident:
`IND-2026-001`

Synthetic vessels:
- MV Ocean Crest — top candidate, score 91
- MT Blue Horizon — score 70
- MV Sea Falcon — score 43
- MV Coastal Pioneer — AIS-inconsistent flag, score 42
- MT Eastern Star — score 38
- MV Neptune — score 18

Key demo values:
- Oil probability: **94%**
- Estimated area: **12.8 km²**
- Release window: **10:20–11:10 UTC**
- Source confidence: **78%**
- SAR contacts: **5**
- AIS matched: **4**
- AIS-inconsistent: **1**
- Forecast: **48 hours, Medium confidence**

## Scientific honesty

The spill detector is a **Demo Inference Engine** backed by a prepared, internally consistent scene. It is intentionally structured behind `/detect-spill` so a trained segmentation model can replace it later.

The drift model is an MVP particle model using the documented **current + 3% wind contribution** idea. It is not an operational oceanographic model.

The attribution engine is a deterministic, explainable weighted sum:

| Factor | Weight |
|---|---:|
| Time Match | 20% |
| Source Region Overlap | 25% |
| Trajectory Similarity | 20% |
| Distance | 15% |
| Behaviour Anomaly | 10% |
| AIS Consistency | 5% |
| Vessel Relevance | 5% |

It is explicitly a **Prototype Attribution Score**, not a validated forensic/legal model.

## Real-data integration seam

For a future real deployment, replace the demo data loaders/services with:
- Sentinel-1/Sentinel-2 imagery;
- live/historical AIS;
- wind and ocean-current products.

The UI/API contracts do not need to change.

## Troubleshooting

**Frontend says API is offline:** start the backend in Terminal 1. The frontend still works in local demo mode.

**Map is blank but controls work:** your environment may block OpenStreetMap tiles. The investigation layers still render when tiles are available on a normal network.

**`uvicorn` import error:** make sure you are inside `backend/` and installed `requirements.txt`.

**`npm` install fails:** check Node.js version (`node -v`) and internet access, then retry `npm install`.

## Credentials

**None.** The MVP has no login and no API keys.
