# OILTRACE

**Satellite + AIS oil-spill monitoring and vessel attribution.**
Smart India Hackathon 2026.

A fleet of vessels is watched by satellite. Every pass, a trained CNN checks each
vessel's SAR tile for oil. When a spill is found, the system traces it back to a
probable source, searches historic AIS around that place and time, scores the
vessels that were nearby, and projects where the oil goes next.

Two trained models do the detection work. Everything between them — drift
geometry, the AIS search, the ranking — is computed. **Nothing is hardcoded, and
anything the models cannot produce is reported as unavailable rather than
estimated.**

---

## The problem statement, and where each part is answered

> Detect and characterise the oil spill, calculating geometric properties and age
> if feasible.

`POST /fleet/scan` runs the CNN over every vessel in the newest pass.
**Age is derived, not assumed**: a tile that was clear on the previous pass and
oily on this one holds oil at most one satellite revisit old, so the 8 h revisit
interval bounds it. Geometric properties are limited — see [Limitations](#limitations).

> Using oceanographic and meteorological data, trace the slick towards the origin
> point and time, predict the future flow of the slick.

Each detection is back-projected along a drift vector to a probable source and
release window, then projected forward at +6/12/24/48 h.
**No oceanographic or meteorological data is used** — the drift vector is a fixed
assumption. This is stated everywhere it appears, in the API and in the UI.

> Analyse and attribute the spill to a vessel using historic AIS data... filter
> out irrelevant traffic... score suspects on proximity, trajectory, behavioural
> anomalies.

AIS is searched ±2 h around the estimated release time and clipped to a 50 km
radius — that is the irrelevant-traffic filter. Survivors are scored
`0.40 × proximity + 0.30 × trajectory + 0.30 × behaviour`, where behaviour is the
trained Isolation Forest's own verdict on that vessel's track.

> A suitable visual interface.

React + Leaflet dashboard: fleet list, live map, per-vessel detail with its SAR
tile, and a leaderboard of vessels showing an oil signature.

---

## Quickstart

Requires Python 3.10+ and Node 18+.

```bash
# backend
cd backend
python3 -m venv .venv && .venv/bin/python -m pip install -r ../requirements.txt
.venv/bin/python -m uvicorn main:app --reload --port 8000
```

```bash
# frontend, in a second terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dashboard scans the newest pass on load; the
`PASS` buttons re-run any pass (T0 and T1 are clear, T2 detects).

`./run_demo.sh` starts both.

---

## How a scan works

```
newest satellite pass (t2)
        │
        ├─ CNN over each vessel's SAR tile ──────── no oil anywhere? report CLEAR, stop
        │
        └─ oil found on one or more vessels
                 │  each detection is treated separately
                 ├─ age  ≤ one revisit interval (previous pass was clear)
                 ├─ hindcast back along the drift vector → probable source
                 ├─ AIS ±2 h around the release time, within 50 km of the source
                 ├─ Isolation Forest scores each survivor's track
                 ├─ rank: 0.40 proximity + 0.30 trajectory + 0.30 behaviour
                 └─ forward projection at +6/12/24/48 h
```

Every flagged vessel gets its own source, age, envelope and suspect list — a spill
found near a second ship is a second finding, not a footnote to the first.

---

## Models

### Oil detection — `artifacts/oilspill_cnn.pth`

Custom CNN, **binary classifier**, 421,570 parameters.

```
Conv(3→32) → ReLU → MaxPool → Conv(32→64) → ReLU → MaxPool
Conv(64→128) → ReLU → MaxPool → Conv(128→256) → ReLU → AdaptiveAvgPool(1×1)
Flatten → Linear(256→128) → ReLU → Dropout(0.4) → Linear(128→2)
```

Preprocessing: `Resize(224×224)` → `Grayscale(3)` → `ToTensor` →
`Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])`.
Inference is `softmax` → `argmax`, confidence = probability of the predicted class.

Test set — 555 Sentinel-1 SAR images:

| Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| 89.91% | 97.78% | 71.35% | 82.50% | 93.20% |

Confusion matrix: TN 367 · FP 3 · FN 53 · TP 132.

High precision, moderate recall — it rarely cries wolf, but misses roughly one
spill in four. For monitoring, a missed spill costs more than a false alarm, so
this is the trade-off to be aware of.

CPU inference: ~5 ms per tile.

### AIS behaviour — `artifacts/ais_isolation_forest.pkl`

`IsolationForest(n_estimators=200, contamination=0.02, random_state=42)` with a
`StandardScaler` fitted over 52,596 AIS records.

Features, **in this exact order** (pinned by the scaler's `feature_names_in_`):

```
["SOG", "speed_change", "COG", "course_change", "time_gap_minutes"]
```

Scoring is point-level, then aggregated per vessel:
`anomaly_score = 100 × (max_raw − decision_function) / (max_raw − min_raw)`, and
`behaviour_score` is that vessel's maximum. The normalisation is **dataset-wide**,
which is why `backend/data/ais_reference/ais_dataset.csv` must ship with the app —
without it a single vessel cannot be placed on the same 0–100 scale.

---

## API

| Method | Route | Purpose |
|---|---|---|
| POST | `/fleet/scan` | Scan a pass. `{"snapshot_id": "t1"}` optional; defaults to newest |
| GET | `/fleet` | Monitored vessels and available passes |
| GET | `/ai-result` | Stored completed case — the dashboard's fallback |
| GET | `/ai-result/metrics` | CNN validation metrics |
| GET | `/ai/cnn/status` · POST `/ai/cnn/predict` | CNN status; classify an uploaded image |
| GET | `/ai/ais/status` · POST `/ai/ais/predict` | Isolation Forest status; score a track |
| POST | `/ai/investigate` | Single-scene run reproducing the notebook's completed case |

Interactive docs at http://localhost:8000/docs.

---

## Repository

```
├── backend/
│   ├── main.py                API entrypoint
│   ├── core/config.py         paths and shared constants
│   ├── ml/                    cnn_inference.py, ais_inference.py — the model adapters
│   ├── services/              fleet_pipeline, investigation, stored_result, snapshots, geo
│   ├── routes/                fleet, cnn, ais, stored_result, investigate
│   ├── scripts/build_fleet.py regenerates fleet.json and the clean passes
│   ├── artifacts/             trained model files
│   └── data/
│       ├── simulation/        fleet.json + snapshots/t0,t1,t2 (SAR tiles)
│       ├── ais_reference/     AIS corpus (required at runtime)
│       └── ai_output/         stored completed case + sample tiles
├── frontend/src/              App.tsx, styles.css, lib/oiltrace.ts
├── handoff/                   the Colab notebook and delivered artifacts, untouched
├── dataset/                   LADOS reference paper
└── docs/                      ARCHITECTURE.md, MODELS.md, DEMO.md
```

The repo is ~17 MB: the AIS corpus (5.3 MB), model weights (3 MB) and the handoff
folder (4.9 MB) are committed because the app cannot run without them.

---

## Data provenance

| Data | Source | Real or synthetic |
|---|---|---|
| SAR tiles in `snapshots/` | Public Sentinel-1 oil-spill dataset | **Real imagery** |
| CNN weights, Isolation Forest, scaler | Trained in the Colab notebook | **Real, trained** |
| `ais_dataset.csv` | US Gulf of Mexico AIS (MarineCadastre), 52,943 records | **Real AIS** |
| `fleet.json` — 5 Indian vessels, MMSIs, tracks | Generated for the demo AOI | **Synthetic** |
| Snapshot timestamps and 8 h revisit | Chosen for the demo | **Synthetic** |

**The monitored fleet is synthetic and this matters.** The bundled AIS corpus is
US Gulf traffic and contains no Indian-flag vessels (MMSI 419xxx), so an Indian
fleet could not be drawn from it. The five vessels, their MMSIs and their tracks
are invented for the Arabian Sea demo area. The CNN still classifies real SAR
imagery, and the Isolation Forest genuinely scores these tracks — the behaviour
scores are real model output over synthetic input, not hand-written numbers.

---

## Limitations

These are load-bearing. The interface states them wherever the affected value
appears.

**No spill area, boundary, thickness or volume.** The CNN is a *classifier*, not a
segmentation model. It outputs a class and a confidence and produces no mask, so
there is nothing to measure an area from. The dashboard shows a **search zone**
(the drift envelope, π r²) — that is the sea area the oil could have reached, not
the size of the slick. Getting a true slick area requires a segmentation model
that has not been trained.

**No environmental data.** Wind, current, wave and oil properties are all absent.
Hindcast and forecast are *kinematic projections* along a fixed assumed drift
vector (1.5 km/h for the hindcast, 1.0 km/h for the forecast). This is not drift
physics and must not be presented as such. The AI output itself carries
`requires_environmental_drift_data: true`.

**The CNN cannot geolocate.** A classifier returns no coordinates. The spill
position is taken from the vessel's last known AIS fix, which is an input, not a
model output.

**Age is an upper bound**, derived from the revisit interval — not measured from
the imagery, which encodes nothing about age.

**Ranking is analytical association, never proof.** A high score means a vessel
was near an *estimated* source during an *estimated* window and behaved unusually.
It does not establish that it caused the spill, and the system carries
`vessel_causation_proven: false` throughout.

**`course_change` is not circular** in the saved AIS model: 359° → 1° is recorded
as 358°, not 2°. This is reproduced deliberately, because the saved scaler was
fitted on those values — correcting it requires retraining. See
[`handoff/README.md`](handoff/README.md).

---

## Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the pieces fit together
- [`docs/MODELS.md`](docs/MODELS.md) — full model cards and preprocessing
- [`docs/DEMO.md`](docs/DEMO.md) — presentation walkthrough
- [`handoff/README.md`](handoff/README.md) — the delivered artifacts and notebook quirks
