# OILTRACE

**Satellite + AIS oil-spill detection, source reconstruction and vessel attribution.**
Smart India Hackathon 2026.

A fleet of vessels is watched by satellite. Every pass, a trained CNN checks each
vessel's SAR tile for oil. When a spill is found, the system reconstructs where
and when it probably started, searches historic AIS around that place and time,
ranks the vessels that were nearby, tests each of them against the observation,
and projects where the oil goes next.

Two trained models do the detection work. Everything between them — drift
geometry, the AIS search, the ranking, the counterfactual, the route avoidance —
is computed. **Nothing is hardcoded, and anything the models cannot produce is
reported as unavailable rather than estimated.**

**DETECT · RECONSTRUCT · EXPLAIN · RESPOND.**

---

## The problem statement, and where each part is answered

> Detect and characterise the oil spill, calculating geometric properties and age
> if feasible.

`POST /fleet/scan` runs the CNN over every vessel in the newest pass.
**Age is derived, not assumed**: a tile that was clear on the previous pass and
oily on this one holds oil at most one satellite revisit old, so the 4 h revisit
interval bounds it. Geometric properties are limited — see [Limitations](#limitations).

> Using oceanographic and meteorological data, trace the slick towards the origin
> point and time, predict the future flow of the slick.

Each detection is back-projected along a drift vector to a probable source and
release window, then projected forward at +6/12/24/48 h.
**No oceanographic or meteorological data is used** — the drift vectors are fixed
assumptions. This is stated everywhere it appears, in the API and in the UI.

> Analyse and attribute the spill to a vessel using historic AIS data... filter
> out irrelevant traffic... score suspects on proximity, trajectory, behavioural
> anomalies.

AIS is searched around the estimated release time and clipped to a radius
**derived from the drift envelope** — three envelope radii, or 16.7 km at a 4 h
revisit. That is the irrelevant-traffic filter, and it does real work: on the
demo's second detection it rejects 7 of 12 vessels. The notebook's flat 50 km is
kept only for `/ai/investigate`, which reproduces that completed case; over this
corpus's 21 × 38 km patch it admits every vessel that exists. Survivors are scored
`0.40 × proximity + 0.30 × trajectory + 0.30 × behaviour`, where behaviour is the
trained Isolation Forest's own verdict on that vessel's track. **The dashboard
shows all three terms, their weights and the arithmetic**, so the total can be
checked rather than trusted.

The funnel is shown on screen, because the filtering is the deliverable:
**347 vessels in the corpus → 12 monitored → 12 with AIS in the release window →
N within the radius → ranked.**

> A suitable visual interface.

React + Leaflet dashboard: a staged investigation, a fleet list, a live map, a
per-vessel detail panel with its SAR tile, a candidate ranking with score
breakdowns, a counterfactual test, a simulated reroute, an incident replay and a
printable report.

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

Open http://localhost:5173. The dashboard scans the newest pass on load; the
`PASS` buttons re-run any pass — **T1 and T2 are clear, T3 detects**.

`./run_demo.sh` starts both, and installs frontend dependencies on first run.

The frontend talks to `http://localhost:8000` by default. To point it elsewhere,
copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_URL`.

---

## The investigation

A detection is a fact. Everything after it is an inference, and the interface
keeps that distinction visible: the models run the moment a pass lands, so the
findings are all present at once, and each stage states what it establishes
*and* what it does not. **HOW THIS WAS DERIVED** in the investigation bar opens
the same five stages with their limits in full.

| Stage | Establishes | Does not |
|---|---|---|
| **DETECTION** | The CNN classified each vessel's SAR tile and found an oil signature. | A classifier, not a segmentation model — no mask, no boundary, no area. |
| **CHARACTERIZATION** | The previous pass was clear, so the oil is at most one revisit old. | An upper bound from the satellite cadence, not an age measured from imagery. |
| **HINDCAST** | Drift traced backwards to a probable source and release window. | Kinematic, along an assumed vector. No wind, current or wave feed. |
| **AIS SEARCH** | Historic AIS searched around the release time, clipped to the radius. | Filters against an *estimated* source and window — both carry the hindcast's error. |
| **CANDIDATES** | Vessels scored on proximity, trajectory and behaviour. | Analytical association only. Plausibly present, never causal. |

Findings appear as their stage is reached; the map never shows an estimated
source before the hindcast that produced it has been run.

### Why this vessel?

Each candidate's score is shown taken apart — the raw 0–100 term, the weight
applied, and the points it contributes — followed by the arithmetic and the
total. A `null` behaviour score (the Isolation Forest declining to answer) is
drawn as a hatched bar and stated in words, because a term that scored nothing
for want of a verdict must not look like one that genuinely scored zero.

### What if this vessel caused the spill?

`POST /fleet/counterfactual` takes a candidate's **real AIS position at the
estimated release time**, runs drift forward over the spill's age, and reports
how far that lands from where oil was actually seen.

It returns a distance, not a verdict, and the interface states an exculpatory
result as plainly as a corroborating one — consistency is amber, ruling a vessel
out is green, because "not consistent" is a successful test.

**It is independent of the ranking, and it does disagree with it.** On the
demo's first detection the ranking puts MR CANOPUS top at 81.87, and its oil
*would* have reached the slick — 2.88 km, inside the 6.00 km that drift could
have carried it. But third-ranked GRAND DOLPHIN (78.91) misses by 9.72 km and is
ruled out, while sixth-ranked ACHILLEAS (70.38) lands 3.82 km away and is not.
Rank order and consistency are answering different questions, and the interface
shows both rather than reconciling them.

The threshold is what *that* drift could have carried oil in the estimated time
— 1.5 km/h over 4 h — not the map's 5.58 km affected-area circle, which is sized
by a different vector and answers "how far could the oil have reached at all".

### How robust is that answer?

The drift vector behind every one of those numbers is a stated constant that
nobody measured, so each counterfactual also reports **how far that assumption
can move before the verdict flips** — a 7 × 7 sweep of drift speed and bearing,
reported as `robust` / `moderately sensitive` / `highly sensitive` with the
margin. It is a sensitivity to an assumption, not an accuracy: the sweep is a
deterministic grid over a band chosen by hand, and the payload says so.

Measured on the demo, the pattern is itself a finding: exculpatory verdicts are
mostly robust, and every consistent verdict is sensitive. MR CANOPUS holds its
verdict by 3.12 km under the shipped drift and by **0.06 km** under the
environment-derived one.

### What the drift assumption changes

The system carries three drift vectors — hindcast 1.5 km/h @ 135°, forecast
1.0 @ 180°, and the envelope's current-plus-windage 1.394 @ 181.2° — and they
disagree. The **DRIFT ASSUMPTION** strip measures it: the estimated source moves
**4.56 km**, the forecast horizons **2.37 / 4.75 / 9.49 / 18.98 km**, and
re-ranking the same fleet against the environment-aware source **changes which
vessel is first** (MR CANOPUS → NISALAH).

No environmental data is involved in any of that. It is the constants
disagreeing with each other, and the panel says so twice so it cannot be read
the other way.

### Evidence quality, and refusing to answer

Each candidate's evidence is graded per stream — AIS coverage, trajectory,
behaviour, environmental coverage, counterfactual robustness — on one axis:
**how much that stream can tell us**, never how guilty it says the vessel is.
That is why `UNAVAILABLE` is styled apart from `LOW` rather than below it: a
model that could not answer is not evidence a vessel behaved normally.

Each detection then gets one of three outcomes:

| Outcome | Means |
|---|---|
| `CANDIDATE_SUPPORTED` | A leader exists and holds across the assumptions tested |
| `LEADING_CANDIDATE_UNSTABLE` | A leader exists, but which vessel it is depends on an unmeasured constant |
| `NO_STRONG_CANDIDATE` | The evidence does not support naming any of them |

**The shipped demo produces the last two.** On the second detection all five
candidates are robustly ruled out by their own counterfactuals while the ranking
still shows a leader at 70.54/100 — so the system states that nobody is
supported, keeps the ranked list visible with its scores, and explains why that
number is not support. Declining to name a vessel is a statement about evidence,
never a finding that any vessel is innocent.

Below each candidate, **IN PLAIN TERMS** reads the same evidence back as
sentences, with missing evidence marked as prominently as supporting evidence.

### Environmental data

`services/environment.py` answers "what were the current and wind here, then?"
behind a provider interface, and always reports `environment_mode` —
`historical` or `fallback` — with a reason. **No dataset is committed**, so the
shipped answer is `fallback` and every drift figure is a stated constant. The
system runs fully without one; adding one is dropping a CSV into
`backend/data/environment/` and filling in its `PROVENANCE.md`, with no code
change. The region, window and variables a dataset must cover are written there.

### A guided run

Press **DEMO**, or open `?demo=1`, for a thirteen-step walkthrough from the
satellite pass to the report. It scrolls to and outlines the real panels rather
than duplicating them, every line of its text is drawn from what the panel
already says, and it visits **both** detections — including the one where the
system declines to name anyone.

### Respond

**OPTIMIZE ROUTE** turns the precomputed detour into a decision someone takes: an
at-risk vessel holds course until asked, then shows heading and distance before
and after, whether the route clears the zone, and the detour drawn on the map.

**REPLAY INCIDENT** animates the whole story on one timeline — vessels along
their real AIS tracks, the slick appearing at the detection, the forecast
unrolling past it. Four bands, never merged: `before`, `estimated` (hindcast),
`observed` (the one measured moment) and `projected`. A vessel past its last AIS
fix renders hollow; the slick renders dashed unless it is the measured pass.

**GENERATE REPORT** produces a printable document carrying the stages and their
limits, the full score arithmetic, every counterfactual that was run *including
the exculpatory ones*, the reroute if one was requested, and provenance.

---

## How a scan works

```
newest satellite pass (t3)
        │
        ├─ CNN over each vessel's SAR tile ──────── no oil anywhere? report CLEAR, stop
        │
        └─ oil found on one or more vessels
                 │  each detection is treated separately
                 ├─ age  ≤ one revisit interval (previous pass was clear)
                 ├─ hindcast back along the drift vector → probable source
                 ├─ AIS around the release time, within 50 km of the source
                 ├─ Isolation Forest scores each survivor's track
                 ├─ rank: 0.40 proximity + 0.30 trajectory + 0.30 behaviour
                 ├─ forward projection at +6/12/24/48 h
                 ├─ forward risk: which vessels are projected to enter the area
                 └─ detour geometry for each of them
```

Every flagged vessel gets its own source, age, envelope, suspect list and
response priority — a spill found near a second ship is a second finding, not a
footnote to the first.

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

## Drift: three vectors, and why

The repo carries three different drift assumptions. They are not
interchangeable, and the distinction is load-bearing:

| Used for | Vector | Where |
|---|---|---|
| Hindcast (spill → source) | 1.5 km/h toward 135° | `services/investigation.py` |
| Forecast (spill → +48 h) | 1.0 km/h toward 180° | `services/investigation.py` |
| Impact envelope | ~1.39 km/h toward 181° (current + 3% windage) | `services/damage.py` |

The counterfactual **must** use the hindcast's vector, run forward. It is the
inverse of the source estimate, so only that vector can answer the question: with
any other, a vessel sitting exactly on the estimated source would fail to
reproduce the observation and every result would be noise. It also mirrors the
hindcast's flat-earth arithmetic rather than the spherical `destination()`, so the
inverse closes exactly — a probe placed on the estimated source returns a miss of
0.00 km.

Unifying the three into one physically-motivated vector is real work that has not
been done.

---

## API

| Method | Route | Purpose |
|---|---|---|
| POST | `/fleet/scan` | Scan a pass. `{"snapshot_id": "t1"}` optional; defaults to newest |
| POST | `/fleet/counterfactual` | Test one candidate against the observation |
| GET | `/fleet` | Monitored vessels and available passes |
| GET | `/fleet/t3-ground-truth-debug` | Internal: the seeded t3 assignment, for replay checking |
| GET | `/ai-result` · `/ai-result/raw` | Stored completed case — the dashboard's fallback |
| GET | `/ai-result/metrics` · `/ai-result/models` | CNN validation metrics; artifact status |
| GET | `/ai/cnn/status` · POST `/ai/cnn/predict` | CNN status; classify an uploaded image |
| GET | `/ai/ais/status` · POST `/ai/ais/predict` | Isolation Forest status; score a track |
| POST | `/ai/investigate` · GET `/ai/investigate/defaults` | Single-scene run reproducing the notebook's case |
| GET | `/api/models` | What the models are, composed from the artifacts themselves |
| GET | `/api/environment` | Current and wind at a lat/lon/time, with its mode and reason |
| GET | `/health` | Liveness |

Interactive docs at http://localhost:8000/docs.

---

## Repository

```
├── backend/
│   ├── main.py                API entrypoint
│   ├── core/config.py         paths and shared constants
│   ├── ml/                    cnn_inference.py, ais_inference.py — the model adapters
│   ├── services/              fleet_pipeline, investigation, counterfactual, risk,
│   │                          reroute, damage, snapshots, stored_result, geo
│   ├── routes/                fleet, cnn, ais, stored_result, investigate
│   ├── scripts/build_fleet.py regenerates fleet.json and the clean passes
│   ├── artifacts/             trained model files
│   └── data/
│       ├── simulation/        fleet.json + snapshots/t1,t2,t3 (SAR tiles)
│       ├── ais_reference/     AIS corpus (required at runtime)
│       └── ai_output/         stored completed case + sample tiles
├── frontend/src/
│   ├── App.tsx                dashboard state and layout
│   ├── components/            MapView, InvestigationBar, WhyThisVessel, ReportModal
│   ├── lib/                   oiltrace.ts (data access), replay.ts (timeline maths)
│   ├── types.ts               scan payload shapes
│   ├── stages.ts              the five investigation stages
│   ├── ui.tsx                 Card, Badge, ScoreBar
│   └── mapColours.ts          overlay colours, named by role
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
| `fleet.json` — 12 vessels, MMSIs, tracks | Drawn from that corpus | **Real AIS vessels** |
| Vessel **co-presence** | Constructed by a per-vessel time shift | **Scheduling artefact** |
| Which vessels show oil on t3 | Seeded draw over a real tile pool | **Simulated assignment** |
| Snapshot timestamps and 4 h revisit | Chosen for the demo | **Synthetic cadence** |

### What is real, and what is constructed

The vessels are real — twelve of them, with their real MMSIs and their real
tracks, taken from the MarineCadastre corpus. Four are recorded without a name
and appear as `VESSEL <MMSI>`, which is what the corpus actually knows about
them.

**Their co-presence is constructed, and this matters.** Each vessel's own
timestamps are shifted by a constant offset onto the shared t1/t2/t3 clock so
the fleet can be observed together. No position, speed or course is altered —
only when the fixes are said to have happened.

This is necessary because **the corpus samples transits, not continuous
surveillance**. A vessel typically appears for one to two hours and leaves.

The question has to be asked precisely, because looser versions of it give
flattering answers. What the demo actually needs is a vessel placeable on the
map at *each* of three passes four hours apart. Measured across the whole 88-day
corpus, the best such window anywhere holds **3 vessels of 347** — against the
12 this demo shows. In the shipped window it is **zero**. Reproduce it with
`python backend/scripts/measure_copresence.py`.

Unshifted, ten of these twelve vessels would not yet have arrived at t1, and
eleven of twelve would be up to 7.7 h stale at t3. So the shift is a limit of
the data, not a shortcut around the work — and the interface states it where the
method is explained rather than leaving it in a data file.

### Why the Gulf of Mexico, in an India-facing round

**No openly available AIS corpus carries Indian-flag traffic at the density this
method needs**, and an earlier version of this repo that invented an Indian fleet
had to label every vessel synthetic.
Choosing real data over a more flattering map was deliberate.

Nothing in the method is region-specific. The pipeline takes SAR tiles, AIS
fixes and a drift assumption; pointed at Indian coastal AIS it would run
unchanged. What the demo shows is the method working on real traffic, not a claim
about the Gulf of Mexico.

The **oil/no-oil assignment for t3 is simulated** — a seeded draw over a pool of
real SAR tiles, made before any model runs and never shown to the CNN. The
model's call on those tiles is a real prediction, checkable afterwards against
`t3_ground_truth.json`.

---

## Limitations

These are load-bearing. The interface states them wherever the affected value
appears.

**No spill area, boundary, thickness or volume.** The CNN is a *classifier*, not a
segmentation model. It outputs a class and a confidence and produces no mask, so
there is nothing to measure an area from. The dashboard shows a **drift
envelope** (π r²) — that is the sea area the oil could have reached, not the size
of the slick. Getting a true slick area requires a segmentation model that has
not been trained.

**No environmental dataset is loaded.** There is a service for one
(`services/environment.py`) and every answer carries its mode, but nothing is
committed, so the shipped mode is `fallback`: wind and current are **stated
constants**, not measurements, and the interface says so wherever a drift figure
appears. Hindcast, forecast and envelope are *kinematic projections* along
assumed vectors. Loading a real reanalysis would make them physically informed —
not validated, since a reanalysis is a model output too.

**The three drift vectors disagree, and nothing resolves them.** Hindcast
1.5 km/h @ 135°, forecast 1.0 @ 180°, envelope 1.394 @ 181.2°. The system
measures the disagreement (4.56 km at the source, up to 18.98 km at +48 h, and
a change in which vessel ranks first) and reports it rather than picking one.
Unifying them is real work that has not been done.

**The CNN cannot geolocate.** A classifier returns no coordinates. The spill
position is taken from the vessel's last known AIS fix, which is an input, not a
model output.

**Age is an upper bound**, derived from the revisit interval — not measured from
the imagery, which encodes nothing about age.

**Vessel co-presence is constructed.** The corpus samples transits rather than
tracking continuously, so the twelve vessels are shifted onto a shared clock to
be observed together. Positions are real; simultaneity is not. The ceiling is
measured, not assumed: **3 vessels of 347** in the best three-pass window
anywhere in the corpus. See [Data provenance](#data-provenance).

**Ranking is analytical association, never proof.** A high score means a vessel
was near an *estimated* source during an *estimated* window and behaved unusually.
It does not establish that it caused the spill, and the system carries
`vessel_causation_proven: false` throughout.

**The counterfactual inherits what it tests against.** It uses the hindcast's own
drift vector, so it checks whether a vessel's real position is consistent with the
observation *under that assumption* — it cannot check the assumption itself. What
it can do, and does, is measure how far that assumption must move before the
verdict flips.

**Attribution is unvalidated.** There is no labelled spill-to-vessel dataset, so
neither the ranking nor either counterfactual mode has ever been checked against
a known answer. The seeded t3 assignment validates *detection* against a
simulated scenario; it is not attribution ground truth.

**The reroute is a geometry demo, not navigation guidance.** It routes around a
buffered circle with no regard for traffic separation schemes, depth, weather,
vessel handling or COLREGs.

**Response priority is not a measure of harm.** It ranks spills against each other
for response order, and excludes shoreline proximity, habitat sensitivity, oil
volume and cost. No response assets, crews or arrival times are modelled.

**`course_change` is not circular** in the saved AIS model: 359° → 1° is recorded
as 358°, not 2°. This is reproduced deliberately, because the saved scaler was
fitted on those values — correcting it requires retraining. See
[`handoff/README.md`](handoff/README.md).

**Test coverage is behavioural, not exhaustive.** 73 backend tests
(`backend/tests/`) pin the properties that matter — counterfactual inverse
closure to 0.00 km within 10 m, the seeded assignment, the attribution
arithmetic, `UNAVAILABLE` never grading as `LOW`, both detection outcomes — plus
20 Playwright driver scripts over the real interface. What is *not* covered:
layout and visual regression, load and concurrency, and any browser other than
Chromium.

---

## Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the pieces fit together
- [`docs/MODELS.md`](docs/MODELS.md) — full model cards and preprocessing
- [`docs/DEMO.md`](docs/DEMO.md) — presentation walkthrough
- [`handoff/README.md`](handoff/README.md) — the delivered artifacts and notebook quirks

## Licence

MIT — see [`LICENSE`](LICENSE).
