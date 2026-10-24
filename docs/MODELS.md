# Model cards

Both models were trained in notebooks kept under `handoff/`
(`handoff/cnn/OILTRACE_CNN_Final.ipynb` and `handoff/ais/OILTRACE_AIS_Final.ipynb`),
which are authoritative. Each notebook writes the importable module the backend
runs - `backend/ml/oiltrace_cnn.py` and `backend/ml/oiltrace_ais.py` are those same
files - so a prediction made here is a prediction made in the notebook. The adapters
`backend/ml/cnn_inference.py` and `ais_inference.py` only fit them to the shape the
rest of the backend already used. (The previous models and their notebook are kept in
`handoff/previous/`.)

**The live source of these facts is `GET /api/models`** (`backend/routes/models.py`),
which composes them from the artifacts at request time: metrics from
`cnn_validation_metrics.json`, hyper-parameters from the fitted estimator, and
the attribution weights from `services/investigation.py`. The MODEL INFO button
in the app header renders exactly that payload. This document explains the same
material at greater length; where the two ever disagree, the endpoint is right,
because nothing in it is typed by hand.

---

## 1. Oil-spill detector (CNN)

| | |
|---|---|
| Files | `backend/artifacts/oilspill_cnn_best.pth` (`state_dict`, 4.8 MB) and `cnn_config.json` |
| Task | **Binary image classification** - 0 = NO OIL SPILL, 1 = OIL SPILL |
| Parameters | 1,206,370 |
| Framework | PyTorch (trained on 2.11, runs on 2.2+), CPU - CUDA used automatically if present |
| Adapter | `backend/ml/cnn_inference.py` over `backend/ml/oiltrace_cnn.py` |
| Training data | CSIRO Sentinel-1 SAR oil/non-oil chips, [DOI 10.25919/4v55-dn16](https://doi.org/10.25919/4v55-dn16), CC BY-SA 4.0 |

### Training data

Blondeau-Patissier, Schroeder, Diakogiannis and Li (2022), *CSIRO Sentinel-1 SAR image
dataset of oil- and non-oil features for machine learning (Deep Learning)*. It has 5,630
grayscale 400×400 JPEG chips: 3,725 in class 0 (no oil features, including look-alikes)
and 1,905 in class 1 (oil features). The class meaning is the dataset authors'. We
fetch the files from a public GitHub mirror that is a file-for-file copy of the release
(same file count, same class counts). We use it rather than the Kaggle copy because only
the original filenames carry the scene identifier the grouped split needs. See
[`DATA_LICENSES.md`](../DATA_LICENSES.md).

### Architecture

Four blocks of `Conv-BatchNorm-ReLU` x2 then `MaxPool` (32, 64, 128, 256 channels),
global average pooling, and a `Dropout(0.30) - Linear(256,128) - ReLU - Dropout(0.30) -
Linear(128,2)` head. The checkpoint loads into this class with no missing or
unexpected keys (asserted by `tests/test_model_swap.py`).

### Preprocessing - do not substitute values

```python
transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.Grayscale(num_output_channels=3),
    transforms.ToTensor(),
    transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),     # NOT the ImageNet values
])
```

Images are opened with `.convert("L")`, exactly as in training.

### Decision rule - all fitted on the validation split only

```
probability = softmax(logits / T)[oil]        T = 1.0286   (temperature scaling)
verdict     = OIL SPILL  when probability >= 0.57          (threshold = max validation F1)
confidence  = the calibrated probability of the verdict that was returned
```

Because the threshold is 0.57 rather than 0.5, a tile with an oil probability between
0.50 and 0.57 is classed NO OIL SPILL with a displayed confidence under 50%. That is
intended: the confidence is the probability of the verdict returned. Test-time
augmentation is deliberately **not** applied - the reported metrics were measured
without it.

### How it was evaluated

The 5,536 usable tiles (after removing 90 exact duplicates and 4 images whose identical
copy carries the opposite label) are 400x400 crops, many overlapping 50 %, cut from
4,492 larger scenes. A random split would put overlapping pixels of one scene in both
training and test, so the split is **grouped by scene** (`StratifiedGroupKFold`, 80/10/10):
no scene contributes to more than one of train / validation / test. Calibration and
the threshold used the validation split; the test split was used once.

### Performance - 574 held-out tiles from 451 unseen scenes

| Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| 96.34% | 94.33% | 94.82% | 94.57% | 99.33% |

95% intervals (resampling whole scenes): accuracy 94.6-97.9 %, precision 90.5-97.4 %,
recall 90.7-98.1 %, ROC-AUC 98.7-99.8 %. Expected calibration error 1.4 %.

|  | Predicted no oil | Predicted oil |
|---|---|---|
| **Actual no oil** | 370 | 11 |
| **Actual oil** | 10 | 183 |

**Read this honestly.** Roughly one alarm in 18 is false and roughly one spill in 19 is
missed. The intervals are wide enough that "about 95%" is the defensible claim, not
"96.3%". This is one public dataset, so other sensors, sea states and regions are
untested.

**Training length.** The run is cap-limited. Early stopping (patience 8) never fired
within the 50-epoch cap, and the best validation ROC-AUC (0.9903) came in the last epoch.
The curve had nearly flattened: validation ROC-AUC stayed between 0.986 and 0.990 over
epochs 43–50. A longer run might add a little. We did not retrain, so that the evaluated
model stays fixed.

**Calibration.** The temperature is close to 1 (T = 1.0286), so scaling barely changes
the probabilities. Validation ECE is 0.0229 before scaling and 0.0238 after (10 bins).
The raw model was already well calibrated.

**Near-duplicate audit.** The grouped split cannot catch the same sea patch filed under a
different scene ID, or a rotated copy. A perceptual-hash check (64-bit pHash, all 8
orientations, Hamming distance ≤ 8) finds 58 test tiles in 52 scenes with a near-duplicate
in training. At ≤ 4 bits the count is 7. Re-scoring the frozen model without those 58
tiles gives 96.12% accuracy, 94.19% recall and 0.9930 ROC-AUC, so leakage does not explain
the result. Reproduce with `backend/scripts/check_near_duplicates.py`. The output is in
`handoff/cnn/near_duplicate_report.json`.

### What it cannot do

No segmentation head, so **no mask, boundary, area, thickness or volume**. No
geolocation - it classifies a tile and says nothing about where that tile is. No
look-alike discrimination: it has two classes and was not trained to separate oil from
biogenic slicks, low-wind zones or ship wakes, which is the hard part of SAR detection.
(`oiltrace_cnn.py` contains an approximate Grad-CAM mask helper from the notebook. The
backend deliberately does not expose it, because a heat-map region is not a
segmentation. The paper shows two Grad-CAM overlays as a visual aid only.)

### The demo is not a test

The demo's satellite tiles are drawn from the same public dataset the CNN was trained on
- of the bundled tiles, 9 were in the training split, 7 in validation and 1 in test (2
could not be matched) - so its confident detections are not a held-out measurement. The
574-tile figure above is.

### Verified reproduction

Replaying the notebook's exact test split (574 tiles) through `backend/ml/cnn_inference.py`
reproduces the notebook's confusion matrix exactly: TN 370, FP 11, FN 10, TP 183.

---

## 2. AIS behavioural anomaly detector (Isolation Forest)

| | |
|---|---|
| File | `backend/artifacts/ais_anomaly_model.joblib` (forest + scaler + calibration), `ais_anomaly_model_meta.json` |
| Task | Unsupervised anomaly detection over vessel movement |
| Parameters | `n_estimators=300`, `contamination=0.02`, `random_state=42` |
| Framework | scikit-learn **1.6.1** - pinned; the artifact was exported with it (`python scripts/train_ais_model.py` regenerates it) |
| Adapter | `backend/ml/ais_inference.py` over `backend/ml/oiltrace_ais.py` |

### What changed from the previous model, and why it matters

1. **AIS "not available" codes are no longer scored as behaviour.** `SOG 102.3`, `COG 360`
   and `Heading 511` mean "no value". The previous model fed 102.3 knots straight into
   the forest, so a missing-value flag was ranked the most anomalous record in the
   corpus - and the top candidate in the original completed case owed its behaviour score
   of 100 to it. The reference corpus holds 132 such speed codes (4 vessels) and 446 course
   codes; they are cleared and speed/course are **recovered from the position track**
   (132 speeds and 251 courses recovered).
2. Features are computed **inside a track segment** (a gap over 15 minutes starts a new
   one), so a vessel's absence between two visits is not "behaviour". 347 vessels form
   797 segments.
3. Features are **location independent**: `[sog, accel_kn_per_min, turn_rate_deg_per_min,
   speed_mismatch_kn]` - speed, how fast it changes, how fast the course changes, and
   how far the reported speed disagrees with the speed the positions imply. The previous
   model also used raw course, so shipping-lane direction could masquerade as anomaly.
   The course change is now circular (359 to 1 degree is 2, not 358).
4. The 0-100 score uses a **fixed calibration** (0 = the training median, 100 = its 99.5th
   percentile; stored with the model). It no longer needs the corpus at request time, so
   one vessel's track can be scored on its own.

### Scoring

```
anomaly_score    calibrated 0-100, per record
is_anomaly       IsolationForest.predict == -1
behaviour_score  per vessel: max(anomaly_score) over its records      (unchanged)
```

Because the score is clipped at the training 99.5th percentile and the vessel's score is
its **maximum**, several vessels can tie at 100 - it means "had at least one record as
unusual as the most unusual 0.5% of training traffic". Records must carry `LAT` and
`LON`: reported speed is cross-checked against the position track, so the model cannot
score a track without positions.

### Checked how

There is no ground truth for AIS anomalies, so the notebook checks the model by
**injecting** known unusual behaviour (speed collapse, erratic turning, speed/position
mismatch) into 69 held-out vessels: ROC-AUC 0.993, 86% of injected rows flagged, 0.9%
of ordinary rows flagged. That shows the model separates gross changes from ordinary
traffic. It does **not** show it finds real violations - it is unsupervised, and
`contamination = 0.02` flags about 2% of records by construction.

### What it cannot do

Anomalous means *statistically unusual compared with the training traffic* - not
"did something wrong". It was trained on one Gulf of Mexico corpus (52,943 records, 347
vessels, Dec 2020-Mar 2021); its features are location independent, but behaviour in other
waters is untested. AIS has gaps and can be switched off, so no anomaly is not evidence of
normal behaviour.

---

## Ranking formula

Vessels surviving the AIS filter are scored:

```
final = 0.40 × proximity + 0.30 × trajectory + 0.30 × behaviour
```

| Term | How it is computed |
|---|---|
| `proximity` | `100 × (1 − min_distance / r)`, clipped 0–100. In the fleet scan, `r` = 3 × the drift-envelope radius (16.7 km at 4 h). `/ai/investigate` keeps the notebook's 50 km |
| `trajectory` | `100 × (d_first − d_min) / d_first`, clipped 0–100, over fixes from 6 h before to 2 h after release |
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

**The yardstick is the test's own drift, not the map's circle.** Each mode derives its
own threshold from the vector that moves the oil. That is **6.00 km** for the kinematic
vector at a 4 h age, and the integrated displacement (5.59 km in fallback) for the
environment-aware one. The map's affected-area circle (5.58 km) answers a different
question: how far the oil could have reached at all, using the best available
estimate.

### The same test, through the environment field

Every counterfactual now also runs via `drift.integrate()` — the same integrator
the environment-aware hindcast uses, so it is that hindcast's exact inverse in
the way the legacy pair are each other's. Verified: a probe at the
environment-aware source reproduces the observation to **6e-05 km**.

**Measured on t3: the two modes agree on every candidate, on both detections,
and the margins invert.**

| Candidate | Legacy | Environment-aware | Distance from flipping |
|---|---|---|---|
| Vessel K (ranked #1) | 2.88 km, consistent | 5.53 km, consistent | 3.12 km → **0.06 km** |
| Vessel L | 3.82 km, consistent | 1.08 km, consistent | 2.18 → 4.51 km |
| Vessel F | 14.20 km, not | 18.71 km, not | 8.20 → 13.12 km |

Same verdict, opposite confidence. The vessel ranked first is consistent by
three kilometres under one assumption and by sixty metres under the other, and
the vessel that best reproduces the observation changes from Vessel K to
Vessel L. Reporting only "both modes agree" would hide precisely that, which is
why the distance-from-flipping travels with the verdict.

**Agreement is not corroboration.** No environmental dataset is committed, so
the environment-aware run is a *different assumption*, not an observation — and
a reanalysis would be a model output too. Neither mode is validated against a
known attribution.

It is **independent of the ranking and can disagree with it**. In the shipped T3 demo,
the third-ranked vessel (Vessel H, 72.71) misses by 9.15 km and is not consistent, while
the fourth-ranked one (Vessel L, 68.79) lands 3.82 km away, inside the 6.00 km threshold. Neither outcome establishes causation, and the test
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
