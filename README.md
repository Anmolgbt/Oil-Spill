# OILTRACE

**SAR oil-spill tile classification, AIS behaviour screening, source reconstruction
and vessel risk planning in one assumption-explicit pipeline.**
Smart India Hackathon 2026 · Department of Computer Engineering and Technology,
MIT World Peace University, Pune.

> **Status: research prototype.** The models are evaluated on public data and the
> end-to-end incident is a constructed scenario. Nothing here is validated for
> operational spill attribution, legal action or navigation. See
> [Limitations](#limitations).

A fleet of vessels is watched by satellite. On every pass, a trained CNN checks each
vessel's SAR tile for oil. When it finds oil, the system:

1. bounds when the release happened;
2. back-projects where it probably started;
3. searches historic AIS around that place and time;
4. ranks the vessels that were nearby;
5. tests each of them against the observation;
6. projects where the oil goes next and which ships are heading into it.

Two trained models do the detection work. Everything between them (drift geometry,
the AIS search, ranking, the counterfactual and route avoidance) is a stated
calculation. **Nothing is hardcoded. Anything the models cannot produce is reported as
unavailable rather than estimated.**

The accompanying paper is in [`paper/`](paper/).

---

## Contents

- [Evidence levels](#evidence-levels)
- [Quickstart](#quickstart)
- [The problem statement, and where each part is answered](#the-problem-statement-and-where-each-part-is-answered)
- [The dashboard](#the-dashboard)
- [How a scan works](#how-a-scan-works)
- [Models](#models)
- [Drift: three vectors, and why](#drift-three-vectors-and-why)
- [Attribution: ranking, counterfactual, robustness](#attribution-ranking-counterfactual-robustness)
- [API](#api)
- [Repository](#repository)
- [Data provenance and licensing](#data-provenance-and-licensing)
- [Limitations](#limitations)
- [Testing and reproducibility](#testing-and-reproducibility)
- [Licence](#licence)

---

## Evidence levels

Each output belongs to one of four categories. They answer different questions and
need different kinds of validation, so they are never mixed:

| Level | Examples | What it can claim |
|---|---|---|
| **Measured** | CNN test metrics on 574 held-out tiles from 451 unseen scenes | Performance on that dataset and split |
| **Controlled** | AIS anomaly-injection test on 69 held-out vessels | Sensitivity to the injected patterns, not to real misconduct |
| **Rule-based** | Source estimate, drift envelope, forecast, ranking, priority score | Arithmetic on stated assumptions |
| **Constructed** | The 12-vessel incident on passes T1–T3 | That the pipeline runs end to end, not that it is accurate |

---

## Quickstart

Requires Python 3.10–3.13 and Node 18+.

```bash
# backend
cd backend
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn main:app --reload --port 8000
```

```bash
# frontend, in a second terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dashboard scans the newest pass on load, and the
**T1 / T2 / T3** buttons re-run any pass. **T1 and T2 are clear. T3 detects oil.**

`./run_demo.sh` starts both, and installs the frontend dependencies on first run.

The frontend talks to `http://localhost:8000` by default. To point it elsewhere, copy
`frontend/.env.example` to `frontend/.env` and set `VITE_API_URL`.

---

## The problem statement, and where each part is answered

> Detect and characterise the oil spill, calculating geometric properties and age
> if feasible.

`POST /fleet/scan` runs the CNN over every vessel in a pass. **Age is derived, not
assumed.** A tile that was clear on the previous pass and oily on this one holds oil
that is at most one revisit old, so the 4 h pass interval bounds the age. Geometric
properties are limited because the CNN is a classifier (see [Limitations](#limitations)).

> Using oceanographic and meteorological data, trace the slick towards the origin
> point and time, predict the future flow of the slick.

Each detection is back-projected along a drift vector to a probable source and release
window, then projected forward to +6, +12, +24 and +48 h. **No measured oceanographic or
meteorological data is loaded.** The drift uses stated values (current 0.25 m/s toward
170°, wind 5.0 m/s toward 200°, 3% windage), and both the API and the UI say so. A
gridded reanalysis can be added without any code change
([`backend/data/environment/PROVENANCE.md`](backend/data/environment/PROVENANCE.md)).

> Analyse and attribute the spill to a vessel using historic AIS data… filter out
> irrelevant traffic… score suspects on proximity, trajectory, behavioural anomalies.

AIS is searched within ±2 h of the estimated release time, clipped to a radius
**derived from the drift envelope**: three envelope radii, which is 16.7 km at a 4 h
age. That radius is the irrelevant-traffic filter, and it does real work: on the demo's
second detection it rejects 7 of 12 vessels. The remaining vessels are scored
`0.40 × proximity + 0.30 × trajectory + 0.30 × behaviour`, where behaviour is the trained
Isolation Forest's verdict on that vessel's track. **The dashboard shows each term, its
weight and the total**, so the score can be checked rather than trusted. The notebook's
flat 50 km radius is kept only for `/ai/investigate`, which reproduces that completed
single-scene case.

> A suitable visual interface.

A React + Leaflet dashboard. See [The dashboard](#the-dashboard).

---

## The dashboard

| Panel | What it shows |
|---|---|
| **Monitored fleet** | Pass selector (T1–T3), SAR upload for a new pass, and each vessel's CNN verdict and calibrated confidence. Confidences never round up to 100%: a value such as 0.99988 is shown as `>99.9%`. |
| **Monitoring map** | Vessel tracks, the oil-positive position, the estimated source, the drift envelope, forecast points and heatmaps, environment vectors and detour routes. A replay timeline runs from T1 to +48 h. |
| **Vessel detail** | The vessel's SAR tile, CNN result, suspect score, last AIS fix, and the current, wind and resultant drift at the spill. |
| **Top candidates** | The ranked vessels within the search radius. Each score is broken down into proximity, trajectory and behaviour with their weights. **Test source consistency** runs the counterfactual. |
| **Response priority** | Each live spill's relative triage score, its envelope and a recommended action. |
| **Recommended actions** | Investigate, alert, contain and verify. The ranking is presented as an investigation lead, never as grounds for detention. |
| **Vessels at risk** | Which vessels are projected to enter a risk zone within 6 h. **Optimize route** draws a simulated detour that requires navigation review. |
| **How this was derived** | The five investigation stages, each stating what it establishes and what it does not. |
| **Model info** | The model cards, built from the artifacts themselves. |
| **Report** | A printable record of the stages, score arithmetic, every counterfactual run (including the exculpatory ones), the evidence outcome and provenance. |

| Stage | Establishes | Does not establish |
|---|---|---|
| **Detection** | The CNN found an oil signature in a vessel's SAR tile. | A boundary, mask or area. It is a classifier, not a segmentation model. |
| **Characterization** | The previous pass was clear, so the oil is at most one pass interval old. | An age measured from the imagery. |
| **Hindcast** | A probable source and release window, traced back along a drift vector. | A source fixed by measured wind or current. |
| **AIS search** | Vessels near the estimated source in the estimated window. | Certainty, because the source and window are both estimates. |
| **Candidates** | A ranking on proximity, trajectory and behaviour. | Causation. A high score is a lead, not proof. |

---

## How a scan works

```
satellite pass (T1 / T2 / T3)
        │
        ├─ CNN over each vessel's SAR tile ─────── no oil anywhere? report CLEAR, stop
        │
        └─ oil found on one or more tiles (each detection handled separately)
                 ├─ age ≤ one pass interval (previous pass was clear)
                 ├─ hindcast along the drift vector → probable source + release window
                 ├─ AIS within ±2 h of release and within 3 × envelope radius of the source
                 ├─ Isolation Forest scores each remaining vessel's track
                 ├─ rank: 0.40 proximity + 0.30 trajectory + 0.30 behaviour
                 ├─ counterfactual + 7 × 7 drift-sensitivity sweep per candidate
                 ├─ forward projection at +6 / 12 / 24 / 48 h
                 ├─ forward risk: which vessels are projected to enter the zone
                 └─ detour geometry for each of them
```

Every flagged tile gets its own source, age, envelope, candidate list and response
priority. A spill found near a second ship is a second finding, not a footnote to the
first.

---

## Models

Full model cards: [`docs/MODELS.md`](docs/MODELS.md).

### Oil detection: `artifacts/oilspill_cnn_best.pth` + `cnn_config.json`

A custom **binary tile classifier** with 1,206,370 parameters. It has four blocks of
`Conv-BN-ReLU ×2 + MaxPool` (32→64→128→256 channels), global average pooling, and a
`Dropout(0.30)` MLP head. Preprocessing is grayscale, resize to 224², 3 channels and
`Normalize(0.5, 0.5)`. Output is `softmax(logits / 1.0286)`, and a tile is **oil when the
calibrated probability is ≥ 0.57**. The temperature and the threshold were both fitted on
the validation split.

Trained on the **CSIRO Sentinel-1 SAR oil/non-oil dataset**
([DOI 10.25919/4v55-dn16](https://doi.org/10.25919/4v55-dn16), CC BY-SA 4.0). After
removing 4 label conflicts and 90 exact duplicates, the split is **grouped by source
scene**, so no scene appears in more than one partition. Held-out test results (574
tiles, 451 scenes):

| Accuracy | Precision | Recall | F1 | Specificity | ROC-AUC | ECE |
|---|---|---|---|---|---|---|
| 96.34% | 94.33% | 94.82% | 94.57% | 97.11% | 0.9933 | 0.014 |

The confusion matrix is TN 370 · FP 11 · FN 10 · TP 183. The 95% scene-bootstrap
intervals (1,000 resamples) are 94.6–97.9% for accuracy and 90.7–98.1% for recall.
About one alarm in 18 is false and one spill in 19 is missed.

**Near-duplicate audit.** A perceptual-hash check (pHash, 8 orientations, Hamming
distance ≤ 8) finds 58 test tiles with a near-duplicate in training. Removing them gives
96.12% accuracy and 0.9930 ROC-AUC, so leakage does not explain the result
([`handoff/cnn/near_duplicate_report.json`](handoff/cnn/near_duplicate_report.json)).

**The demo is not a test.** The demo's tiles come from the same public dataset, so its
confident detections are not held-out evidence. Replaying the notebook's test split
through the backend reproduces the confusion matrix exactly.

CPU inference takes about 65 ms per tile on one core. A 12-vessel scan adds under a
second of model time.

### AIS behaviour: `artifacts/ais_anomaly_model.joblib`

`IsolationForest(n_estimators=300, contamination=0.02, random_state=42)` behind a
`StandardScaler`. It is trained on the 52,049 scoreable rows of the 52,943-record
reference corpus after cleaning.

The AIS "not available" codes (`SOG 102.3`, `COG 360`, `heading 511`) are **cleared, and
recovered from the position track** where possible. Tracks are split at gaps over 15 min.
The features are location-independent:

```
["sog", "accel_kn_per_min", "turn_rate_deg_per_min", "speed_mismatch_kn"]
```

The `anomaly_score` is calibrated to 0–100: 0 is the training median and 100 is the
training 99.5th percentile, using a fixed calibration stored with the model.
`behaviour_score` is the vessel's maximum over its track.

It is unsupervised. It was checked by injecting known unusual behaviour into 69 vessels
held out of fitting: ROC-AUC 0.993, 86.2% recall and a 0.9% false-flag rate. It has
**not** been checked against real violations.

---

## Drift: three vectors, and why

| Path | Vector | Used for | Code |
|---|---|---|---|
| Kinematic hindcast | 1.5 km/h → 135° | Source estimate, ranking, legacy counterfactual | `services/investigation.py` |
| Kinematic forecast | 1.0 km/h → 180° | +6/12/24/48 h positions | `services/investigation.py` |
| Environment-aware | 1.394 km/h → 181.2° (current + 3% windage) | Drift envelope, environment-aware source, ranking and counterfactual | `services/damage.py`, `services/drift.py` |

The two kinematic vectors are fixed scenario constants from the original notebook. The
environment-aware vector is derived from the stated current and wind. **They are kept
side by side on purpose.** Each scan reports how far apart they put things: 4.56 km at
the source, 2.37 / 4.75 / 9.49 / 18.98 km at the forecast horizons, and whether the
top-ranked vessel changes. That disagreement measures sensitivity to an assumption. It is
not forecast error. Each path is internally consistent: the counterfactual threshold
comes from the same vector that moves the oil, so a probe placed on the estimated source
returns a miss of 0.00 km.

Replacing the constants with a measured field is a data task, not a code task. See
[`PROVENANCE.md`](backend/data/environment/PROVENANCE.md).

---

## Attribution: ranking, counterfactual, robustness

**Ranking** (`0.40 P + 0.30 T + 0.30 B`). If the behaviour model cannot score a vessel,
the remaining two weights are renormalised. That vessel is flagged as scored on partial
evidence and is not given a silent zero.

**Counterfactual** (`POST /fleet/counterfactual`). It takes a candidate's **real AIS
position at the estimated release time**, runs the drift forward over the spill's age,
and reports the miss distance from where oil was seen. It is independent of the ranking,
and it does disagree with it. On the demo's first detection:

| Rank | Vessel | Score | Miss (threshold 6.00 km) | Robustness |
|---|---|---|---|---|
| 1 | Vessel K | 86.44 | 2.88 km, consistent | moderately sensitive |
| 2 | Vessel B | 73.45 | 4.37 km, consistent | moderately sensitive |
| 3 | Vessel H | 72.71 | 9.15 km, not consistent | robust |
| 4 | Vessel L | 68.79 | 3.82 km, consistent | moderately sensitive |

**Robustness.** Each verdict is re-run on a 7 × 7 grid of drift speed (±50%) and bearing
(±45°). The grid spans all three vectors above. The verdict is `robust` if at least 90%
of the 49 runs agree and `moderately sensitive` at 60–90%. Vessel K holds its verdict by
3.12 km under the kinematic drift but by only **0.06 km** under the environment-aware one.
Under that drift, **Vessel L ranks first instead of Vessel K**.

**Evidence outcome** (in the API and the report). Each detection gets exactly one outcome:

| Outcome | Means |
|---|---|
| `CANDIDATE_SUPPORTED` | A leader exists and holds across the assumptions tested |
| `LEADING_CANDIDATE_UNSTABLE` | A leader exists, but which vessel it is depends on an unmeasured assumption |
| `NO_STRONG_CANDIDATE` | The evidence does not support naming any vessel |

The demo produces the last two. On the second detection, all five candidates' own
counterfactuals rule them out, while the ranking still has a leader at 50.17/100. The
system therefore states that nobody is supported. Declining to name a vessel is a
statement about the evidence, never a finding that any vessel is innocent.

---

## API

| Method | Route | Purpose |
|---|---|---|
| POST | `/fleet/scan` | Scan a pass. `{"snapshot_id": "t1"}` is optional and defaults to the newest |
| POST | `/fleet/counterfactual` | Test one candidate against the observation |
| GET | `/fleet` | Monitored vessels and available passes |
| POST | `/fleet/passes` · GET `/fleet/passes/next` | Upload a new pass of SAR tiles |
| GET | `/fleet/t3-ground-truth-debug` | Internal: the seeded T3 assignment, for replay checking |
| GET | `/ai-result` · `/ai-result/raw` | Stored completed case, used as the dashboard's fallback |
| GET | `/ai-result/metrics` · `/ai-result/models` | CNN test metrics and artifact status |
| GET | `/ai/cnn/status` · POST `/ai/cnn/predict` | CNN status, or classify an uploaded image |
| GET | `/ai/ais/status` · POST `/ai/ais/predict` | Isolation Forest status, or score a track |
| POST | `/ai/investigate` · GET `/ai/investigate/defaults` | Single-scene run that reproduces the notebook's case |
| GET | `/api/models` | Model cards composed from the artifacts |
| GET | `/api/environment` | Current and wind at a lat/lon/time, with its mode and reason |
| GET | `/health` | Liveness |

Interactive docs are at http://localhost:8000/docs.

---

## Repository

```
├── backend/
│   ├── main.py                 API entrypoint
│   ├── core/config.py          paths and shared constants (drift inputs, weights)
│   ├── ml/                     CNN and AIS model adapters
│   ├── services/               fleet_pipeline, investigation, drift, environment,
│   │                           counterfactual, evidence, narrative, risk, reroute,
│   │                           damage, geo, ingest, snapshots, t3_simulation
│   ├── routes/                 fleet, cnn, ais, investigate, models, stored_result
│   ├── scripts/                fleet build, pseudonymisation, test-split replay,
│   │                           near-duplicate audit, paper figures, co-presence check
│   ├── tests/                  88 pytest tests
│   ├── artifacts/              trained model files
│   └── data/                   AIS corpus, demo fleet + passes, stored case
├── frontend/src/               React + Leaflet dashboard (App.tsx, components/, lib/)
├── handoff/                    training notebooks and their artifacts (cnn/, ais/, previous/)
├── paper/                      IEEE paper source, figures and the data behind them
├── docs/                       ARCHITECTURE.md, MODELS.md, DEMO.md
├── DATA_LICENSES.md            licences of the data (separate from the code licence)
└── LICENSE                     MIT (code)
```

The AIS corpus (5.3 MB) and the model artifacts (7.1 MB) are committed because the app
cannot run without them. The `handoff/` folder is the training provenance record and is
not read at runtime.

---

## Data provenance and licensing

| Data | Source | Status | Licence |
|---|---|---|---|
| SAR chips (training and demo) | CSIRO Sentinel-1 SAR oil/non-oil dataset, [10.25919/4v55-dn16](https://doi.org/10.25919/4v55-dn16) | Real imagery | **CC BY-SA 4.0** |
| `ais_dataset.csv` | MarineCadastre.gov (BOEM/NOAA) export, Gulf of Mexico, 31 Dec 2020 to 28 Mar 2021 | Real AIS | U.S. public data |
| Model weights | Trained by the OILTRACE team (`handoff/`) | Trained | MIT |
| `fleet.json`: 12 vessels | Tracks drawn from that corpus | Real tracks, **pseudonymised identities** | — |
| Vessel co-presence | Per-vessel constant time shift | Constructed | — |
| Which vessels show oil on T3 | Seeded draw over a pool of real chips | Simulated assignment | — |

Details and per-file attribution: [`DATA_LICENSES.md`](DATA_LICENSES.md).

**Pseudonymised vessels.** The demo ranks vessels as suspects for an incident that never
happened, so no real ship is named. The twelve vessels appear as **Vessel A–L** with
pseudo-MMSIs `999000001–999000012`. Their tracks, speeds, courses, types and dimensions
are real. `scripts/build_fleet.py` and `scripts/anonymise_fleet.py` apply the same
mapping.

**Constructed co-presence.** The corpus samples transits, not continuous surveillance.
Measured across all 88 days, the best window in which vessels have a fix at all three
passes, four hours apart, holds **3 of 347** vessels (`scripts/measure_copresence.py`).
Each demo vessel's timestamps are therefore shifted by a constant offset onto the shared
T1/T2/T3 clock. No position, speed or course is altered.

**Why the Gulf of Mexico.** No openly available AIS corpus carries Indian coastal traffic
at the density this method needs. The method is not region-specific: it takes SAR tiles,
AIS fixes and a drift assumption. The roadmap for Indian waters (Sentinel-1 over the
Arabian Sea, INCOIS currents, IMD winds, Indian Coast Guard workflows) is in the paper.

---

## Limitations

**No spill area, boundary, thickness or volume.** The CNN is a classifier. The
**drift envelope** (π r², 97.7 km² at 4 h) is the sea area the oil could have reached, not
the size of the slick.

**The CNN cannot geolocate.** The spill position is the vessel's AIS fix at that pass.

**No measured environmental data.** Drift uses stated inputs. A reanalysis would make it
physically informed, but not validated: no observed slick trajectory is used anywhere.

**Three drift vectors that disagree.** This is reported rather than hidden (see
[Drift](#drift-three-vectors-and-why)).

**Age is an upper bound** taken from the pass interval, not measured from imagery.

**The incident is constructed.** The vessels are time-shifted onto a shared clock, and the
T3 oil assignment is a seeded draw.

**Attribution is unvalidated.** There is no labelled spill-to-vessel dataset. The ranking
weights are set by hand. A score is an investigation lead and never proof.
`vessel_causation_proven: false` is carried throughout.

**The AIS model is unsupervised.** "Anomalous" means unusual, not wrong. Legitimate
manoeuvres and GPS errors can score high.

**The reroute is geometry, not navigation.** It ignores traffic separation, depth,
weather, vessel handling and COLREGs.

**Response priority is triage, not harm.** It excludes oil volume, shoreline, habitat and
cost.

**Map tiles.** The public OpenStreetMap and Esri tile endpoints are for light use only. A
deployment needs its own tile provider.

---

## Testing and reproducibility

```bash
cd backend && .venv/bin/python -m pytest        # 88 tests
cd frontend && npx tsc --noEmit                 # type check
```

The tests pin the properties that matter: counterfactual inverse closure to 0.00 km, the
seeded assignment, the ranking arithmetic and renormalisation, that `UNAVAILABLE` never
grades as `LOW`, both evidence outcomes, model loading and the environment fallback. They
do not cover visual regression, load testing or browsers other than Chromium.

Reproducing the paper's numbers and figures from the frozen artifacts (no retraining) is
covered in [`paper/README.md`](paper/README.md):

| Script | Output |
|---|---|
| `scripts/replay_cnn_test_split.py` | Reproduces TN/FP/FN/TP = 370/11/10/183 and writes per-tile probabilities |
| `scripts/check_near_duplicates.py` | `handoff/cnn/near_duplicate_report.json` |
| `scripts/make_paper_figures.py` | `paper/figures/*.pdf`, `paper/data/figure_numbers.json` |
| `scripts/measure_copresence.py` | The 3-of-347 co-presence ceiling |

---

## Further reading

- [`paper/`](paper/): the IEEE paper and how to build it
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): how the pieces fit together
- [`docs/MODELS.md`](docs/MODELS.md): model cards and preprocessing
- [`docs/DEMO.md`](docs/DEMO.md): presentation walkthrough
- [`handoff/README.md`](handoff/README.md): how the models were trained

## Licence

The code is MIT; see [`LICENSE`](LICENSE). The data keeps its own licence: the SAR chips
and anything derived from them are **CC BY-SA 4.0** (CSIRO), and the AIS data is U.S.
public data. See [`DATA_LICENSES.md`](DATA_LICENSES.md).
