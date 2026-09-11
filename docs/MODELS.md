# Model cards

Both models were trained in `handoff/OILTRACE_AIS_Model.ipynb`, which is
authoritative. The adapters in `backend/ml/` reproduce its architecture,
preprocessing and scoring exactly — including one known flaw, documented below.

**The live source of these facts is `GET /api/models`** (`backend/routes/models.py`),
which composes them from the artifacts at request time: metrics from
`cnn_validation_metrics.json`, hyper-parameters from the pickled estimator, and
the attribution weights from `services/investigation.py`. The MODEL INFO button
in the app header renders exactly that payload. This document explains the same
material at greater length; where the two ever disagree, the endpoint is right,
because nothing in it is typed by hand.

---

## 1. Oil-spill detector (CNN)

| | |
|---|---|
| File | `backend/artifacts/oilspill_cnn.pth` (`state_dict`, 1.7 MB) |
| Task | **Binary image classification** — 0 = NO OIL SPILL, 1 = OIL SPILL |
| Parameters | 421,570 |
| Framework | PyTorch 2.13, CPU (CUDA used automatically if present) |
| Adapter | `backend/ml/cnn_inference.py` |

### Architecture (notebook cell 35)

```python
features = Sequential(
    Conv2d(3, 32, 3, padding=1),  ReLU(), MaxPool2d(2),
    Conv2d(32, 64, 3, padding=1), ReLU(), MaxPool2d(2),
    Conv2d(64, 128, 3, padding=1),ReLU(), MaxPool2d(2),
    Conv2d(128, 256, 3, padding=1),ReLU(), AdaptiveAvgPool2d((1, 1)),
)
classifier = Sequential(
    Flatten(), Linear(256, 128), ReLU(), Dropout(0.4), Linear(128, 2),
)
```

### Preprocessing (cell 33) — do not substitute values

```python
transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.Grayscale(num_output_channels=3),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])
```

Images are opened with `.convert("RGB")`, matching the notebook's inference cells
(73/76). Training used `.convert("L")`, but both funnel through `Grayscale(3)`, so
the resulting tensor is identical.

### Inference

`softmax(dim=1)` → `argmax` → confidence is the probability **of the predicted
class**, not of class 1.

### Performance — 555 held-out Sentinel-1 images

| Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| 89.91% | 97.78% | 71.35% | 82.50% | 93.20% |

|  | Predicted no oil | Predicted oil |
|---|---|---|
| **Actual no oil** | 367 | 3 |
| **Actual oil** | 53 | 132 |

**Read this honestly.** Precision 97.78% means almost every alarm is real — only
3 false positives in 370 clean images. Recall 71.35% means it misses about 29% of
actual spills: 53 of 185. For continuous monitoring that asymmetry is the wrong
way round, since a missed spill costs more than a false alarm. Lowering the
decision threshold would trade precision for recall.

### What it cannot do

No segmentation head, so **no mask, boundary, area, thickness or volume**. No
geolocation — it classifies a tile and says nothing about where that tile is. No
look-alike discrimination: it was not trained to separate oil from biogenic
slicks, low-wind zones or ship wakes, which is the hard part of SAR detection.

Verified reproduction: `class_1.jpg` scores **0.805028**, matching the `0.805` in
the delivered `oiltrace_ai_output_final.json` to the digits it carries — a wrong
resize, normalisation or colour path would have shifted it.

---

## 2. AIS behavioural anomaly detector (Isolation Forest)

| | |
|---|---|
| Files | `ais_isolation_forest.pkl` (1.4 MB), `ais_scaler.pkl` |
| Task | Unsupervised anomaly detection over vessel movement |
| Parameters | `n_estimators=200`, `contamination=0.02`, `random_state=42` |
| Framework | scikit-learn **1.6.1** — pinned; the pickles were created with it |
| Adapter | `backend/ml/ais_inference.py` |

### Features — order is pinned by the scaler

```python
["SOG", "speed_change", "COG", "course_change", "time_gap_minutes"]
```

Not inferred: the saved `StandardScaler` carries `feature_names_in_` with exactly
this order. Note `COG` sits **third**, between the two derived features, which is
not the order a reader would guess.

### Feature engineering (cells 12–13)

```python
df = df.sort_values(["MMSI", "BaseDateTime"])
df["speed_change"]     = df.groupby("MMSI")["SOG"].diff().abs()
df["course_change"]    = df.groupby("MMSI")["COG"].diff().abs()      # naive
df["time_gap_minutes"] = df.groupby("MMSI")["BaseDateTime"].diff().dt.total_seconds() / 60
df = df.dropna(subset=["speed_change", "course_change", "time_gap_minutes"])
```

The `dropna` removes each vessel's first fix, which is why a track needs at least
two valid time-ordered points.

### Scoring (cell 15, then 52/53)

```
anomaly_raw     = model.decision_function(scaled)
anomaly_score   = 100 * (max_raw - anomaly_raw) / (max_raw - min_raw)
is_anomaly      = model.predict(scaled) == -1        # -1 anomalous, 1 normal
behaviour_score = max(anomaly_score) per vessel, clipped 0-100
```

`max_raw` and `min_raw` are **dataset-wide**. A vessel's behaviour score therefore
depends on the corpus it is normalised against, which is why
`data/ais_reference/ais_dataset.csv` (52,943 records, 347 vessels) ships with the
app. Without it the adapter returns `behaviour_score: null` rather than a number
on an unknown scale.

### Known flaw, reproduced deliberately

**`course_change` is not circular.** 359° → 1° is recorded as 358, not 2. The
notebook has a corrected version in cell 18, but that belongs to a second pipeline
whose model was never saved. The naive form is required for compatibility with the
saved scaler's `mean_`/`scale_`; fixing it means retraining. Surfaced in the API as
`course_change_is_circular: false`.

### Which pipeline was saved

The notebook has two. The artifacts prove the **first** (cells 12–15) was saved:
`n_features_in_=5` and `n_samples_seen_=52596` — that is 52,943 raw records minus
347 first-per-vessel rows. The cell-19 variant (4 features, 300 trees, with the
circular fix) was not saved.

---

## Ranking formula

Vessels surviving the AIS filter are scored:

```
final = 0.40 × proximity + 0.30 × trajectory + 0.30 × behaviour
```

| Term | How it is computed |
|---|---|
| `proximity` | `100 × (1 − min_distance / 50 km)`, clipped 0–100 |
| `trajectory` | Convergence: how much the vessel closed on the source across the window |
| `behaviour` | The Isolation Forest's `behaviour_score` for that track |

Deliberately a transparent weighted sum, not a learned ranker: a judge can
multiply the numbers on screen and get the shown score. It is **not** validated
against known attributions — no labelled spill-to-vessel dataset was available.

The dashboard renders each term, its weight and the points it contributes, then
the arithmetic and the total — so the sum can be checked on screen rather than
trusted. Two decimals throughout, because rounding the operands makes the
displayed sum disagree with the displayed total.

### When behaviour is unavailable

A `behaviour` of `null` means the model did not produce a verdict. The candidate
carries `behaviour_status` saying which of these happened:

| status | meaning |
|---|---|
| `ok` | scored normally |
| `track_too_short` | fewer than two AIS fixes, so no movement features exist |
| `model_unavailable` | the Isolation Forest or its scaler could not be loaded |
| `model_declined` | the model ran but returned no score |
| `inference_error` | an unexpected failure, logged with the MMSI |

**The scoring rule is to re-weight, not to zero.** The remaining terms are
renormalised to sum to 1 — proximity 0.571, trajectory 0.429 — and
`weights_applied` travels with the candidate so the displayed arithmetic is the
arithmetic actually used.

This replaced `behaviour or 0.0`, which asserted something false: that a vessel
whose model call failed had behaved unremarkably. At a weight of 0.30 that
silent zero cost up to 30 of 100 points for a reason having nothing to do with
the vessel. Measured on a test track, a forced inference error moved the score
from 57.74 to **39.73** under the old rule and to **56.76** under the new one.

The trade-off is that a candidate scored on two terms is not strictly comparable
with one scored on three. That is why `scored_on_partial_evidence` is set and
the interface says so above the bars, rather than leaving the difference to be
inferred from a hatched bar.

---

## Counterfactual — no model involved

`POST /fleet/counterfactual` is geometry, not inference. It is documented here
because it is easily mistaken for a third model.

It takes a candidate's **real AIS position at the estimated release time** and
runs the hindcast's drift vector forward over the spill's estimated age, then
measures the distance between that simulated position and where the CNN actually
found oil.

**Why it must use the hindcast's vector.** The repo carries three drift
assumptions — hindcast 1.5 km/h toward 135°, forecast 1.0 km/h toward 180°, and
the impact envelope's current-plus-windage (~1.39 km/h toward 181°). The
counterfactual is the *inverse* of the hindcast, so only the hindcast's vector
can answer it. With any other, a vessel sitting exactly on the estimated source
would fail to reproduce the observation and every result would be noise. It also
mirrors `hindcast_over()`'s flat-earth arithmetic rather than the spherical
`geo.destination()`, so the inverse closes exactly: a probe placed on the
estimated source returns a miss of 0.00 km.

**Inverse closure, and its tolerance.** A probe placed at the estimated source
must reproduce the observed spill. `backend/tests/test_counterfactual.py`
asserts a miss of **0.00 km within 0.01 km (10 m)**, at spill ages of 2, 4 and
8 h. The tolerance is that tight deliberately: both sides run the same
flat-earth formula with the sign reversed, so the residual is floating-point
noise. A change that needs a looser tolerance has broken the property rather
than perturbed it, and should be reverted rather than accommodated.

**What the result means.** A distance, not a verdict. The yardstick is how far
the drift being tested could have carried oil over the spill's estimated age:
a miss inside that cannot be separated from the observation under these
assumptions; a miss outside it means the observation does not follow from that
vessel having been the source.

**The yardstick is the test's own drift, not the map's circle.** This was wrong
until Phase 16. The counterfactual drifted at the hindcast's 1.5 km/h toward
135° but was handed the affected-area radius — 5.58 km, sized by
`damage.drift_vector()`'s 1.394 km/h toward 181.2°. It moved a parcel of oil one
way and judged it against how far it could have gone another way. Each mode now
derives its own threshold: **6.00 km** for the legacy vector at a 4 h age, the
integrated displacement (5.59 km in fallback) for the environment-aware one. The
map's affected-area circle stays at 5.58 km — it answers "how far could the oil
have reached at all", sized by the best available estimate, which is a different
question from "how far could THIS assumption have carried it".

Measured consequences: **no verdict changed** (6.26 and 6.23 km sat outside 5.58
and still sit outside 6.00), and no miss distance changed — those are
threshold-independent. Two robustness classifications moved, because those are
margin questions: NISALAH *highly* → *moderately sensitive* (0.571 → 0.653) and
HARVEY HERD *robust* → *moderately sensitive* (0.918 → 0.878).

### The same test, through the environment field

Every counterfactual now also runs via `drift.integrate()` — the same integrator
the environment-aware hindcast uses, so it is that hindcast's exact inverse in
the way the legacy pair are each other's. Verified: a probe at the
environment-aware source reproduces the observation to **6e-05 km**.

**Measured on t3: the two modes agree on every candidate, on both detections,
and the margins invert.**

| Candidate | Legacy | Environment-aware | Distance from flipping |
|---|---|---|---|
| MR CANOPUS (ranked #1) | 2.88 km, consistent | 5.53 km, consistent | 3.12 km → **0.06 km** |
| ACHILLEAS | 3.82 km, consistent | 1.08 km, consistent | 2.18 → 4.51 km |
| SAKAKA | 14.20 km, not | 18.71 km, not | 8.20 → 13.12 km |

Same verdict, opposite confidence. The vessel ranked first is consistent by
three kilometres under one assumption and by sixty metres under the other, and
the vessel that best reproduces the observation changes from MR CANOPUS to
ACHILLEAS. Reporting only "both modes agree" would hide precisely that, which is
why the distance-from-flipping travels with the verdict.

**Agreement is not corroboration.** No environmental dataset is committed, so
the environment-aware run is a *different assumption*, not an observation — and
a reanalysis would be a model output too. Neither mode is validated against a
known attribution.

It is **independent of the ranking and can disagree with it** — in the shipped
t3 demo the third-ranked vessel (GRAND DOLPHIN, 78.91) misses by 9.72 km and is
not consistent, while the sixth-ranked one (ACHILLEAS, 70.38) lands 3.82 km
away, inside the envelope. Neither outcome establishes causation, and the test
inherits every assumption in the drift model rather than checking any of them.

### Robustness — sensitivity to the assumption, not accuracy

Every counterfactual result carries a `robustness` block answering the one
question the miss distance cannot: **how far can the drift assumption move
before the verdict changes?** Nothing in this system measures wind or current,
so the drift vector is a stated constant, and a verdict that turns on getting it
exactly right is worth less than one that does not.

**Swept:** drift speed and bearing, on a 7 × 7 grid (49 evaluations, a couple of
milliseconds per candidate).

| Axis | Band | Why this band |
|---|---|---|
| Drift speed | 0.75–2.25 km/h (±50 % of 1.5) | Contains all three drift assumptions this repo carries (1.0, ~1.39, 1.5 km/h) |
| Drift bearing | 90–180° (±45° of 135°) | Reaches the forecast vector's 180° at its outer edge |

**Not swept, and why.** The observed slick position and the vessel's own AIS
fixes are *observations*, not assumptions. The estimated source is not an input
to the miss distance at all — it appears in the response only as a reported
distance — so perturbing it would manufacture variation the calculation does not
have.

**The assumed age is reported separately, not as a third grid axis.** It is an
assumption, but one bounded by an observation: the previous pass was clear, so
the release lies inside one revisit interval and the true age can only be
younger, never older. Shrinking it collapses the drift and the envelope
together, and near zero only a vessel sitting on the slick can be consistent —
correct physics, but it drives every candidate to "not consistent" at the young
end. Folded into a joint grid it swamped the two axes nothing constrains: on the
t3 case it labelled a candidate at half the envelope radius *highly sensitive*
and one at nearly twice it *robust*. So the age result is kept, as the youngest
age the verdict survives, and reported as its own margin.

**The label is a rule, and the rule travels with the result:** agreement ≥ 90 %
is `robust`, ≥ 60 % is `moderately sensitive`, below that is `highly sensitive`.

**What the fraction is not.** It is not an accuracy, a confidence or a
probability, and the payload says so explicitly (`is_accuracy: false`,
`is_probability: false`). The sweep is a uniform grid over a band chosen by
hand; the fraction is a property of that grid and says nothing about how likely
any drift value is. There are no confidence intervals because the sweep is
deterministic, not statistical.

**Measured on t3**, the pattern is itself a finding: the *not consistent*
verdicts are mostly robust (a vessel 14 km out stays 14 km out however the drift
is nudged), while every *consistent* verdict is sensitive — the consistency
radius is 6.00 km and the swept drift band moves the simulated slick several
kilometres, so exculpatory results here are firmer than incriminating ones.

(This sentence read "the consistency disc is 5.58 km across" until Phase 21: the
radius moved to 6.00 km when each mode was given its own threshold, and "across"
described a radius as if it were a diameter.)
