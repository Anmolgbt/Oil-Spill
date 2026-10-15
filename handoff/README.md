# Handoff — how the two models were produced

This folder is the provenance record for the models in `backend/artifacts/`. Nothing in
`cnn/` or `ais/` has been edited; `previous/` holds the models these replaced.

## Current models

### `cnn/` — oil-spill classifier (trained on a GPU in Colab)

| File | What it is |
|---|---|
| `OILTRACE_CNN_Final.ipynb` | The training notebook. Authoritative for the architecture, preprocessing, scene-grouped split, calibration and threshold selection. |
| `oilspill_cnn_best.pth` | Trained weights (`state_dict`). 1,206,370 parameters. Copied to `backend/artifacts/`. |
| `cnn_config.json` | Image size, normalisation, dropout, **temperature (1.0286)** and **decision threshold (0.57)**, evaluation summary, provenance. Copied to `backend/artifacts/`. |
| `oiltrace_cnn.py` | The module the notebook wrote. Identical to `backend/ml/oiltrace_cnn.py`. |
| `cnn_test_metrics.json` | The held-out test result: 574 tiles, 451 unseen scenes, with 95% intervals. |
| `cnn_split_manifest.csv` | Every tile, its scene and its split — what makes the split reproducible. |
| `cnn_training_history.csv` | Per-epoch loss / validation metrics (50 epochs). |
| `cnn_output_example.json`, `example_*.png` | The notebook's own example outputs. |
| `requirements_cnn.txt` | Versions it was trained under. |

### `ais/` — AIS behaviour model

| File | What it is |
|---|---|
| `OILTRACE_AIS_Final.ipynb` | The notebook, with its recorded outputs (cleaning report, injection test, 28 passing checks). |
| `oiltrace_ais.py` | The module the notebook wrote. Identical to `backend/ml/oiltrace_ais.py`. |
| `ais_anomaly_model.joblib`, `..._meta.json` | The model as exported **under scikit-learn 1.8.0** (needs Python 3.11+). |
| `demo_ais_arabian_sea.csv`, `ais_incident_result.json` | The notebook's own synthetic demo incident. Not used by this app. |

**The backend does not load `ais/ais_anomaly_model.joblib`.** This app pins
scikit-learn 1.6.1 (and supports Python 3.9+), and a pickle is only safe under the version
that wrote it, so `backend/artifacts/ais_anomaly_model.joblib` is the same recipe re-run
under 1.6.1 by `backend/scripts/train_ais_model.py`. The two have identical calibration
constants (`lo = -0.25533`, `hi = 0.09406`), as they should: same code, same corpus, same
seed.

### Files in this folder's root

`oiltrace_ai_output_final.json`, `cnn_validation_metrics.json` — the stored completed case
and the metrics file, as served by `/ai-result` and `/api/models`. They are **regenerated**
from the installed models by `backend/scripts/regenerate_stored_result.py`, and are
byte-identical to the copies in `backend/data/ai_output/`. `class_0.jpg` / `class_1.jpg`
are the sample tiles.

## What was checked

* **The shipped weights, run through the backend's own inference code, reproduce the
  notebook's test result exactly** — TN 370, FP 11, FN 10, TP 183. Re-run it with
  `backend/scripts/replay_cnn_test_split.py` (it needs the public dataset; the script says
  where to get it).
* The checkpoint loads into the shipped architecture with no missing or unexpected keys.
* The AIS model's calibration matches the notebook's.
* The demo detects exactly the vessels the simulation seeded, with no false alarms on the
  two clear passes — see `backend/tests/test_model_swap.py`.

## What these models are, and are not

* The CNN's 96.3% accuracy is on scenes it never saw, with a 95% interval of 94.6–97.9%.
  The demo's tiles, however, come from the dataset it was trained on, so the demo's
  detections are **not** an accuracy test.
* `Class 1 = oil spill` is taken from the dataset's own `_cls_N` naming
  (`cnn_config.json` says so too). Confirm it with the data owner before relying on it.
* The AIS model is unsupervised. It was checked by injecting known unusual behaviour into
  held-out vessels, not against real violations. "Anomalous" means unusual, not wrong.
* The CNN is a binary classifier: no mask, area or look-alike discrimination.

## `previous/`

The models and notebook used before this swap — `oilspill_cnn.pth`,
`ais_isolation_forest.pkl`, `ais_scaler.pkl`, `OILTRACE_AIS_Model.ipynb` — with their stored
outputs and the README that described them. Kept so the change is auditable and reversible;
the app no longer reads any of it.

## Reproducing

```bash
cd backend
python scripts/train_ais_model.py                       # re-export the AIS model under the pinned sklearn
python scripts/regenerate_stored_result.py              # refresh the stored case + metrics from the installed models
python scripts/replay_cnn_test_split.py "<dataset>/SAR Image Dataset"
python -m pytest
```
