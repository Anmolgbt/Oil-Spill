# Demo fixtures — frozen synthetic data

Everything in this folder is **hand-authored synthetic data** for the hackathon
demo. No real vessel, company, or spill event is represented. These files are the
single canonical source for every hardcoded value in the backend: no service
contains literal probabilities, areas, or scores of its own.

They are read **only when `DEMO_MODE=1`** (the default). With `DEMO_MODE=0` the
services raise `NotImplementedError` until the real implementations are connected.

| File | Feeds | Notable fixture values |
|------|-------|------------------------|
| `incident.json` | `/incident`, `/detect-spill`, `/characterize-spill`, `/forecast`, `/ais/consistency-check`, `/report` | `spill_probability 0.94`, `estimated_area_km2 12.8`, `source_confidence 0.78` |
| `vessels.json` | `/ais/candidates`, `/ais/tracks`, `/attribute`, `/attribute/ranked` | per-vessel `factors` (the seven attribution criteria) and AIS tracks |
| `hindcast_particles.json` | `/hindcast` | prerecorded backward particle ensemble |
| `forecast_polygons.geojson` | `/forecast` | 6/12/24/36/48h drift envelopes |
| `source_region.geojson`, `spill_polygon.geojson` | frontend fallback only | map polygons |
| `vessel_tracks.geojson` | frontend fallback only | precomputed copy of the tracks the backend derives from `vessels.json` |
| `source_probability_points.json` | **nothing — currently unreferenced** | kept for a future source-probability heatmap |

`attribution_score` is no longer taken from `vessels.json`; it is computed by
`services/vessel_attribution.score_from_factors()` from that file's `factors`.

## Relationship to the other data folders

- `data/simulation/` — the snapshot simulation, and the **input** to the coming
  ML pipeline. Not demo output. Never disabled by `DEMO_MODE`.
- `data/runtime/` — where computed results will be written once real mode works.
- `data/images/` — SAR imagery served at `/demo-images`.

## Duplication with the frontend

`frontend/public/demo-data/` holds byte-identical copies of most of these files.
That duplication is **required**: the browser cannot read `backend/data/`, and
`frontend/src/lib/api.ts` falls back to those copies when the API is unreachable.
If you edit a fixture here, copy it across, or the offline fallback will drift.
