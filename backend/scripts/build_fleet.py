"""
Build the monitored fleet from the REAL AIS corpus.

Earlier drafts of this demo invented a Gujarat fleet because the bundled AIS
corpus (data/ais_reference/ais_dataset.csv) is US Gulf of Mexico traffic. That
was flagged as a problem: it rewrote real Gulf coordinates and presented them
as if they were Indian-flag vessels. This script no longer does that.

What it does instead:

* Selects a geographically tight cluster of ~30 REAL vessels from the corpus
  (real MMSI, real name/type where recorded, real lat/lon/speed/course).
* For each vessel, keeps its longest contiguous AIS session (no big time gaps)
  so the track reads as one continuous voyage on the map, downsampled to a
  sane number of fixes rather than dumping the vessel's entire multi-month
  history.
* Re-indexes each vessel's own timestamps onto a shared demo clock (three
  satellite passes, t1/t2/t3, PASS_INTERVAL_HOURS apart) so the fleet can be
  "observed" together. The SHIFT is a constant offset per vessel — the actual
  recorded order, spacing, speed and course between fixes are untouched. This
  is a scheduling artefact of the demo, not an invented position.
* Builds real, all-clean SAR tiles for t1 and t2, and hands t3 to the seeded
  simulation in services/t3_simulation.py, which decides which vessels (if
  any) get an oil-positive tile — never this script and never the CNN.

Run from the backend/ directory:
    python scripts/build_fleet.py
"""
import json
import shutil
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from core.config import AIS_REFERENCE_FILE, SIMULATION_DIR, SIMULATION_SEED
from services.geo import haversine_km
from services.t3_simulation import CLEAN_POOL_DIR, write_t3_snapshot

FLEET_FILE = SIMULATION_DIR / "fleet.json"
SNAPSHOTS_DIR = SIMULATION_DIR / "snapshots"

FLEET_SIZE = 10
# A real, historically busy patch of Gulf traffic. This is only used to pick a
# geographically tight CLUSTER out of the corpus — the vessels' own recorded
# coordinates are what gets used everywhere downstream.
CLUSTER_CENTER_LAT = 28.57
CLUSTER_CENTER_LON = -94.80
CLUSTER_RADIUS_KM = 20
MIN_TRACK_POINTS = 30
MIN_TRACK_RANGE_KM = 1.5   # excludes vessels that barely moved (e.g. moored)

MAX_SEGMENT_GAP_HOURS = 3   # splits a vessel's history into contiguous sessions
MAX_TRACK_POINTS = 80       # downsample cap per vessel, so the file stays small

PASS_INTERVAL_HOURS = 8
SNAPSHOT_IDS = ["t1", "t2", "t3"]

# A handful of AIS VesselType codes that show up in this corpus, translated to
# plain text. Anything else is reported as its raw numeric code rather than
# guessed.
VESSEL_TYPE_NAMES = {
    30: "Fishing", 31: "Towing", 32: "Towing (large)", 35: "Military",
    36: "Sailing", 37: "Pleasure Craft", 52: "Tug",
    60: "Passenger", 70: "Cargo", 71: "Cargo — Hazardous A", 79: "Cargo",
    80: "Tanker", 81: "Tanker — Hazardous A", 89: "Tanker",
    90: "Other",
}


def vessel_type_name(code):
    if pd.isna(code):
        return "Unknown"
    code = int(code)
    return VESSEL_TYPE_NAMES.get(code, f"Type {code}")


def _longest_contiguous_segment(times):
    """Indices of the longest run with no gap wider than MAX_SEGMENT_GAP_HOURS."""
    gap = timedelta(hours=MAX_SEGMENT_GAP_HOURS)
    best_start = best_len = 0
    start = 0
    for i in range(1, len(times) + 1):
        if i == len(times) or times[i] - times[i - 1] > gap:
            if i - start > best_len:
                best_start, best_len = start, i - start
            start = i
    return best_start, best_start + best_len


def _downsample(rows, cap):
    if len(rows) <= cap:
        return rows
    step = (len(rows) - 1) / (cap - 1)
    indices = sorted({round(i * step) for i in range(cap)})
    return [rows[i] for i in indices]


def select_cluster(corpus):
    """~FLEET_SIZE real vessels clustered near CLUSTER_CENTER, with enough
    history and enough movement to read as a real route on the map."""
    stats = corpus.groupby("MMSI").agg(
        n=("MMSI", "size"),
        lat=("LAT", "mean"), lon=("LON", "mean"),
        latmin=("LAT", "min"), latmax=("LAT", "max"),
        lonmin=("LON", "min"), lonmax=("LON", "max"),
    ).reset_index()
    stats["dist_km"] = stats.apply(
        lambda r: haversine_km(CLUSTER_CENTER_LAT, CLUSTER_CENTER_LON, r["lat"], r["lon"]), axis=1)
    stats["range_km"] = stats.apply(
        lambda r: haversine_km(r["latmin"], r["lonmin"], r["latmax"], r["lonmax"]), axis=1)

    eligible = stats[(stats["n"] >= MIN_TRACK_POINTS)
                      & (stats["dist_km"] <= CLUSTER_RADIUS_KM)
                      & (stats["range_km"] >= MIN_TRACK_RANGE_KM)]
    eligible = eligible.sort_values("dist_km")
    return eligible.head(FLEET_SIZE)["MMSI"].tolist()


def build_ship_track(vessel_rows, track_end):
    """The vessel's longest contiguous real session, downsampled and re-indexed
    onto the demo clock ending at `track_end`. lat/lon/speed/course are the
    corpus's own recorded values, verbatim."""
    vessel_rows = vessel_rows.sort_values("BaseDateTime").reset_index(drop=True)
    times = list(vessel_rows["BaseDateTime"])
    start, end = _longest_contiguous_segment(times)
    segment = vessel_rows.iloc[start:end]

    rows = segment.to_dict("records")
    rows = _downsample(rows, MAX_TRACK_POINTS)

    shift = track_end - rows[-1]["BaseDateTime"]
    track = [{
        "time": (r["BaseDateTime"] + shift).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lat": round(float(r["LAT"]), 5), "lon": round(float(r["LON"]), 5),
        "speed_kt": round(float(r["SOG"]), 1), "course_deg": round(float(r["COG"]), 1),
    } for r in rows]
    return track


def build_fleet():
    corpus = pd.read_csv(AIS_REFERENCE_FILE, parse_dates=["BaseDateTime"])
    mmsis = select_cluster(corpus)
    if len(mmsis) < FLEET_SIZE:
        print(f"warning: only {len(mmsis)} vessels matched the cluster filters "
              f"(wanted {FLEET_SIZE})")

    last_pass = corpus["BaseDateTime"].max()
    snapshot_times = {
        sid: (last_pass - timedelta(hours=PASS_INTERVAL_HOURS * (len(SNAPSHOT_IDS) - 1 - i)))
        .strftime("%Y-%m-%dT%H:%M:%SZ")
        for i, sid in enumerate(SNAPSHOT_IDS)
    }

    ships = []
    for i, mmsi in enumerate(mmsis, start=1):
        rows = corpus[corpus["MMSI"] == mmsi]
        track = build_ship_track(rows, last_pass)
        last = track[-1]
        first_row = rows.iloc[0]
        ships.append({
            "id": f"ship{i}",
            "mmsi": int(mmsi),
            "name": (first_row["VesselName"] if pd.notna(first_row["VesselName"])
                     else f"VESSEL {mmsi}"),
            "vessel_type": vessel_type_name(first_row["VesselType"]),
            "image_filename": f"ship{i}.jpg",
            "latitude": last["lat"], "longitude": last["lon"],
            "speed_kt": last["speed_kt"], "course_deg": last["course_deg"],
            "track_points": len(track), "track": track,
        })

    return {
        "note": ("REAL AIS FLEET. Vessel identities, MMSIs, coordinates, speed and "
                 "course are taken as recorded in data/ais_reference/ais_dataset.csv "
                 "(Gulf of Mexico traffic) — nothing is invented. Each vessel's own "
                 "recorded timestamps are shifted by a constant per-vessel offset "
                 "onto a shared 3-pass demo clock (t1/t2/t3); the recorded order, "
                 "spacing, speed and course between fixes are untouched."),
        "synthetic": False,
        "coordinates_source": "real_ais",
        "region": "Gulf of Mexico — real AIS traffic cluster (demo AOI)",
        "pass_interval_hours": PASS_INTERVAL_HOURS,
        "snapshot_times": snapshot_times,
        "simulation_seed": SIMULATION_SEED,
        "ships": ships,
    }


def fill_clean_snapshots(ships, passes=("t1", "t2")):
    """t1 and t2: every ship gets a real 'no oil' tile. A small local pool is
    reused across ships (referenced, not endlessly re-downloaded/duplicated)."""
    pool = sorted(CLEAN_POOL_DIR.glob("*.jpg"))
    if not pool:
        raise FileNotFoundError(f"No clean tiles under {CLEAN_POOL_DIR}")

    for snapshot in passes:
        folder = SNAPSHOTS_DIR / snapshot
        folder.mkdir(parents=True, exist_ok=True)
        for i, ship in enumerate(ships):
            source = pool[i % len(pool)]
            shutil.copyfile(source, folder / ship["image_filename"])
        print(f"  {snapshot}: {len(ships)} real no-oil SAR tiles written "
              f"(from a {len(pool)}-image pool)")


def main():
    fleet = build_fleet()
    FLEET_FILE.write_text(json.dumps(fleet, indent=1))
    print(f"wrote {FLEET_FILE}")
    for s in fleet["ships"]:
        print(f"  {s['id']}  {s['name']:20} MMSI {s['mmsi']}  "
              f"{s['latitude']:.3f},{s['longitude']:.3f}  {s['track_points']} fixes")
    print("passes:", fleet["snapshot_times"])

    if "--skip-images" not in sys.argv:
        fill_clean_snapshots(fleet["ships"])
        assignments = write_t3_snapshot(fleet["ships"])
        oil_ships = [a["ship_id"] for a in assignments
                     if a["ground_truth_for_simulation"] == "oil"]
        print(f"  t3: {len(assignments)} tiles written, seed={fleet['simulation_seed']}, "
              f"oil-positive (ground truth, debug only): {oil_ships}")
    print("Done.")


if __name__ == "__main__":
    main()
