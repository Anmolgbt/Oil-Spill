# Historical environmental data — provenance

## Status: NO DATASET IS COMMITTED

The system runs fully without one and reports `environment_mode: "fallback"`,
with `environment_reason` naming this file. Every drift figure in the app is
therefore derived from the stated assumptions in `backend/core/config.py`:

| | Assumed value | Where |
|---|---|---|
| Surface current | 0.25 m/s toward 170° | `ASSUMED_CURRENT_SPEED_MS` / `_DIRECTION_DEG` |
| Wind (10 m) | 5.0 m/s toward 200° | `ASSUMED_WIND_SPEED_MS` / `_DIRECTION_DEG` |
| Windage | 3 % of wind speed | `WIND_DRIFT_FACTOR` |
| Resulting slick drift | **1.394 km/h toward 181.2°** | `services/damage.drift_vector()` |

This is not a placeholder to be quietly filled in. It is the honest state of the
system, and the app says so wherever the drift is reported.

---

## What a dataset must cover

Derived from the repo, not assumed — the AIS fixes in
`data/simulation/fleet.json` span `2021-03-28T09:39:59Z → 21:39:58Z` inside
`28.4329–28.6210 N`, `-95.1171 – -94.7605 W`, and the forward forecast runs
48 h past the last pass.

| | Required |
|---|---|
| Region | **28.0 – 29.1 N, 95.7 – 94.2 W** (Gulf of Mexico, ~±60 km of padding) |
| Window | **2021-03-28T00:00Z → 2021-03-31T00:00Z** |
| Currents | surface eastward/northward velocity, m/s |
| Wind | 10 m eastward/northward velocity, m/s |
| Cadence | hourly preferred; daily works, the service interpolates in time |

## How to add one

1. Download a subset covering the above. Candidate sources, none of which this
   repo endorses or depends on:
   - **Copernicus Marine** GLORYS12 reanalysis (`cmems_mod_glo_phy_my_0.083deg_P1D-m`,
     variables `uo`/`vo` at the shallowest depth) for currents, plus
   - **ERA5 single levels** (`10m_u_component_of_wind`, `10m_v_component_of_wind`)
     for wind. Both free, both need an account.
   - **HYCOM GOFS 3.1** `expt_93.0` (`water_u`/`water_v`) needs no account but
     gives currents only.
2. Convert it: `python scripts/build_environment_grid.py <files...> -o data/environment/gulf_2021-03-28.csv`
   The script needs `xarray` and `netCDF4`, which are deliberately NOT runtime
   dependencies — install them only to run the conversion.
3. Drop the CSV in this directory. **No code change is needed.** The service
   picks up exactly one `*.csv` here; more than one and it declines and says so.
4. Fill in the record below and commit both.

## Expected CSV schema

```
time,lat,lon,uo,vo,u10,v10
2021-03-28T00:00:00Z,28.0,-95.7,0.104,-0.233,-1.82,-4.05
```

Vectors are **eastward (`u`) and northward (`v`) components in m/s**, the
convention every reanalysis uses, so no sign or bearing convention has to be
guessed at load time. The grid must be regular in lat, lon and time; the service
does bilinear interpolation in space and linear in time, and returns *no value*
outside the coverage rather than extrapolating.

## Record for the dataset actually used

> Fill this in when a file is added. Leave it as-is while none is.

- **Source / product ID:** —
- **Variables and units:** —
- **Spatial resolution:** —
- **Temporal resolution:** —
- **Coverage (bbox, time range):** —
- **Retrieved on:** —
- **Retrieved by:** —
- **Licence / attribution required:** —
- **Converted with:** `scripts/build_environment_grid.py` (record the command)

## What using one would and would not mean

A historical reanalysis is itself a model output, not an observation of this
patch of sea. Loading one makes the drift **physically informed**; it does not
make it **accurate**, and nothing in this system is validated against a known
spill trajectory. No accuracy claim follows from adding data here.
