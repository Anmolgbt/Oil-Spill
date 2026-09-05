# Visually ambiguous "clean" tiles — kept out of the demo pool

These are real SAR tiles from the dataset's **no-oil (class 0)** folder, and the
trained CNN classifies them correctly as NO OIL. They are set aside here for a
presentation reason only, not a modelling one:

each contains a large dark low-backscatter patch that *looks* like a slick to a
human viewer. On the dashboard that reads as "the tile obviously has oil but the
model missed it", which is exactly the wrong impression to give in a demo — the
model is right, the tile is just visually misleading.

Measured dark-pixel fraction (pixels below intensity 60), which is what makes
them read as oily:

| tile          | mean intensity | dark pixels |
|---------------|---------------:|------------:|
| t1_ship2.jpg  |           49.7 |       43.1% |
| t0_ship2.jpg  |           65.0 |       29.8% |
| t0_ship1.jpg  |          113.7 |        9.3% |
| t0_ship5.jpg  |          219.9 |        4.8% |
| t0_ship4.jpg  |           94.0 |        2.1% |

The tiles left in `../clean/` are all below 1% dark pixels — uniform sea texture,
sometimes with a bright vessel return, and no slick-shaped dark region.

Nothing reads this folder at runtime: `services/t3_simulation.py` globs
`clean/*.jpg` and `oil/*.jpg` only, and does not recurse.
