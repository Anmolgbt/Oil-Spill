# Model cards

Both models were trained in `handoff/OILTRACE_AIS_Model.ipynb`, which is
authoritative. The adapters in `backend/ml/` reproduce its architecture,
preprocessing and scoring exactly — including one known flaw, documented below.

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
