# OILTRACE paper

`oiltrace.tex` is the IEEE conference paper (IEEEtran, two-column). The figures are in
`figures/`. The bibliography is inline (`thebibliography`), so no BibTeX run is needed.

## Build

**Overleaf:** upload `oiltrace.tex` and the `figures/` folder, set the compiler to
pdfLaTeX, and compile. IEEEtran, TikZ and booktabs are all in the default TeX Live image.

**Locally:**

```bash
latexmk -pdf oiltrace.tex
```

The source has been linted (environments, braces, citations, labels, figure paths), but it
has not been compiled in this repository. Check the PDF for overfull boxes and the column
layout of Fig. 1 before submission.

## Before submission: must fill

- [ ] Authors and affiliations replace `[Author 1–6]`, and a corresponding author is named.
- [ ] `[repository URL]` in *Data and Code Availability* points at the public repository.
- [ ] The target venue's own template and page limit are applied. The paper now runs to
      about 8–9 pages with the result figures. If the limit is 6, move Figs. 7–8
      (reliability, Grad-CAM) and Table II to a supplement.
- [ ] Reference [2] (Potdar et al.) is checked against the publisher. The PDF is hosted at
      `jet-m.com`. We could not confirm that this is Elsevier's *Journal of Engineering
      and Technology Management* (ISSN 0923-4748). Cite the version of record if it exists
      elsewhere.
- [ ] Reference [11] (Reed et al., 1999) has no verified DOI, so none is given. Add it
      from Crossref if the venue requires DOIs.

## Where every number comes from

All values come from frozen artifacts. Nothing was retrained for this paper.

| Paper item | Source |
|---|---|
| Table I (dataset, split) | `handoff/cnn/cnn_split_manifest.csv`, recounted from the CSIRO chips |
| Table IV CNN metrics, CIs, ECE | `handoff/cnn/cnn_test_metrics.json` |
| Table IV near-duplicate column, §VII-B | `handoff/cnn/near_duplicate_report.json` (`backend/scripts/check_near_duplicates.py`) |
| Figs. 4–9 (confusion, ROC/PR, training, reliability, Grad-CAM, scenario) | `backend/scripts/make_paper_figures.py` → `paper/data/figure_numbers.json` |
| Per-tile test probabilities | `paper/data/cnn_test_predictions.csv` (`backend/scripts/replay_cnn_test_split.py`, reproduces TN/FP/FN/TP = 370/11/10/183 exactly) |
| Validation ECE before/after scaling | `paper/data/figure_numbers.json` (`val_ece_raw`, `val_ece_calibrated`) |
| Table V (AIS) | `handoff/ais/OILTRACE_AIS_Final.ipynb` outputs, `backend/artifacts/ais_anomaly_model_meta.json` |
| Table VI, Fig. 9 (scenario) | live `run_fleet_scan("t3")`, captured in `paper/data/figure_numbers.json` |
| Drift arithmetic | `backend/services/damage.py: drift_vector()`, `backend/core/config.py` |
| Fig. 10 (dashboard) | screenshot of the running app, pass T3 |

## Reproduce the figures

```bash
cd backend
.venv/bin/pip install -r ../paper/requirements-figures.txt
git clone --depth 1 https://github.com/Saisamarth21/Oil-Spill-Detection-in-Marine-Environments-Using-AIS-and-Satellite-Data.git /tmp/csiro-chips
.venv/bin/python scripts/replay_cnn_test_split.py "/tmp/csiro-chips/SAR Image Dataset"
.venv/bin/python scripts/check_near_duplicates.py "/tmp/csiro-chips/SAR Image Dataset"
.venv/bin/python scripts/make_paper_figures.py "/tmp/csiro-chips/SAR Image Dataset"
```

The mirror is a file-for-file copy of the CSIRO release (DOI 10.25919/4v55-dn16, CC BY-SA 4.0).
See [`../DATA_LICENSES.md`](../DATA_LICENSES.md).
