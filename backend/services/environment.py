"""
HISTORICAL ENVIRONMENT — what were the current and wind here, then?

Everything this system says about where oil goes rests on four numbers typed
into core/config.py: a current of 0.25 m/s toward 170 deg and a wind of 5.0 m/s
toward 200 deg. The repo has always said so (`environmental_data_measured:
false`). This module is the socket a real historical field plugs into, so that
the later phases can step a slick through a varying field instead of one
constant.

NO DATASET IS COMMITTED. That is the shipped state, not an oversight: the
padded window a dataset must cover is documented in
data/environment/PROVENANCE.md, and the file can only arrive by someone
downloading it. So the contract here is that the system runs FULLY without one
and says which mode it is in:

    environment_mode: "historical"   every value came from the dataset
                      "fallback"     every value is the stated assumption

`environment_reason` says why, whenever it is not "historical". A partial answer
is never silently blended into a whole one — if the dataset covers the current
but not the wind, the per-variable `measured` flags say so and the overall mode
stays "fallback", because a drift built half from data and half from a guess is
not a historical drift.

WHAT THIS IS NOT. Nothing here is validated against anything. A historical
reanalysis is a model output too, and swapping one in makes the drift
*physically informed*, not *accurate*. No claim of improved accuracy is made
here or anywhere downstream.
"""
import math
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path

from core.config import (ASSUMED_CURRENT_DIRECTION_DEG, ASSUMED_CURRENT_SPEED_MS,
                         ASSUMED_WIND_DIRECTION_DEG, ASSUMED_WIND_SPEED_MS,
                         WIND_DRIFT_FACTOR)
from .geo import parse_time

MS_TO_KMH = 3.6

# Where a committed grid is looked for. Absent by design; see PROVENANCE.md.
ENVIRONMENT_DIR = Path(__file__).resolve().parents[1] / "data" / "environment"

# The columns a grid file must carry. Vectors are metres per second, eastward
# and northward — the convention every reanalysis uses — so that no sign or
# bearing convention has to be guessed at load time.
GRID_COLUMNS = ("time", "lat", "lon", "uo", "vo", "u10", "v10")


# --- vector arithmetic -------------------------------------------------------

def combine_current_and_wind(current_ms, current_deg, wind_ms, wind_deg,
                             windage=WIND_DRIFT_FACTOR):
    """
    Slick drift: the current, plus `windage` of the wind, summed as vectors.

    Lifted out of damage.drift_vector() so the assumed drift and any historical
    drift are computed by the identical arithmetic. A second copy would
    eventually disagree with this one and the comparison Phase 15 exists to draw
    would be measuring the copy rather than the data.

    Directions are compass bearings the flow moves TOWARD. Returns km/h and a
    bearing.
    """
    current_kmh = current_ms * MS_TO_KMH
    wind_kmh = wind_ms * MS_TO_KMH * windage

    # Compass bearings: north is +y, east is +x.
    east = (current_kmh * math.sin(math.radians(current_deg))
            + wind_kmh * math.sin(math.radians(wind_deg)))
    north = (current_kmh * math.cos(math.radians(current_deg))
             + wind_kmh * math.cos(math.radians(wind_deg)))

    return (round(math.hypot(east, north), 3),
            round((math.degrees(math.atan2(east, north)) + 360) % 360, 1))


def _uv_to_speed_bearing(u, v):
    """Eastward/northward m/s to (speed m/s, compass bearing moved toward)."""
    return (round(math.hypot(u, v), 4),
            round((math.degrees(math.atan2(u, v)) + 360) % 360, 1))


# --- providers ---------------------------------------------------------------

class AssumedConstantProvider:
    """
    The stated assumptions from core/config.py. Always answers, and is honest
    that it is not an observation. This is the fallback, and with no dataset
    committed it is also the only provider that ever answers.
    """
    name = "Stated assumption (core/config.py)"
    resolution = None
    coverage = None
    measured = False

    def conditions_at(self, lat, lon, when):
        return {
            "current": {"speed_ms": ASSUMED_CURRENT_SPEED_MS,
                        "direction_deg": ASSUMED_CURRENT_DIRECTION_DEG,
                        "measured": False},
            "wind": {"speed_ms": ASSUMED_WIND_SPEED_MS,
                     "direction_deg": ASSUMED_WIND_DIRECTION_DEG,
                     "measured": False},
            "sampled_at": None,
        }


class GridFileProvider:
    """
    A committed historical grid, read from CSV.

    CSV rather than NetCDF deliberately: reading NetCDF at runtime would put
    xarray or netCDF4 on requirements.txt for a demo that ships no dataset.
    scripts/build_environment_grid.py does that conversion once, offline, with
    those libraries imported inside the function.

    Bilinear in space, linear in time, and `None` outside coverage rather than
    an extrapolation — a value invented beyond the data's edge is worse than no
    value, because it looks like data.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.name
        self._grid = None
        self._meta = {}

    # -- loading --

    def _load(self):
        if self._grid is not None:
            return self._grid
        import pandas as pd

        df = pd.read_csv(self.path)
        missing = [c for c in GRID_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{self.path.name} is missing columns: {missing}. "
                             f"Expected {list(GRID_COLUMNS)}.")

        df["time"] = df["time"].map(lambda t: parse_time(t).timestamp())
        self._times = sorted(df["time"].unique())
        self._lats = sorted(df["lat"].unique())
        self._lons = sorted(df["lon"].unique())
        # Keyed lookup: the grid is small (a few thousand rows for one incident
        # window) so a dict beats re-filtering a frame per sample.
        self._grid = {(r.time, r.lat, r.lon): (r.uo, r.vo, r.u10, r.v10)
                      for r in df.itertuples()}
        self._meta = {
            "rows": len(df),
            "lat_range": [self._lats[0], self._lats[-1]],
            "lon_range": [self._lons[0], self._lons[-1]],
            "time_range": [
                datetime.fromtimestamp(self._times[0], timezone.utc).isoformat(),
                datetime.fromtimestamp(self._times[-1], timezone.utc).isoformat(),
            ],
            "lat_step": round(self._lats[1] - self._lats[0], 4) if len(self._lats) > 1 else None,
            "lon_step": round(self._lons[1] - self._lons[0], 4) if len(self._lons) > 1 else None,
        }
        return self._grid

    @property
    def coverage(self):
        self._load()
        return {k: self._meta[k] for k in ("lat_range", "lon_range", "time_range")}

    @property
    def resolution(self):
        self._load()
        return {"lat_deg": self._meta["lat_step"], "lon_deg": self._meta["lon_step"],
                "time_slices": len(self._times)}

    # -- sampling --

    @staticmethod
    def _bracket(values, x):
        """The two grid values either side of x, plus the interpolation weight."""
        if x < values[0] or x > values[-1]:
            return None
        i = bisect_left(values, x)
        if i == 0:
            return values[0], values[0], 0.0
        lo, hi = values[i - 1], values[i]
        if hi == lo:
            return lo, hi, 0.0
        return lo, hi, (x - lo) / (hi - lo)

    def conditions_at(self, lat, lon, when):
        self._load()
        t = parse_time(when).timestamp() if isinstance(when, str) else when.timestamp()

        bt = self._bracket(self._times, t)
        blat = self._bracket(self._lats, lat)
        blon = self._bracket(self._lons, lon)
        if bt is None or blat is None or blon is None:
            return None

        (t0, t1, wt), (y0, y1, wy), (x0, x1, wx) = bt, blat, blon

        def at(tt, yy, xx):
            return self._grid.get((tt, yy, xx))

        # Trilinear: bilinear in space at each bracketing time slice, then
        # linear between them. Any missing corner (a land cell, a ragged grid)
        # makes the whole sample unavailable rather than partially filled.
        corners = []
        for tt in (t0, t1):
            square = [at(tt, yy, xx) for yy in (y0, y1) for xx in (x0, x1)]
            if any(c is None for c in square):
                return None
            c00, c01, c10, c11 = square
            blended = tuple(
                (c00[i] * (1 - wx) + c01[i] * wx) * (1 - wy)
                + (c10[i] * (1 - wx) + c11[i] * wx) * wy
                for i in range(4)
            )
            corners.append(blended)
        uo, vo, u10, v10 = tuple(a * (1 - wt) + b * wt for a, b in zip(*corners))

        current_ms, current_deg = _uv_to_speed_bearing(uo, vo)
        wind_ms, wind_deg = _uv_to_speed_bearing(u10, v10)
        return {
            "current": {"speed_ms": current_ms, "direction_deg": current_deg,
                        "measured": True},
            "wind": {"speed_ms": wind_ms, "direction_deg": wind_deg,
                     "measured": True},
            "sampled_at": datetime.fromtimestamp(t0 * (1 - wt) + t1 * wt,
                                                 timezone.utc).isoformat(),
        }


# --- the service ------------------------------------------------------------

def _grid_provider():
    """
    The committed grid, if one has been added. Cached per path so a scan does
    not re-read the file per sample; absence is cached too, since the usual
    answer is that there is no file.
    """
    if not ENVIRONMENT_DIR.is_dir():
        return None, "No data/environment directory — no historical dataset added."
    files = sorted(ENVIRONMENT_DIR.glob("*.csv"))
    if not files:
        return None, ("No historical environmental dataset is committed. See "
                      "backend/data/environment/PROVENANCE.md for the region, "
                      "window and variables one must cover.")
    if len(files) > 1:
        return None, (f"{len(files)} grid files present ({', '.join(f.name for f in files)}); "
                      "exactly one is expected, so none was used.")
    return _cached_provider(files[0]), None


_PROVIDER_CACHE = {}


def _cached_provider(path):
    key = str(path)
    if key not in _PROVIDER_CACHE:
        _PROVIDER_CACHE[key] = GridFileProvider(path)
    return _PROVIDER_CACHE[key]


def reset_provider_cache():
    """Drop the cached grid. For tests, and for a file added while running."""
    _PROVIDER_CACHE.clear()


FALLBACK = AssumedConstantProvider()


def get_conditions(lat, lon, when):
    """
    Current, wind and the drift they imply at one place and time.

    Always answers. `environment_mode` says whether the answer came from a
    dataset or from the stated assumptions, and `environment_reason` says why
    when it did not.
    """
    provider, reason = _grid_provider()
    sample, source = None, FALLBACK

    if provider is not None:
        try:
            sample = provider.conditions_at(lat, lon, when)
            if sample is None:
                reason = (f"The point ({lat}, {lon}) at {when} is outside the "
                          f"dataset's coverage {provider.coverage}.")
            else:
                source = provider
        except Exception as exc:
            # A malformed grid must not take the app down, and must not be
            # quietly treated as "no data" either — the reason names it.
            reason = f"Could not read {provider.name}: {type(exc).__name__}: {exc}"
            sample = None

    if sample is None:
        sample = FALLBACK.conditions_at(lat, lon, when)

    current, wind = sample["current"], sample["wind"]
    measured = current["measured"] and wind["measured"]
    speed_kmh, direction_deg = combine_current_and_wind(
        current["speed_ms"], current["direction_deg"],
        wind["speed_ms"], wind["direction_deg"])

    return {
        "environment_mode": "historical" if measured else "fallback",
        "environment_reason": None if measured else reason,
        "requested": {"latitude": lat, "longitude": lon, "when": str(when)},
        "sampled_at": sample["sampled_at"],
        "current": current,
        "wind": wind,
        "drift": {
            "speed_kmh": speed_kmh,
            "direction_deg": direction_deg,
            "windage": WIND_DRIFT_FACTOR,
            "basis": (f"Current + {WIND_DRIFT_FACTOR:.0%} windage, summed as vectors."
                      + ("" if measured else
                         " Both inputs are stated assumptions, not observations.")),
        },
        "source": source.name,
        "resolution": source.resolution,
        "coverage": source.coverage,
        "measured": measured,
        "note": ("A historical reanalysis is itself a model output. Using one makes "
                 "the drift physically informed, not validated — no accuracy claim "
                 "is made from it."),
    }
