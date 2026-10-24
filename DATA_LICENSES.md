# Data and third-party licences

The MIT licence in [`LICENSE`](LICENSE) covers the **source code** of this
repository. It does **not** cover the data below, which keeps its original
licence. If you redistribute this repository, keep this file with it.

## SAR image chips: CC BY-SA 4.0

The CNN was trained and evaluated on, and the demo displays tiles from:

> Blondeau-Patissier, D., Schroeder, T., Diakogiannis, F., Li, Z. (2022).
> *CSIRO Sentinel-1 SAR image dataset of oil- and non-oil features for machine
> learning (Deep Learning).* CSIRO Data Collection.
> https://doi.org/10.25919/4v55-dn16

The dataset is licensed under
[Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/).
It contains Copernicus Sentinel-1 data processed by CSIRO. It holds 5,630 grayscale
400×400 JPEG chips: 3,725 in class 0 (no oil features, including look-alikes)
and 1,905 in class 1 (oil features).

We fetch the chips from a public GitHub mirror that copies the CSIRO release
file for file (5,630 files, identical class counts). The mirror is an access route
only and adds no licence of its own. The training images are **not** committed.

Files in this repository that are CSIRO chips, or are derived from them (overlays,
crops, renamed copies), are distributed under **CC BY-SA 4.0** with the
attribution above, not under MIT:

| Path | What it is |
|---|---|
| `backend/data/simulation/image_pool/**` | Chips used by the seeded demo passes |
| `backend/data/simulation/snapshots/t1/`, `t2/`, `t3/` | Copies of pool chips, one per vessel and pass |
| `backend/data/ai_output/samples/*.jpg` | Example chips |
| `frontend/public/ai-data/class_1.jpg` | Example chip |
| `handoff/class_0.jpg`, `handoff/class_1.jpg` | Example chips |
| `handoff/cnn/example_overlay_*.png`, `example_scene_overlay.png` | Grad-CAM overlays on chips (derived) |
| `paper/figures/fig_gradcam.pdf`, `fig_dashboard.jpg` | Paper figures that contain chips (derived) |

Changes we made: grayscale conversion, resizing, Grad-CAM overlays, and copying
chips under per-vessel file names for the demo.

## AIS vessel tracks: U.S. public data

`backend/data/ais_reference/ais_dataset.csv` is an extract (52,943 records,
347 vessels, 31 Dec 2020 to 28 Mar 2021, Gulf of Mexico) in the export schema of
**MarineCadastre.gov**. That service publishes AIS data collected by the U.S. Coast
Guard and distributed by the Bureau of Ocean Energy Management (BOEM) and the National
Oceanic and Atmospheric Administration (NOAA). U.S. federal data is in the public
domain. We credit the source as BOEM and NOAA, MarineCadastre.gov.

The demo fleet (`backend/data/simulation/fleet.json`) uses real tracks from this
extract under **pseudonyms** ("Vessel A"–"Vessel L", pseudo-MMSIs `999000001`–
`999000012`). The incident it depicts is constructed, so no real vessel is
presented as a spill suspect.

## Map tiles

The dashboard loads basemap tiles at runtime from Esri World Imagery and
OpenStreetMap. Both credit lines are shown on the map. OpenStreetMap's public tile
servers are for light use only. A production deployment must use its own tile
server or a commercial provider, under that provider's terms.

## Model weights

`backend/artifacts/*` and `handoff/**/*.pth|*.joblib` were trained by the OILTRACE
team on the data above and are released with the code under MIT. Because the CNN
was trained on CC BY-SA material, we also credit the CSIRO dataset wherever the
weights are redistributed.
