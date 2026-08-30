# Architecture

## Design principles

1. **A value is either measured, computed, or unavailable.** There is no fourth
   category. If a model cannot produce something, the API returns `null` and the
   UI renders "Not available". No placeholder, no plausible-looking estimate.
2. **Provenance travels with the data.** Every response says which parts came from
   a trained model and which the backend calculated, so a stubbed result can never
   be mistaken for a real one.
3. **The seam is the adapter.** All model-specific code lives in `backend/ml/`.
   Swapping a checkpoint touches one file; routes and the frontend never change.

## Request flow

```
browser
  │  POST /fleet/scan  {snapshot_id?}
  ▼
routes/fleet.py
  ▼
services/fleet_pipeline.py            ← orchestration lives here and nowhere else
  ├── services/snapshots.py           which passes exist, which tiles per vessel
  ├── ml/cnn_inference.py             classify each vessel's tile
  │       └── artifacts/oilspill_cnn.pth
  ├── services/investigation.py       drift constants, hindcast, forecast
  ├── ml/ais_inference.py             score each track for anomalous behaviour
  │       ├── artifacts/ais_isolation_forest.pkl
  │       ├── artifacts/ais_scaler.pkl
  │       └── data/ais_reference/ais_dataset.csv   (normalisation corpus)
  └── services/geo.py                 haversine, bearings, destination points
  ▼
one JSON payload → frontend/src/lib/oiltrace.ts → App.tsx
```

## Module responsibilities

| Module | Owns |
|---|---|
| `services/fleet_pipeline.py` | The 7 steps and their order. The only module that knows the sequence. |
| `services/investigation.py` | Drift arithmetic and scoring weights, shared with the single-scene `/ai/investigate` path. |
| `services/snapshots.py` | Pass discovery. Sorts `t0…t10` numerically, so dropping in a `t3` folder needs no code change. |
| `services/stored_result.py` | Adapts the stored Colab result into the same shape a live scan returns. |
| `services/geo.py` | Pure geometry. No domain knowledge. |
| `ml/cnn_inference.py` | Architecture, preprocessing and inference, reproduced from the notebook. |
| `ml/ais_inference.py` | Feature engineering, scaler, Isolation Forest, corpus normalisation. |

## Two things worth understanding

**Age comes from the revisit interval, not an assumption.** If a vessel's tile was
clear at t1 and oily at t2, the oil appeared between those passes. The 8 h
interval is therefore an upper bound on its age, and it also sets the hindcast
window. This is a real inference from monitoring cadence — the imagery itself
encodes nothing about age.

**The AIS corpus is required at runtime.** The notebook normalises anomaly scores
against dataset-wide min/max of `decision_function`. A single vessel's track
cannot be placed on that 0–100 scale in isolation, so the corpus ships with the
app and is scored once at startup, then cached. First scan ~2.5 s; subsequent
scans ~35 ms.

## Fallback chain

The dashboard degrades rather than failing:

1. `POST /fleet/scan` — both models run now. Badge: **LIVE INFERENCE**
2. `GET /ai-result` — the stored completed case. Badge: **STORED RESULT**
3. `/ai-data/oiltrace_ai_output_final.json` — same output bundled with the frontend

The badge always names the tier in use. A stored result is never presented as a
live one.

## Frontend

Single `App.tsx` with a light theme in `styles.css`. All data access goes through
`lib/oiltrace.ts`; components never call `fetch` directly and never compute an
investigation value — they render what the backend returned, or "Not available".

Layout: fleet list and forecast on the left, map centre, selected-vessel detail on
the right, and a leaderboard of flagged vessels across the bottom.

## Extending it

**Real segmentation** (would unlock spill area): train a U-Net or DeepLab, then
extend `ml/cnn_inference.py` to return a mask. `fleet_pipeline` already has a
`measured_area_km2` field wired through as `None` — populate it and the UI picks
it up.

**Real drift physics**: replace `hindcast_over()` and `forecast()` in
`services/investigation.py` with an OpenDrift run. The constants at the top of
that file are the only things the rest of the pipeline depends on.

**Live AIS**: `rank_fleet()` takes tracks as plain dicts. Point it at a live feed
instead of `fleet.json` and nothing downstream changes.
