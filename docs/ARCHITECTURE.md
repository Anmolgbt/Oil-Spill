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
  ├── services/damage.py              drift vector, impact envelope, response priority
  ├── services/environment.py         current/wind at a point in time; historical or fallback
  ├── services/drift.py               integrates a slick through that field, both directions
  ├── services/evidence.py            per-stream grades, and whether anyone is supported
  ├── services/narrative.py           the same evidence, read back in sentences
  ├── services/risk.py                which vessels are projected to enter the area
  ├── services/reroute.py             tangent-arc-tangent detour around the zone
  ├── ml/ais_inference.py             score each track for anomalous behaviour
  │       ├── artifacts/ais_isolation_forest.pkl
  │       ├── artifacts/ais_scaler.pkl
  │       └── data/ais_reference/ais_dataset.csv   (normalisation corpus)
  └── services/geo.py                 haversine, bearings, destination points
  ▼
one JSON payload → frontend/src/lib/oiltrace.ts → App.tsx
```

A second, much smaller path answers the counterfactual:

```
  POST /fleet/counterfactual  {mmsi, release_at, spill lat/lon, age_hours, ...}
  ▼
routes/fleet.py → services/counterfactual.py
  └── services/geo.py + the hindcast's drift constants
```

It takes its figures explicitly rather than a `snapshot_id`, because it is pure
geometry over AIS the fleet already holds — re-deriving from a pass would put the
CNN over every vessel again to answer a question no model is involved in.

## Module responsibilities

| Module | Owns |
|---|---|
| `services/fleet_pipeline.py` | The 7 steps and their order. The only module that knows the sequence. |
| `services/investigation.py` | Drift arithmetic and scoring weights, shared with the single-scene `/ai/investigate` path. |
| `services/snapshots.py` | Pass discovery. Sorts `t0…t10` numerically, so dropping in a `t4` folder needs no code change. |
| `services/stored_result.py` | Adapts the stored Colab result into the same shape a live scan returns. |
| `services/damage.py` | The assumed drift vector, the impact envelope, and the 0-100 response-priority triage score. |
| `services/environment.py` | Current and wind at a lat/lon/time, from a committed historical grid or the stated assumptions. Owns the current + windage vector sum that `damage.py` calls. |
| `services/drift.py` | Environment-aware hindcast and forecast by integration, and the closure check that keeps the counterfactual meaningful. Does not replace the legacy vectors. |
| `services/evidence.py` | Grades each evidence stream by what it can tell us, and decides whether any candidate is supported. Reads the ranking; never changes it. |
| `services/narrative.py` | The plain-language reading of one candidate, built from the grades. Backend-side so there is one place to correct the wording. |
| `services/risk.py` | Forward risk: projected tracks against the spill polygons, via shapely. |
| `services/reroute.py` | Detour geometry. Four candidate routes, shortest valid one wins. |
| `services/counterfactual.py` | The inverse of the hindcast, run per candidate. |
| `services/geo.py` | Pure geometry. No domain knowledge. |
| `ml/cnn_inference.py` | Architecture, preprocessing and inference, reproduced from the notebook. |
| `ml/ais_inference.py` | Feature engineering, scaler, Isolation Forest, corpus normalisation. |

## Two things worth understanding

**Age comes from the revisit interval, not an assumption.** If a vessel's tile was
clear at t2 and oily at t3, the oil appeared between those passes. The 4 h
interval is therefore an upper bound on its age, and it also sets the hindcast
window. This is a real inference from monitoring cadence — the imagery itself
encodes nothing about age.

**One haversine, three deliberate flat-earth approximations.**
`services/geo.py` owns all of it. `investigation.py` used to carry a second
haversine at R = 6371.0 for notebook fidelity; measured across the coordinates
this pipeline actually uses the two agreed to within **0.2 m over 148 km**
(1.4 ppm, entirely the radius — the atan2 and asin forms are mathematically
identical), so it is gone and every distance now comes from one function.
Verified: the notebook path's candidate scores and distances are unchanged.

The flat approximations stay separate because they are not interchangeable:
`KM_PER_DEG_LAT_WGS84`/`km_per_deg_lon()` keep `risk.py` and `reroute.py`
consistent with the planar circles they draw in shapely, while
`KM_PER_DEG_NOTEBOOK` (1/111) is what the hindcast uses — and
`counterfactual.py` mirrors it exactly so forward-then-backward closes to
**0.00 km**. `backend/tests/test_counterfactual.py` asserts that closure to
0.01 km at three spill ages; the tolerance is tight on purpose, because the two
sides run the identical formula with the sign reversed, so the residual should
be floating-point noise rather than approximation error.

**The search radius is derived, not chosen.** `fleet_search_radius_km()` in
`services/investigation.py` returns three drift-envelope radii — 16.74 km at a
4 h revisit. The notebook's flat `MAX_DISTANCE_KM = 50` is kept for
`/ai/investigate`, which reproduces that completed case, but over this corpus's
21 × 38 km patch it admits every vessel that exists, so the fleet path cannot
use it. The radius is also the proximity denominator (`100 × (1 − d / radius)`),
so a 50 km denominator compressed every vessel into the top of the score range.
`/fleet/scan` reports the resulting funnel per detection.

**Vessel co-presence is constructed.** The corpus samples transits rather than
tracking continuously: a vessel appears for one to two hours and leaves. Asked
precisely — a fix within 30 minutes of *each* of three passes four hours apart —
the best window in the whole 88-day corpus holds **3 vessels of 347**, and the
shipped window holds none (`scripts/measure_copresence.py`). Looser phrasings
mislead: counting min/max spans gives 55, counting fixes-in-window gives 12, and
counting overlaps in `fleet.json` gives 12 because that file is the shifted
output and the question is circular.
`build_fleet.py` therefore shifts each vessel's timestamps by a constant offset
onto the shared t1/t2/t3 clock. Positions, speeds and courses are untouched.
Unshifted, ten of the twelve vessels would not have arrived by t1 and eleven
would be up to 7.7 h stale at t3.

**No environmental dataset is committed, and the app says so.**
`services/environment.py` answers "what were the current and wind here, then?"
behind a provider interface, and reports `environment_mode: "historical"` or
`"fallback"` with a reason. With no dataset present — the shipped state — every
answer is `fallback` and comes from the four constants in `core/config.py`
(current 0.25 m/s toward 170°, wind 5.0 m/s toward 200°, 3% windage). Adding one
is dropping a CSV into `backend/data/environment/` and filling in
`PROVENANCE.md`; no code changes. The service refuses to extrapolate past a
dataset's coverage, falls back instead, and never blends a measured current with
an assumed wind into something it calls historical.

The current + windage vector sum lives in `environment.py` and
`damage.drift_vector()` calls it, so a historical drift and an assumed one
cannot be computed two different ways.

**Three drift vectors coexist, and they are not interchangeable.** The hindcast
uses 1.5 km/h toward 135°, the forecast 1.0 km/h toward 180°, and the impact
envelope the assumed current plus 3% windage (1.394 km/h toward 181.2°). The
counterfactual must use the hindcast's, run forward, or it is not the inverse of
the source estimate it is testing against — with any other vector a vessel
sitting exactly on the estimated source would fail to reproduce the observation.
Unifying the three is real work that has not been done.

**How far apart they actually are, measured.** `services/drift.py` integrates
the same question through the environment service's vector — the one the stated
wind and current imply — and the scan reports the gap as `drift_divergence`. On
the t3 case the estimated source lands **4.56 km** from the legacy one, and the
forecast horizons **2.37 / 4.75 / 9.49 / 18.98 km** apart at +6/12/24/48 h. No
environmental data is involved in that: it is entirely the three constants
disagreeing with each other. It is a disagreement between assumptions, not a
measurement of anyone's error, and neither estimate is validated.

**The system can decline to name a vessel, and on the shipped demo it does.**
`services/evidence.py` grades five streams per candidate — AIS coverage,
trajectory, behaviour, environmental coverage, counterfactual robustness — on one
axis: **how much this stream can tell us**, not how guilty it says the vessel is.
That is the only reading under which UNAVAILABLE is not LOW, and it is what stops
the layer becoming a second suspicion score. A behaviour model that ran and found
nothing is HIGH-quality evidence of normality; one that could not run is
UNAVAILABLE. Every grade ships the threshold rule that produced it.

Three detection outcomes, and t3 produces two of them:

- **`NO_STRONG_CANDIDATE`** on the GRAND DOLPHIN detection. All five candidates'
  counterfactuals robustly say they could not have been the source, while the
  ranking still shows a leader at **70.54/100**. The banner says nobody is
  supported and explains why that score does not amount to support; the ranked
  list stays below it with scores intact.
- **`LEADING_CANDIDATE_UNSTABLE`** on the NISALAH detection. Three candidates are
  consistent, but which one leads changes with the drift assumption and the
  leader's verdict holds by 0.06 km under the environment-aware drift.
- `CANDIDATE_SUPPORTED` otherwise.

Declining to name a vessel is a statement about evidence, never a finding that
any vessel is innocent, and the payload says so in `assessment.means`.

**The explanation is prose, and it is generated backend-side.**
`services/narrative.py` reads the graded streams back as ordered beats, each
toned `supports` / `weakens` / `missing` / `neutral`. Two rules shape it:

- **Beats are built from the grades, never from raw fields.** An UNAVAILABLE
  stream therefore *changes its sentence* rather than losing it. Omission is the
  easiest way to lose the rule that UNAVAILABLE is not LOW — a narrative that
  simply says nothing about the environment reads as though the environment were
  fine. A test asserts this by removing streams, not by inspection.
- **The opening is set by the detection outcome, not the rank.** On the
  `NO_STRONG_CANDIDATE` detection, opening "Ranked #1 because…" for GRAND DOLPHIN
  would be the accusation the system declined to make one panel earlier. There it
  opens: *"ranks #1 … but on this detection no vessel's oil could have reached
  where oil was actually seen, this one included."*

It lives in the backend for the same reason the model statements and the grade
reasons do — one place to correct the wording — and so Phase 19's report reuses
the sentences rather than restating them.

**The drift assumption changes who is ranked first, and the app says so.**
`drift_divergence.ranking_change` re-runs the existing `rank_fleet()` against
the environment-aware source — same fleet, same search radius, same behaviour
scores, only the estimated source moves. On the t3 case the first detection's
top candidate changes (**MR CANOPUS #1 → #3, NISALAH #2 → #1, ACHILLEAS
#6 → #2**) while the second detection's does not (GRAND DOLPHIN stays #1). The
DRIFT ASSUMPTION strip headlines that, framed as a sensitivity of the
attribution to an assumption nobody measured — the same class of thing the
per-candidate robustness line reports — rather than as a fault. The shipped
ranking is the legacy one; the comparison is parallel and a test pins that the
real candidate list is untouched by it.

**Both drift paths are computed; only the legacy one drives anything.**
`spills[].source` / `.forecast` are the legacy fixed-vector estimates and still
feed the search radius, the candidates, the counterfactual and the risk
polygons. `spills[].source_environmental` / `.forecast_environmental` are the
integrated versions, reported alongside so the difference can be shown without
changing a single downstream figure.

**Closure survives a varying field, because the backward step is implicit.**
The counterfactual only means something if the forward run is the exact inverse
of the backward one. With one constant vector that is exact arithmetic; with a
varying field it is a property of the integration scheme. The naive explicit
backward step does not close — measured against the synthetic test grid it left
**1.28 km at 4 h, identically at 60-minute and 1-minute steps**, so it was
structural rather than something finer resolution would fix. `drift.integrate()`
solves the backward step by fixed-point iteration instead, making it the inverse
of the forward step by construction; the residual is then **0.0 km** at every
step size tested. In fallback it is 0.0001 km (10 cm), from each run holding
cos(lat) at its own start latitude — two orders of magnitude inside the
counterfactual's 10 m tolerance. `drift.closure_residual_km()` keeps checking it
rather than trusting it.

**The AIS corpus is required at runtime.** The notebook normalises anomaly scores
against dataset-wide min/max of `decision_function`. A single vessel's track
cannot be placed on that 0–100 scale in isolation, so the corpus ships with the
app and is scored once, at startup.

`main.py` warms the models and the corpus in a FastAPI startup hook, so the
~2.1 s of corpus scoring is paid while uvicorn is booting rather than by whoever
triggers the first scan. Measured on this machine, before and after that change
plus de-duplicating the corpus work:

| | before | after |
|---|---|---|
| first detecting scan | 5.55 s | **1.24 s** |
| subsequent detecting scan | 0.83 s | 0.72 s |
| clear pass | 0.25 s | 0.26 s |

Two things were doing the same work twice. `_reference_normalisation()` and
`scored_corpus()` each read the same 5.3 MB CSV, ran `build_features()` over it
and called `decision_function()` on all 52,596 rows, into two separate caches —
the normalisation is now derived from the scored corpus, which contains exactly
those values. And `rank_fleet()` called `predict_track()` once per vessel *per
detection*; a vessel's track is the same track whichever spill it is ranked
against, so behaviour is now scored once per scan by
`score_fleet_behaviour()`.

## Fallback chain

The dashboard degrades rather than failing:

1. `POST /fleet/scan` — both models run now. Badge: **LIVE INFERENCE**
2. `GET /ai-result` — the stored completed case. Badge: **STORED RESULT**
3. `/ai-data/oiltrace_ai_output_final.json` — same output bundled with the frontend

The badge always names the tier in use. A stored result is never presented as a
live one.

## Frontend

`App.tsx` holds dashboard state and layout; everything else lives in its own
module:

| File | Owns |
|---|---|
| `components/MapView.tsx` | The Leaflet map and every overlay, docked or full-window. |
| `components/EnvironmentLayer.tsx` | The drift field, as arrows. Off by default; badged uniform when no dataset is loaded. |
| `components/DriftComparison.tsx` | Legacy vs environment-aware: source, forecast horizons, the three vectors, and the ranking change. |
| `components/EvidenceQuality.tsx` | Per-candidate stream grades, each with the rule that produced it. |
| `components/OutcomeBanner.tsx` | Whether the evidence supports naming anyone, stated above the ranking. |
| `components/CandidateNarrative.tsx` | Renders the backend's beats; a `missing` beat is styled as prominently as a supporting one. |
| `components/CounterfactualLines.tsx` | The mode-comparison and robustness lines, moved out of `WhyThisVessel.tsx`. |
| `components/DemoMode.tsx` | The thirteen-step guided run. Scrolls to and outlines real panels; duplicates none of them. |
| `components/InvestigationBar.tsx` | The five stages and the step rail. |
| `components/WhyThisVessel.tsx` | Candidate ranking, score breakdown, counterfactual. |
| `components/ReportModal.tsx` | The printable report. |
| `lib/oiltrace.ts` | All data access. Components never call `fetch` directly. |
| `lib/replay.ts` | Timeline interpolation. Pure functions. |
| `types.ts` | Scan payload shapes. |
| `stages.ts` | The five stages, each with what it establishes and what it does not. |
| `ui.tsx` | `Card`, `Badge`, `ScoreBar`. |
| `mapColours.ts` | Overlay colours, named by role. |

No component computes an investigation value — they render what the backend
returned, or "Not available".

Map colours cannot live in `styles.css` with the rest of the palette, because
Leaflet paints strokes through `pathOptions` rather than CSS classes. They are
named by role instead (`spill`, `hindcast`, `forecast`, `counterfactual`), which
is what makes an accidental reuse visible; the legend swatches read the same
constants, so the key cannot drift from the map.

Layout: fleet list and forecast on the left, map centre, selected-vessel detail
on the right, and full-width strips below for attribution, response priority and
forward risk.

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
