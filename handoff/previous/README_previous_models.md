# Model handoff

Everything in this folder is exactly as delivered by the model-training work in
Google Colab. Nothing here has been edited — it is kept as the provenance record
for how the two models were built.

| File | What it is |
|---|---|
| `OILTRACE_AIS_Model.ipynb` | The training notebook. Authoritative for the CNN architecture, preprocessing, the AIS feature engineering and the scoring formulas. |
| `oilspill_cnn.pth` | Trained CNN weights (`state_dict`). Binary classifier, 421,570 parameters. |
| `ais_isolation_forest.pkl` | Trained Isolation Forest (200 trees, contamination 0.02, 5 features). |
| `ais_scaler.pkl` | The `StandardScaler` fitted alongside it. Carries `feature_names_in_`, which is what pins the feature order. |
| `oiltrace_ai_output_final.json` | The completed investigation the notebook produced end to end. |
| `cnn_validation_metrics.json` | Test-set metrics and confusion matrix. |
| `class_0.jpg`, `class_1.jpg` | Sample SAR tiles: no-oil and oil. |

## The running app does not read this folder

`backend/artifacts/` and `backend/data/ai_output/` hold the copies the API loads.
They are byte-identical to the originals here. The duplication is deliberate: this
folder stays pristine as a record, while the backend owns its own copies so the
app never depends on the handoff layout.

## Two things found in the notebook, recorded here so they are not lost

**1. `course_change` is not circular.** Cell 13 computes
`groupby("MMSI")["COG"].diff().abs()`, so 359° → 1° is recorded as 358, not 2.
Cell 18 has a corrected version — but that belongs to a *second* pipeline whose
model was never saved. `backend/ml/ais_inference.py` deliberately reproduces the
naive form, because the saved scaler's `mean_`/`scale_` were fitted on those
values. Fixing it requires retraining.

**2. The save cells would overwrite the AIS model on a clean re-run.** Cells 59,
61 and 63 call `joblib.dump(model, "ais_isolation_forest.pkl")`, but `model` is
rebound to the CNN in cell 35. The delivered `.pkl` is a genuine
`IsolationForest`, so those cells must have run before cell 35 — but executing the
notebook top to bottom would replace the AIS model with the CNN. Worth fixing
before any retrain.

## Which pipeline was actually saved

The notebook contains two AIS pipelines. The artifacts prove the **first** one
(cells 12–15) was saved: `n_estimators=200`, `n_features_in_=5`, and
`n_samples_seen_=52596` (= 52,943 raw records minus 347 first-per-vessel rows
dropped by the cell-13 `dropna`). The cell 19 variant — 4 features, 300 trees,
with the circular fix — was not saved.
