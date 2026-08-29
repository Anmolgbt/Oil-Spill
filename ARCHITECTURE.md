# ARCHITECTURE.md — OILTRACE AI

## Design goals (hackathon constraints)

1. **Zero mandatory external dependency.** No API key, no live satellite
   feed, no live AIS feed is required for the app to run and demo
   convincingly. Everything works from bundled synthetic data.
2. **Explainability over sophistication.** Every score the system produces
   traces back to a small number of named, weighted factors a judge can
   inspect in ~10 seconds.
3. **Same interface, swappable engine.** Every ML/physics piece (spill
   detection, drift model, attribution) is a plain function with a fixed
   signature. Replacing the demo body with a trained model or a live feed
   touches one file, not the UI.

## High-level data flow

```
                       ┌─────────────────────────┐
                       │   backend/data/*.json     │  ← generated once by
                       │   (spill, source region,  │    scripts/generate_*.py
                       │    vessels, tracks, env)  │
                       └────────────┬─────────────┘
                                    │  data_store.py (cached loader)
        ┌───────────────┬──────────┼───────────┬─────────────────┐
        ▼               ▼          ▼           ▼                 ▼
 spill_detection  lookalike_filter drift_model ais_service  vessel_attribution
        │               │          │           │                 │
        └───────────────┴────┬─────┴───────────┴─────────────────┘
                              ▼
                        routes/*.py (FastAPI)
                              │
                              ▼  REST (JSON / GeoJSON)
                     frontend/src/lib/api.ts
                              │  (falls back to /public/demo-data/*.json
                              │   if the backend is unreachable)
                              ▼
                  useInvestigation() state machine
                              │
                              ▼
        App.tsx → Header / ControlsPanel / MapView / IntelligencePanel
                   / TimelineBar / ReplayModal / ReportModal
```

## Backend

FastAPI, organized by responsibility (per the brief's suggested layout):

| Module | Responsibility |
|---|---|
| `services/data_store.py` | Single seam between "demo JSON" and "real feed." Cached loaders only — no other module touches the filesystem. |
| `services/spill_detection.py` | Demo Inference Engine — same call signature (`run_detection(scene_id)`) a trained SAR segmentation model would expose. |
| `services/lookalike_filter.py` | Oil vs. biofilm / low-wind / other-dark-feature classification, so "dark patch" is never silently assumed to be oil. |
| `services/drift_model.py` | Real particle-drift math: `velocity = ocean_current + 0.03 × wind` (the classic "3% wind rule"), applied backward (hindcast) or forward (forecast) with per-particle noise for an ensemble spread. This is genuinely computed, not just replayed — see `combine_drift()` / `run_hindcast()`. |
| `services/ais_service.py` | Historical AIS reconstruction scoped to the **probable source region + release-time window** (not the visible slick), plus the SAR–AIS consistency check. |
| `services/vessel_attribution.py` | The explainable weighted-sum attribution engine (weights below). Deterministic and inspectable — `explain(vessel_id)` returns the full per-factor breakdown, not just a final number. |
| `services/report_service.py` | Assembles the consolidated Investigation Report payload from every other service. |

### Attribution weights

```
Time Match              20%
Source Region Overlap   25%
Trajectory Similarity   20%
Distance                15%   (derived: max(0, 100 − km × 10))
Behaviour Anomaly       10%
AIS Consistency          5%
Vessel Relevance         5%
```

This is intentionally simple and auditable — a judge can multiply the
numbers on screen and get the shown score. It is explicitly **not**
presented as scientifically validated (see README → Scientific Honesty).

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/detect-spill` | Run (demo) spill detection + look-alike filter |
| POST | `/characterize-spill` | Spill metrics + source reconstruction |
| POST | `/hindcast` | Backward particle simulation |
| POST | `/forecast` | Forward particle/polygon simulation |
| POST | `/ais/candidates` | AIS vessels found in source region + release window |
| POST | `/attribute` | Full explainable score breakdown for one vessel |
| GET | `/incident/{id}` | Full incident object |
| GET | `/report/{id}` | Consolidated investigation report |

All endpoints degrade gracefully: if `backend/data/*.json` is missing, run
`backend/scripts/generate_demo_data.py` to regenerate it (deterministic,
seeded — always produces the same incident).

## Frontend

- **`lib/api.ts`** — every fetch function tries the FastAPI backend with a
  1.5s timeout, then falls back to the identical JSON bundled under
  `public/demo-data/`. The UI never shows an error state because of this —
  it always has *some* valid response to render.
- **`hooks/useInvestigation.ts`** — the single state machine for the whole
  app. Owns: which pipeline step is active, the hindcast/forecast animation
  clocks, the selected vessel, and the replay/report modal state. `App.tsx`
  is purely presentational and reads from this hook.
- **`components/MapView.tsx`** — all map layers (spill polygon, source
  region "heatmap" — an inner + outer polygon glow, hindcast particles,
  forecast envelope, vessel tracks/markers, wind/current arrows) as a
  single Leaflet map. No external heatmap plugin is used — the glow effect
  is two concentric polygons at different opacities, which is enough to
  read as "probabilistic region" without adding a dependency.
- **Design system** — dark maritime "HUD" theme defined once in
  `tailwind.config.js` (color tokens: `abyss`, `spill`, `source`, `risk`,
  `vessel`) and `index.css` (the `.hud-frame` corner-bracket motif used on
  every panel).

## Why these simplifications were made

| Cut corner | Why it's OK for an MVP demo |
|---|---|
| No trained segmentation model | A real Sentinel-1 U-Net would take days to train/validate; the interface is identical, so swapping it in later is a one-file change. |
| No live AIS/Sentinel/metocean feeds | Judges need the demo to work with no network flakiness; `data_store.py` is the explicit seam for later integration. |
| No heatmap plugin, no vector-field grid | Two polygons + a handful of arrow markers read correctly on a projector at demo distance, at zero extra dependency cost. |
| Deterministic instead of "real" ML scoring | Explainability was an explicit judging criterion — a formula a judge can verify by hand is more convincing than a black-box confidence number. |
