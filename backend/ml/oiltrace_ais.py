"""
OILTRACE AI - AIS module
========================
Self-contained, backend-importable module (no notebook state needed).

Pipeline
    raw AIS  ->  clean_ais()  ->  build_features()  ->  AISAnomalyModel.score()
    source region + release window  ->  attribute_vessels()  ->  ranked, explainable candidates
    SAR vessel detections  ->  sar_ais_consistency()  ->  matched / AIS-dark vessels

IMPORTANT (scientific honesty)
    * The anomaly model is UNSUPERVISED. "Anomalous" means "statistically unusual
      compared with the training traffic", not "violated a rule".
    * The attribution score is a PROTOTYPE, hand-weighted heuristic. It is not
      validated against ground-truth spills and is NOT a legal determination.
"""
from __future__ import annotations

import json
import math
import os
import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

__all__ = [
    "AIS_SOG_NA", "AIS_COG_NA", "AIS_HEADING_NA", "FEATURES", "WEIGHTS", "DISCLAIMER",
    "haversine_km", "bearing_deg", "standardize_columns", "clean_ais", "build_features",
    "AISAnomalyModel", "SourceRegion", "interpolate_track", "attribute_vessels",
    "sar_ais_consistency", "to_jsonable",
]

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
AIS_SOG_NA = 102.3        # AIS code: speed over ground "not available"
AIS_COG_NA = 360.0        # AIS code: course over ground "not available"
AIS_HEADING_NA = 511      # AIS code: true heading "not available"
MAX_PLAUSIBLE_SOG = 50.0  # knots; above this a value is treated as corrupt
SEGMENT_GAP_MIN = 15.0    # a gap longer than this starts a new track segment
MIN_DT_MIN = 0.5          # lower bound for dt when converting differences to rates
MAX_INTERP_GAP_MIN = 15.0 # do not interpolate across an AIS gap longer than this

# Behaviour features: location independent on purpose (no lat/lon/raw COG), so a model
# trained on one sea area can score traffic in another.
FEATURES = ["sog", "accel_kn_per_min", "turn_rate_deg_per_min", "speed_mismatch_kn"]

# Attribution weights (must sum to 100) - taken from the OILTRACE specification.
WEIGHTS = {
    "time_match": 20,
    "source_overlap": 25,
    "trajectory": 20,
    "distance": 15,
    "behaviour": 10,
    "ais_consistency": 5,
    "vessel_relevance": 5,
}
assert sum(WEIGHTS.values()) == 100

DISCLAIMER = ("Prototype Attribution Score - an investigation aid, not a legal determination "
              "of responsibility. 'Anomalous' means statistically unusual, not proven wrongdoing.")

_COLUMN_MAP = {
    "mmsi": "mmsi", "basedatetime": "time", "timestamp": "time", "time": "time",
    "datetime": "time", "lat": "lat", "latitude": "lat", "lon": "lon", "lng": "lon",
    "longitude": "lon", "sog": "sog", "speed": "sog", "cog": "cog", "course": "cog",
    "heading": "heading", "vesselname": "vessel_name", "vessel_name": "vessel_name",
    "name": "vessel_name", "vesseltype": "vessel_type", "vessel_type": "vessel_type",
    "status": "status", "imo": "imo", "length": "length", "width": "width",
    "vessel_id": "vessel_id",
}


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (vectorised)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2 in degrees [0, 360) (vectorised)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlon = lon2 - lon1
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return (np.degrees(np.arctan2(x, y)) + 360.0) % 360.0


def _angle_diff(a, b):
    """Smallest absolute difference between two bearings (degrees)."""
    d = np.abs(np.asarray(a, float) - np.asarray(b, float)) % 360.0
    return np.minimum(d, 360.0 - d)


def _local_km(lat, lon, lat0, lon0):
    """Equirectangular projection to km around (lat0, lon0)."""
    x = (np.asarray(lon, float) - lon0) * 111.320 * math.cos(math.radians(lat0))
    y = (np.asarray(lat, float) - lat0) * 110.574
    return x, y


# --------------------------------------------------------------------------
# 1. Cleaning
# --------------------------------------------------------------------------
def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename common AIS column spellings to the canonical lowercase names."""
    rename = {}
    for c in df.columns:
        key = str(c).strip().lower().replace(" ", "")
        if key in _COLUMN_MAP and _COLUMN_MAP[key] not in rename.values():
            rename[c] = _COLUMN_MAP[key]
    out = df.rename(columns=rename).copy()
    missing = [c for c in ("mmsi", "time", "lat", "lon", "sog") if c not in out.columns]
    if missing:
        raise ValueError(f"AIS data is missing required columns: {missing}")
    for c in ("cog", "heading", "vessel_name", "vessel_type", "status"):
        if c not in out.columns:
            out[c] = np.nan
    return out


def _implied_motion(df: pd.DataFrame) -> pd.DataFrame:
    """Add implied speed (knots) / bearing from consecutive positions (df sorted by mmsi,time)."""
    g = df.groupby("mmsi", sort=False)
    plat, plon, ptime = g["lat"].shift(1), g["lon"].shift(1), g["time"].shift(1)
    dt_h = (df["time"] - ptime).dt.total_seconds() / 3600.0
    dist = haversine_km(plat, plon, df["lat"], df["lon"])
    ok = (dt_h > 0) & (dt_h * 60 <= SEGMENT_GAP_MIN)
    df["implied_speed_kn"] = np.where(ok, dist / 1.852 / dt_h.where(dt_h > 0), np.nan)
    df["implied_bearing"] = np.where(ok, bearing_deg(plat, plon, df["lat"], df["lon"]), np.nan)
    # fall back to the NEXT record for the first row of each segment
    nxt_speed = df.groupby("mmsi", sort=False)["implied_speed_kn"].shift(-1)
    nxt_bear = df.groupby("mmsi", sort=False)["implied_bearing"].shift(-1)
    df["implied_speed_kn"] = df["implied_speed_kn"].fillna(nxt_speed)
    df["implied_bearing"] = df["implied_bearing"].fillna(nxt_bear)
    return df


def clean_ais(raw: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Clean raw AIS records.

    * canonical column names, UTC-naive timestamps, de-duplication, sorting
    * drops impossible coordinates (incl. AIS codes lat=91 / lon=181)
    * AIS "not available" codes (SOG 102.3, COG 360, heading 511) are NOT treated as data:
      they are set to NaN, and SOG/COG are then RECOVERED from the position track when possible
    * rows whose SOG cannot be recovered are dropped
    * adds track-segment ids (new segment after a gap > SEGMENT_GAP_MIN)

    Returns (clean_df, report) where report counts what was changed.
    """
    df = standardize_columns(raw)
    rep: Dict[str, int] = {"input_rows": int(len(df))}

    df["time"] = pd.to_datetime(df["time"], errors="coerce", utc=True).dt.tz_localize(None)
    for c in ("lat", "lon", "sog", "cog", "heading"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["mmsi"] = pd.to_numeric(df["mmsi"], errors="coerce")

    before = len(df)
    df = df.dropna(subset=["mmsi", "time", "lat", "lon"])
    df = df[df["lat"].between(-90, 90) & df["lon"].between(-180, 180)]
    df = df[~((df["lat"] == 91) | (df["lon"] == 181) | ((df["lat"] == 0) & (df["lon"] == 0)))]
    rep["dropped_invalid_position_or_time"] = int(before - len(df))

    before = len(df)
    df = df.drop_duplicates(["mmsi", "time"]).sort_values(["mmsi", "time"]).reset_index(drop=True)
    df["mmsi"] = df["mmsi"].astype("int64")
    rep["dropped_duplicates"] = int(before - len(df))

    # --- AIS sentinel codes -> NaN
    sog_bad = df["sog"].isna() | (df["sog"] >= AIS_SOG_NA) | (df["sog"] < 0) | (df["sog"] > MAX_PLAUSIBLE_SOG)
    cog_bad = df["cog"].isna() | (df["cog"] >= AIS_COG_NA) | (df["cog"] < 0)
    rep["sog_sentinel_or_invalid"] = int(sog_bad.sum())
    rep["cog_sentinel_or_invalid"] = int(cog_bad.sum())
    df.loc[sog_bad, "sog"] = np.nan
    df.loc[cog_bad, "cog"] = np.nan
    df.loc[(df["heading"] >= 360) | (df["heading"] < 0), "heading"] = np.nan

    # --- recover SOG / COG from the track
    df = _implied_motion(df)
    can_sog = df["sog"].isna() & df["implied_speed_kn"].between(0, MAX_PLAUSIBLE_SOG)
    df["sog_recovered"] = can_sog
    df.loc[can_sog, "sog"] = df.loc[can_sog, "implied_speed_kn"]
    can_cog = df["cog"].isna() & df["implied_bearing"].notna() & (df["implied_speed_kn"] > 0.5)
    df["cog_recovered"] = can_cog
    df.loc[can_cog, "cog"] = df.loc[can_cog, "implied_bearing"]
    rep["sog_recovered_from_track"] = int(can_sog.sum())
    rep["cog_recovered_from_track"] = int(can_cog.sum())

    before = len(df)
    df = df.dropna(subset=["sog"]).reset_index(drop=True)
    rep["dropped_unrecoverable_sog"] = int(before - len(df))

    # --- segments (split at long gaps)
    gap_min = df.groupby("mmsi", sort=False)["time"].diff().dt.total_seconds() / 60.0
    new_seg = gap_min.isna() | (gap_min > SEGMENT_GAP_MIN)
    df["segment_id"] = new_seg.cumsum().astype("int64")
    rep["output_rows"] = int(len(df))
    rep["vessels"] = int(df["mmsi"].nunique())
    rep["segments"] = int(df["segment_id"].nunique())
    return df, rep


# --------------------------------------------------------------------------
# 2. Behaviour features
# --------------------------------------------------------------------------
def build_features(clean: pd.DataFrame) -> pd.DataFrame:
    """
    Add behaviour features computed ONLY inside a track segment (never across long gaps).
    The first row of every segment has no previous point and gets NaN features.
    """
    df = clean.copy()
    g = df.groupby("segment_id", sort=False)
    dt_min = (g["time"].diff().dt.total_seconds() / 60.0).clip(lower=MIN_DT_MIN)
    d_sog = g["sog"].diff().abs()
    df["accel_kn_per_min"] = d_sog / dt_min
    cog_prev = g["cog"].shift(1)
    turn = _angle_diff(df["cog"], cog_prev)
    # COG is meaningless at (almost) zero speed - do not call a drifting hull "turning"
    slow = (df["sog"] < 0.5) | (g["sog"].shift(1) < 0.5)
    df["turn_rate_deg_per_min"] = np.where(slow, 0.0, turn / dt_min)
    mism = (df["implied_speed_kn"] - df["sog"]).abs()
    df["speed_mismatch_kn"] = mism.fillna(0.0).clip(upper=MAX_PLAUSIBLE_SOG)
    df["dt_min"] = dt_min
    first = g.cumcount() == 0
    for c in ("accel_kn_per_min", "turn_rate_deg_per_min"):
        df.loc[first, c] = np.nan
    df.loc[first, "speed_mismatch_kn"] = np.nan
    return df


# --------------------------------------------------------------------------
# 3. Anomaly model (Isolation Forest + calibrated 0-100 score)
# --------------------------------------------------------------------------
class AISAnomalyModel:
    """
    Isolation Forest on FEATURES with a FIXED score calibration learned on the training data.

    score_0_100 = 0 at the training median "unusualness", 100 at the training 99.5th percentile
    (clipped). Because the calibration is stored, scores are comparable across calls/candidates -
    unlike per-batch min-max normalisation.
    """

    def __init__(self, n_estimators: int = 300, contamination: float = 0.02, random_state: int = 42):
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.random_state = random_state
        self.scaler = None
        self.detector = None
        self.calib = None
        self.meta: Dict = {}

    @staticmethod
    def _matrix(feat: pd.DataFrame) -> pd.DataFrame:
        x = feat[FEATURES].replace([np.inf, -np.inf], np.nan)
        return x

    def fit(self, feat: pd.DataFrame) -> "AISAnomalyModel":
        import sklearn
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler

        x = self._matrix(feat).dropna()
        self.scaler = StandardScaler().fit(x.values)
        self.detector = IsolationForest(
            n_estimators=self.n_estimators, contamination=self.contamination,
            random_state=self.random_state, n_jobs=-1,
        ).fit(self.scaler.transform(x.values))
        raw = -self.detector.decision_function(self.scaler.transform(x.values))
        self.calib = {"lo": float(np.percentile(raw, 50)), "hi": float(np.percentile(raw, 99.5))}
        self.meta = {
            "features": FEATURES,
            "n_training_rows": int(len(x)),
            "contamination": self.contamination,
            "n_estimators": self.n_estimators,
            "sklearn_version": sklearn.__version__,
            "calibration": self.calib,
            "score_definition": "0 = training-median unusualness, 100 = training 99.5th percentile (clipped)",
        }
        return self

    def score(self, feat: pd.DataFrame) -> pd.DataFrame:
        """Return DataFrame(index=feat.index) with anomaly_score (0-100) and is_anomaly (bool).
        Rows with missing features get score NaN / is_anomaly False."""
        x = self._matrix(feat)
        ok = x.notna().all(axis=1)
        out = pd.DataFrame({"anomaly_score": np.nan, "is_anomaly": False}, index=feat.index)
        if ok.any():
            xs = self.scaler.transform(x[ok].values)
            raw = -self.detector.decision_function(xs)
            lo, hi = self.calib["lo"], self.calib["hi"]
            out.loc[ok, "anomaly_score"] = 100.0 * np.clip((raw - lo) / (hi - lo), 0, 1)
            out.loc[ok, "is_anomaly"] = self.detector.predict(xs) == -1
        return out

    def save(self, directory: str, name: str = "ais_anomaly_model") -> str:
        import joblib
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{name}.joblib")
        joblib.dump({"scaler": self.scaler, "detector": self.detector, "calib": self.calib,
                     "meta": self.meta}, path)
        with open(os.path.join(directory, f"{name}_meta.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, indent=2)
        return path

    @classmethod
    def load(cls, path: str) -> "AISAnomalyModel":
        import joblib
        import sklearn
        blob = joblib.load(path)
        m = cls()
        m.scaler, m.detector, m.calib, m.meta = blob["scaler"], blob["detector"], blob["calib"], blob["meta"]
        trained = m.meta.get("sklearn_version")
        if trained and trained != sklearn.__version__:
            warnings.warn(f"Model trained with scikit-learn {trained}, running {sklearn.__version__}. "
                          "Pin the version or retrain.")
        if list(m.meta.get("features", [])) != FEATURES:
            raise ValueError("Saved model feature list does not match oiltrace_ais.FEATURES")
        return m


# --------------------------------------------------------------------------
# 4. Source region + track interpolation
# --------------------------------------------------------------------------
@dataclass
class SourceRegion:
    """Probable source region produced by the backward hindcast (a probabilistic REGION, not a point)."""
    lat: float
    lon: float
    radius_km: float
    polygon: Optional[Sequence[Tuple[float, float]]] = None  # optional [(lat, lon), ...]

    def distance_km(self, lat, lon):
        return haversine_km(self.lat, self.lon, lat, lon)

    def _inside_polygon(self, lat, lon):
        px, py = _local_km(lat, lon, self.lat, self.lon)
        vx, vy = _local_km([p[0] for p in self.polygon], [p[1] for p in self.polygon], self.lat, self.lon)
        inside = np.zeros(np.shape(px), dtype=bool)
        n = len(vx)
        j = n - 1
        for i in range(n):
            cond = ((vy[i] > py) != (vy[j] > py)) & (
                px < (vx[j] - vx[i]) * (py - vy[i]) / (vy[j] - vy[i] + 1e-12) + vx[i])
            inside ^= cond
            j = i
        return inside

    def membership(self, lat, lon):
        """Soft membership in [0,1]: 1 inside the region, falling linearly to 0 at 2x the radius."""
        d = self.distance_km(lat, lon)
        m = np.clip(1.0 - (d - self.radius_km) / max(self.radius_km, 1e-6), 0.0, 1.0)
        if self.polygon:
            m = np.maximum(m, self._inside_polygon(lat, lon).astype(float))
        return m


def interpolate_track(vessel: pd.DataFrame, times: pd.DatetimeIndex,
                      max_gap_min: float = MAX_INTERP_GAP_MIN) -> pd.DataFrame:
    """
    Linearly interpolate a vessel's lat/lon at `times`.
    `covered` is False outside the observed span or where the bracketing AIS reports are more than
    `max_gap_min` apart (we never invent positions across an AIS gap).
    """
    v = vessel.sort_values("time")
    t_obs = v["time"].values.astype("datetime64[s]").astype("int64").astype(float)
    t_q = pd.DatetimeIndex(times).values.astype("datetime64[s]").astype("int64").astype(float)
    out = pd.DataFrame({"time": pd.DatetimeIndex(times)})
    if len(v) < 2:
        out["lat"] = np.nan
        out["lon"] = np.nan
        out["covered"] = False
        return out
    out["lat"] = np.interp(t_q, t_obs, v["lat"].values, left=np.nan, right=np.nan)
    out["lon"] = np.interp(t_q, t_obs, v["lon"].values, left=np.nan, right=np.nan)
    idx = np.searchsorted(t_obs, t_q, side="right")
    lo = np.clip(idx - 1, 0, len(t_obs) - 1)
    hi = np.clip(idx, 0, len(t_obs) - 1)
    bracket_gap_min = (t_obs[hi] - t_obs[lo]) / 60.0
    exact = np.isin(t_q, t_obs)
    out["covered"] = (~np.isnan(out["lat"].values)) & ((bracket_gap_min <= max_gap_min) | exact)
    out.loc[~out["covered"], ["lat", "lon"]] = np.nan
    return out


# --------------------------------------------------------------------------
# 5. Attribution engine
# --------------------------------------------------------------------------
_RELEVANCE = [  # (low, high, score, label)
    (80, 89, 1.00, "Tanker"),
    (70, 79, 0.70, "Cargo ship"),
    (90, 99, 0.40, "Other"),
    (60, 69, 0.30, "Passenger"),
    (30, 30, 0.30, "Fishing"),
    (31, 32, 0.45, "Towing"),
    (52, 52, 0.45, "Tug"),
    (35, 35, 0.20, "Military"),
    (36, 37, 0.10, "Pleasure craft"),
]


def _vessel_relevance(vessel_type) -> Tuple[float, str]:
    """Heuristic: how plausible is this ship class as an oil source? Unknown type -> neutral 0.4."""
    try:
        t = int(float(vessel_type))
    except (TypeError, ValueError):
        return 0.4, "Unknown type"
    for lo, hi, score, label in _RELEVANCE:
        if lo <= t <= hi:
            return score, label
    return 0.4, f"Type {t}"


def _grade(x: float) -> str:
    return "Excellent" if x >= 0.85 else "Good" if x >= 0.60 else "Fair" if x >= 0.35 else "Poor"


def _level(x: float) -> str:
    return "High" if x >= 0.60 else "Medium" if x >= 0.30 else "Low"


def _hhmm(ts) -> str:
    return pd.Timestamp(ts).strftime("%H:%M")


def attribute_vessels(
    clean: pd.DataFrame,
    region: SourceRegion,
    window_start,
    window_end,
    model: AISAnomalyModel,
    *,
    search_radius_km: float = 20.0,
    pad_min: float = 60.0,
    distance_scale_km: float = 5.0,
    time_tolerance_min: float = 60.0,
    anonymize: bool = False,
    step_min: float = 1.0,
) -> Dict:
    """
    Reconstruct vessel traffic around the PROBABLE SOURCE REGION during the ESTIMATED RELEASE WINDOW
    (not around the observed slick) and rank candidates with an explainable 7-factor score.

    Factors (0-1 each, weights in WEIGHTS):
      time_match       closest approach to the region centre falls inside the release window
                       (linear decay to 0 over `time_tolerance_min` minutes outside it)
      source_overlap   share of the release window the vessel spent inside / near the region
      trajectory       0.5 * path passes through region  +  0.5 * heading aligned with the line to region
      distance         Gaussian decay of the closest distance to centre during the window
      behaviour        mean of the 3 highest calibrated anomaly scores near the window (0-100 -> 0-1)
      ais_consistency  AIS continuity x (1 - share of records with speed/position mismatch)
      vessel_relevance heuristic ship-class plausibility
    """
    w0, w1 = pd.Timestamp(window_start), pd.Timestamp(window_end)
    if w1 <= w0:
        raise ValueError("window_end must be after window_start")
    pad = pd.Timedelta(minutes=pad_min)
    ext0, ext1 = w0 - pad, w1 + pad

    # behaviour scores for every record
    feat = build_features(clean)
    sc = model.score(feat)
    feat = feat.join(sc)

    # --- candidate search: source region x release window (+ padding)
    in_time = clean["time"].between(ext0, ext1)
    sub = clean[in_time]
    near = sub[region.distance_km(sub["lat"].values, sub["lon"].values) <= search_radius_km]
    cand_ids = sorted(near["mmsi"].unique())

    win_times = pd.date_range(w0, w1, freq=f"{int(step_min * 60)}s")
    ext_times = pd.date_range(ext0, ext1, freq=f"{int(step_min * 60)}s")
    results: List[Dict] = []

    for mmsi in cand_ids:
        v_all = clean[(clean["mmsi"] == mmsi) & clean["time"].between(ext0 - pd.Timedelta(minutes=30),
                                                                      ext1 + pd.Timedelta(minutes=30))]
        f_v = feat[(feat["mmsi"] == mmsi) & feat["time"].between(w0 - pd.Timedelta(minutes=30),
                                                                 w1 + pd.Timedelta(minutes=30))]
        trk_w = interpolate_track(v_all, win_times)
        trk_e = interpolate_track(v_all, ext_times)
        cov_w = float(trk_w["covered"].mean()) if len(trk_w) else 0.0
        cov_e = float(trk_e["covered"].mean()) if len(trk_e) else 0.0

        # distances on the extended track
        ce = trk_e[trk_e["covered"]].copy()
        if ce.empty:
            continue
        ce["d"] = region.distance_km(ce["lat"].values, ce["lon"].values)
        i_min = int(ce["d"].values.argmin())
        t_close, d_close_ext = ce["time"].iloc[i_min], float(ce["d"].iloc[i_min])

        # --- time match
        if w0 <= t_close <= w1:
            time_f = 1.0
        else:
            off = (w0 - t_close).total_seconds() / 60 if t_close < w0 else (t_close - w1).total_seconds() / 60
            time_f = float(max(0.0, 1.0 - off / time_tolerance_min))

        # --- source overlap (uncovered minutes count as 0: unknown is not evidence)
        cw = trk_w[trk_w["covered"]]
        if len(cw):
            m_w = region.membership(cw["lat"].values, cw["lon"].values)
            overlap_f = float(m_w.sum() / len(trk_w))
            inside_share = float((region.distance_km(cw["lat"].values, cw["lon"].values) <= region.radius_km).sum()
                                 / len(trk_w))
            d_win = float(region.distance_km(cw["lat"].values, cw["lon"].values).min())
        else:
            overlap_f, inside_share, d_win = 0.0, 0.0, d_close_ext

        # --- distance
        dist_f = float(np.exp(-((d_win / distance_scale_km) ** 2)))

        # --- trajectory
        path_f = float(region.membership(np.array([ce["lat"].iloc[i_min]]), np.array([ce["lon"].iloc[i_min]]))[0])
        near_r = max(3.0 * region.radius_km, 6.0)
        la, lo_ = ce["lat"].values, ce["lon"].values
        if len(ce) >= 3:
            brg_v = bearing_deg(la[:-1], lo_[:-1], la[1:], lo_[1:])
            brg_c = bearing_deg(la[:-1], lo_[:-1], np.full(len(la) - 1, region.lat), np.full(len(la) - 1, region.lon))
            near_mask = ce["d"].values[:-1] <= near_r
            if near_mask.any():
                align = np.abs(np.cos(np.radians(_angle_diff(brg_v, brg_c))))[near_mask]
                align_f = float(align.mean())
            else:
                align_f = 0.0
        else:
            align_f = 0.0
        traj_f = 0.5 * path_f + 0.5 * align_f

        # --- behaviour
        scores = f_v["anomaly_score"].dropna().sort_values(ascending=False)
        top3 = float(scores.head(3).mean()) if len(scores) else 0.0
        beh_f = top3 / 100.0
        anomalous = bool(len(scores) and (beh_f >= 0.5))
        events = []
        for idx in scores.head(3).index:
            r = f_v.loc[idx]
            if r["anomaly_score"] >= 50:
                events.append({"time": _hhmm(r["time"]), "sog_kn": round(float(r["sog"]), 1),
                               "accel_kn_per_min": round(float(r["accel_kn_per_min"]), 2),
                               "turn_rate_deg_per_min": round(float(r["turn_rate_deg_per_min"]), 1),
                               "anomaly_score": round(float(r["anomaly_score"]), 1)})
        events.sort(key=lambda e: e["time"])

        # --- AIS consistency (continuity x plausibility)
        mism_share = float((f_v["speed_mismatch_kn"] > 3.0).mean()) if len(f_v) else 0.0
        cons_f = float(cov_e * (1.0 - mism_share))
        ais_gap = cov_w < 0.8

        # --- relevance
        vtype = v_all["vessel_type"].dropna().iloc[0] if v_all["vessel_type"].notna().any() else np.nan
        rel_f, type_label = _vessel_relevance(vtype)

        factors = {"time_match": time_f, "source_overlap": overlap_f, "trajectory": traj_f,
                   "distance": dist_f, "behaviour": beh_f, "ais_consistency": cons_f,
                   "vessel_relevance": rel_f}
        points = {k: round(WEIGHTS[k] * factors[k], 2) for k in WEIGHTS}
        total = float(sum(points.values()))
        n_strong = sum(1 for k in ("time_match", "source_overlap", "trajectory", "distance") if factors[k] >= 0.6)
        confidence = ("High" if (total >= 75 and cov_w >= 0.6 and n_strong >= 3)
                      else "Medium" if total >= 50 else "Low")
        status = ("High priority" if total >= 75 else "Medium" if total >= 50 else "Low")

        name = v_all["vessel_name"].dropna().iloc[0] if v_all["vessel_name"].notna().any() else None
        label = f"Vessel-{str(int(mmsi))[-4:]}" if (anonymize or not name) else str(name)
        # evidence (explainable)
        ev = []

        def add(key, positive, text):
            ev.append({"factor": key, "score": round(factors[key], 3), "positive": bool(positive), "text": text})

        add("source_overlap", overlap_f >= 0.6,
            f"{'Strong' if overlap_f >= 0.6 else 'Partial' if overlap_f >= 0.3 else 'Weak'} source-region overlap "
            f"({inside_share * 100:.0f}% of the release window inside the region)")
        add("time_match", time_f >= 0.6,
            (f"Release-time match: closest approach at {_hhmm(t_close)} UTC, inside the window"
             if time_f == 1.0 else
             f"Closest approach at {_hhmm(t_close)} UTC is outside the {_hhmm(w0)}-{_hhmm(w1)} release window"))
        add("trajectory", traj_f >= 0.6,
            f"{'High' if traj_f >= 0.6 else 'Moderate' if traj_f >= 0.35 else 'Low'} trajectory similarity "
            f"(path {'crosses' if path_f >= 0.99 else 'passes near' if path_f > 0 else 'misses'} the region)")
        add("distance", dist_f >= 0.6,
            f"{'Close' if dist_f >= 0.6 else 'Distant'} to inferred origin (minimum {d_win:.1f} km during the window)")
        if anomalous and events:
            e0 = max(events, key=lambda e: e["anomaly_score"])
            add("behaviour", True, f"Behaviour anomaly detected near {e0['time']} UTC "
                                   f"(speed {e0['sog_kn']} kn, change {e0['accel_kn_per_min']} kn/min)")
        else:
            add("behaviour", False, "No unusual speed/course behaviour near the release window")
        add("ais_consistency", cons_f >= 0.8 and not ais_gap,
            "AIS continuity acceptable" if (cons_f >= 0.8 and not ais_gap) else
            f"AIS gap/inconsistency: {cov_w * 100:.0f}% of the release window covered by AIS")
        flags = []
        if ais_gap:
            flags.append("AIS gap during release window - requires investigation")
        if mism_share > 0.1:
            flags.append("Reported speed disagrees with position track - requires investigation")

        results.append({
            "vessel_id": f"V{int(mmsi)}", "mmsi": int(mmsi), "vessel_name": label,
            "vessel_type": None if pd.isna(vtype) else int(float(vtype)), "type_label": type_label,
            "attribution_score": round(total, 1), "confidence": confidence, "status": status,
            "factors": {k: round(v, 3) for k, v in factors.items()},
            "points": points,
            "table": {
                "time_match": _grade(time_f), "source_overlap": _level(overlap_f),
                "distance_km": round(d_win, 1), "closest_approach_km": round(d_close_ext, 1),
                "trajectory": _grade(traj_f),
                "behaviour": "Anomalous" if anomalous else "Normal", "status": status,
            },
            "closest_approach": {"time_utc": pd.Timestamp(t_close).isoformat(), "distance_km": round(d_close_ext, 2)},
            "ais_coverage_window": round(cov_w, 3), "ais_coverage_extended": round(cov_e, 3),
            "anomaly_events": events, "evidence": ev, "flags": flags,
            "assessment": ("HIGH-PRIORITY INVESTIGATION CANDIDATE" if status == "High priority"
                           else "MEDIUM-PRIORITY - REVIEW" if status == "Medium" else "LOW PRIORITY"),
            "track": [{"time": pd.Timestamp(r.time).isoformat(), "lat": round(float(r.lat), 5),
                       "lon": round(float(r.lon), 5)} for r in
                      v_all[v_all["time"].between(ext0, ext1)].itertuples()],
        })

    results.sort(key=lambda r: r["attribution_score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return {
        "label": "Prototype Attribution Score",
        "disclaimer": DISCLAIMER,
        "weights": WEIGHTS,
        "region": {"lat": region.lat, "lon": region.lon, "radius_km": region.radius_km},
        "release_window_utc": [w0.isoformat(), w1.isoformat()],
        "search_radius_km": search_radius_km,
        "vessels_found_in_source_region": len(results),
        "candidates": results,
        "model": model.meta,
    }


# --------------------------------------------------------------------------
# 6. SAR <-> AIS consistency
# --------------------------------------------------------------------------
def sar_ais_consistency(
    clean: pd.DataFrame,
    sar_detections: Sequence[Dict],
    acquisition_time,
    *,
    match_radius_km: float = 2.0,
    max_interp_gap_min: float = 20.0,
    footprint_margin_km: float = 30.0,
    footprint: Optional[Dict] = None,
) -> Dict:
    """
    Match ships detected in the SAR scene with AIS positions interpolated to the acquisition time.

    sar_detections: [{"id": "S1", "lat": .., "lon": ..}, ...]
    footprint: optional {"lat":.., "lon":.., "radius_km":..} = SAR scene coverage. AIS vessels outside it are
               ignored. If omitted, the extent of the detections (+ footprint_margin_km) is used.
    A SAR ship with no AIS vessel within `match_radius_km` is a *potential AIS-dark / inconsistent vessel*.
    That is a flag for investigation, never evidence of guilt (AIS can be off for legitimate reasons,
    and SAR positions are only accurate to a few hundred metres).
    """
    from scipy.optimize import linear_sum_assignment

    t_acq = pd.Timestamp(acquisition_time)
    lats = np.array([d["lat"] for d in sar_detections], float)
    lons = np.array([d["lon"] for d in sar_detections], float)
    lat_c, lon_c = (lats.mean(), lons.mean()) if len(lats) else (np.nan, np.nan)

    ais_pos = []
    near_t = clean[clean["time"].between(t_acq - pd.Timedelta(hours=1), t_acq + pd.Timedelta(hours=1))]
    for mmsi, v in near_t.groupby("mmsi"):
        trk = interpolate_track(v, pd.DatetimeIndex([t_acq]), max_gap_min=max_interp_gap_min)
        if bool(trk["covered"].iloc[0]):
            name = v["vessel_name"].dropna().iloc[0] if v["vessel_name"].notna().any() else f"MMSI {int(mmsi)}"
            ais_pos.append({"mmsi": int(mmsi), "name": str(name),
                            "lat": float(trk["lat"].iloc[0]), "lon": float(trk["lon"].iloc[0])})
    # AIS vessels that could plausibly be inside the SAR footprint
    if footprint:
        ais_pos = [a for a in ais_pos
                   if haversine_km(footprint["lat"], footprint["lon"], a["lat"], a["lon"]) <= footprint["radius_km"]]
    elif len(lats):
        span = max(np.ptp(lats) * 110.574, np.ptp(lons) * 111.32) / 2 + footprint_margin_km
        ais_pos = [a for a in ais_pos if haversine_km(lat_c, lon_c, a["lat"], a["lon"]) <= span]

    matches, matched_sar, matched_ais = [], set(), set()
    if len(sar_detections) and len(ais_pos):
        D = np.array([[haversine_km(s["lat"], s["lon"], a["lat"], a["lon"]) for a in ais_pos]
                      for s in sar_detections])
        cost = np.where(D <= match_radius_km, D, 1e6)
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols):
            if D[r, c] <= match_radius_km:
                matched_sar.add(r)
                matched_ais.add(c)
                matches.append({"sar_id": sar_detections[r].get("id", f"S{r + 1}"), "mmsi": ais_pos[c]["mmsi"],
                                "vessel_name": ais_pos[c]["name"], "separation_km": round(float(D[r, c]), 2)})
    dark = [{"sar_id": s.get("id", f"S{i + 1}"), "lat": s["lat"], "lon": s["lon"],
             "flag": "Potential AIS-dark / inconsistent vessel", "action": "Requires Investigation"}
            for i, s in enumerate(sar_detections) if i not in matched_sar]
    ais_only = [{"mmsi": a["mmsi"], "vessel_name": a["name"]}
                for j, a in enumerate(ais_pos) if j not in matched_ais]
    return {
        "acquisition_time_utc": t_acq.isoformat(),
        "sar_detected": len(sar_detections),
        "ais_matched": len(matches),
        "potential_ais_inconsistent": len(dark),
        "matches": matches,
        "unmatched_sar": dark,
        "ais_without_sar_detection": ais_only,
        "match_radius_km": match_radius_km,
        "note": ("An unmatched SAR vessel is a flag for investigation, not evidence of responsibility."),
    }


# --------------------------------------------------------------------------
# JSON helper
# --------------------------------------------------------------------------
def to_jsonable(obj):
    """Recursively convert numpy / pandas objects to plain JSON-safe Python."""
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj
