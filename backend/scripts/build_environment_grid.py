"""
Convert a downloaded NetCDF subset into the CSV grid services/environment.py
reads. Run once, offline, by hand.

Why a conversion step at all: reading NetCDF at runtime would put xarray and
netCDF4 on requirements.txt for a demo that ships no dataset. Both are imported
inside main() here, so they are needed only to run this script.

    python scripts/build_environment_grid.py currents.nc wind.nc \
        -o data/environment/gulf_2021-03-28.csv

Accepts one file carrying everything, or several that are merged on their shared
coordinates. Variable names are looked up from the aliases below, so a CMEMS,
ERA5 or HYCOM subset all work without editing this file.

Nothing here validates the science of the dataset. It renames, subsets and
writes; PROVENANCE.md is where what the data IS gets recorded.
"""
import argparse
import sys
from pathlib import Path

# Canonical name -> the names real products use for it.
ALIASES = {
    "uo": ["uo", "water_u", "u", "eastward_sea_water_velocity", "ugos"],
    "vo": ["vo", "water_v", "v", "northward_sea_water_velocity", "vgos"],
    "u10": ["u10", "eastward_wind", "wind_u", "UGRD_10maboveground"],
    "v10": ["v10", "northward_wind", "wind_v", "VGRD_10maboveground"],
}
COORDS = {"lat": ["lat", "latitude", "nav_lat", "y"],
          "lon": ["lon", "longitude", "nav_lon", "x"],
          "time": ["time", "valid_time", "date"]}


def _find(names, candidates):
    lower = {n.lower(): n for n in names}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("inputs", nargs="+", help="NetCDF file(s) to read")
    p.add_argument("-o", "--out", required=True, help="CSV to write")
    p.add_argument("--lat", nargs=2, type=float, default=[28.0, 29.1],
                   metavar=("MIN", "MAX"))
    p.add_argument("--lon", nargs=2, type=float, default=[-95.7, -94.2],
                   metavar=("MIN", "MAX"))
    p.add_argument("--start", default="2021-03-28T00:00:00")
    p.add_argument("--end", default="2021-03-31T00:00:00")
    args = p.parse_args(argv)

    try:
        import xarray as xr
    except ImportError:
        sys.exit("This script needs xarray and netCDF4:\n"
                 "    pip install xarray netCDF4\n"
                 "They are deliberately NOT runtime dependencies — the app reads "
                 "the CSV this script produces, not NetCDF.")
    import pandas as pd

    frames = []
    for path in args.inputs:
        ds = xr.open_dataset(path)
        rename = {}
        for canon, names in {**COORDS, **ALIASES}.items():
            found = _find(list(ds.variables) + list(ds.coords), names)
            if found and found != canon:
                rename[found] = canon
        ds = ds.rename(rename)

        # Some products carry a depth/level dimension of size 1 or more; the
        # surface is what a slick sees, so take the shallowest and say so.
        for dim in ("depth", "lev", "level", "z"):
            if dim in ds.dims:
                print(f"  {Path(path).name}: taking shallowest {dim} "
                      f"({float(ds[dim][0])})")
                ds = ds.isel({dim: 0}, drop=True)

        # Longitudes as 0-360 would silently miss a western bbox.
        if "lon" in ds.coords and float(ds.lon.max()) > 180:
            ds = ds.assign_coords(lon=(((ds.lon + 180) % 360) - 180)).sortby("lon")

        ds = ds.sel(lat=slice(*args.lat), lon=slice(*args.lon),
                    time=slice(args.start, args.end))
        keep = [v for v in ALIASES if v in ds.variables]
        if not keep:
            print(f"  {Path(path).name}: none of {list(ALIASES)} present — skipped")
            continue
        print(f"  {Path(path).name}: {keep}, {dict(ds.sizes)}")
        frames.append(ds[keep].to_dataframe().reset_index())

    if not frames:
        sys.exit("No recognised variables in any input. Expected some of "
                 f"{list(ALIASES)} under the aliases this script knows.")

    df = frames[0]
    for f in frames[1:]:
        df = df.merge(f, on=[c for c in ("time", "lat", "lon") if c in f.columns],
                      how="outer")

    for col in ALIASES:
        if col not in df.columns:
            sys.exit(f"Column {col} is missing from the merged result. The app "
                     f"requires all of {list(ALIASES)}; supply the file that "
                     "carries it, or the grid will be rejected at load.")

    df = df[["time", "lat", "lon", *ALIASES]].dropna()
    # Land cells and gaps are dropped rather than filled: environment.py returns
    # no value where a corner is missing, which is the intended behaviour.
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    df = df.sort_values(["time", "lat", "lon"])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, float_format="%.5f")
    print(f"\nWrote {len(df)} rows to {out}")
    print(f"  lat {df.lat.min()}..{df.lat.max()}  lon {df.lon.min()}..{df.lon.max()}")
    print(f"  time {df.time.min()}..{df.time.max()}")
    print("\nNow record the source, resolution, coverage and retrieval date in "
          "data/environment/PROVENANCE.md.")


if __name__ == "__main__":
    main()
