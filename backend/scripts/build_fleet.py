"""
Build the monitored fleet and fill the earlier satellite passes.

FLEET DATA IS SYNTHETIC. The bundled AIS corpus (data/ais_reference/) is US Gulf
of Mexico traffic and contains no Indian-flag vessels, so an Indian fleet cannot
be drawn from it. These five vessels, their MMSIs, names and tracks are invented
for the demo AOI off the Gujarat coast. What stays real:

* the CNN classifies real Sentinel-1 SAR tiles;
* the Isolation Forest genuinely scores these tracks - the behaviour scores are
  real model output over synthetic input, not hand-written numbers;
* the anomaly 0-100 scale is still normalised against the real AIS corpus.

Routes are straight transits at constant course so the map reads clearly, with
one vessel making a course change and slowdown mid-window. That manoeuvre is
generated, but the anomaly score it earns is the model's own verdict.

Satellite passes are 8 h apart, which is also what bounds the spill age: a tile
that was clean on the previous pass and oily on this one holds oil at most one
revisit old.

Run from the backend/ directory:
    python scripts/build_fleet.py
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from math import cos, radians, sin
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from core.config import SIMULATION_DIR

FLEET_FILE = SIMULATION_DIR / "fleet.json"
SNAPSHOTS_DIR = SIMULATION_DIR / "snapshots"

# Satellite revisit cadence. Also the age bound for a newly-appeared spill.
PASS_INTERVAL_HOURS = 8
FIRST_PASS = datetime(2026, 3, 14, 6, 0, tzinfo=timezone.utc)
SNAPSHOT_IDS = ["t0", "t1", "t2"]

AIS_INTERVAL_MIN = 15
KM_PER_DEG_LAT = 110.574
KT_TO_KMH = 1.852


def km_per_deg_lon(lat):
    return 111.320 * cos(radians(lat))


# Arabian Sea, off the Saurashtra / Gujarat coast. Start points are spread so the
# vessels stay tens of km apart instead of overlapping on the map.
# Start points sit inshore of the AOI and every course heads out to open sea, so
# no track ever runs onto the Saurashtra coast.
#  id,     mmsi,      name,              type,            lat,   lon,   course, kt,  event
FLEET = [
    ("ship1", 419001234, "MV Sagar Deep",     "Crude Oil Tanker", 21.90, 68.60, 250, 11.5, None),
    ("ship2", 419002345, "MT Kandla Pride",   "Product Tanker",   21.30, 69.90, 215, 9.8,  None),
    ("ship3", 419003456, "MV Gujarat Star",   "Bulk Carrier",     20.40, 70.60, 260, 12.6, None),
    ("ship4", 419004567, "MT Okha Voyager",   "Chemical Tanker",  19.90, 68.20, 300, 10.4, None),
    ("ship5", 419005678, "MV Dwarka Prime",   "Crude Oil Tanker", 20.95, 69.25, 235, 8.6,  "turn_and_slow"),
]


def _track(lat, lon, course, speed_kt, event, start, hours):
    """Straight transit at constant course, optionally with one manoeuvre."""
    steps = int(hours * 60 / AIS_INTERVAL_MIN) + 1
    turn_at = steps // 2
    points = []
    for i in range(steps):
        when = start + timedelta(minutes=AIS_INTERVAL_MIN * i)
        if event == "turn_and_slow" and i >= turn_at:
            # Course change then near-stop: the vessel loiters instead of
            # transiting. A realistic discharge profile, and a clear behavioural
            # break for the anomaly model - whatever score it earns is the
            # model's own verdict, not a set value.
            crs, spd = (course + 46) % 360, 1.4
        else:
            crs, spd = course, speed_kt

        points.append({
            "time": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lat": round(lat, 5), "lon": round(lon, 5),
            "speed_kt": round(spd, 1), "course_deg": round(float(crs), 1),
        })

        leg = spd * KT_TO_KMH * (AIS_INTERVAL_MIN / 60)
        lat += leg * cos(radians(crs)) / KM_PER_DEG_LAT
        lon += leg * sin(radians(crs)) / km_per_deg_lon(lat)
    return points


def build_fleet():
    snapshot_times = {
        sid: (FIRST_PASS + timedelta(hours=PASS_INTERVAL_HOURS * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i, sid in enumerate(SNAPSHOT_IDS)
    }
    # Tracks cover the newest pass back through the hindcast window and its
    # search margin — enough for the investigation, short enough that vessels
    # stay inside the AOI instead of transiting hundreds of km off the map.
    track_hours = 14
    last_pass = FIRST_PASS + timedelta(hours=PASS_INTERVAL_HOURS * (len(SNAPSHOT_IDS) - 1))
    track_start = last_pass - timedelta(hours=track_hours)

    ships = []
    for ship_id, mmsi, name, vtype, lat, lon, course, speed, event in FLEET:
        track = _track(lat, lon, course, speed, event, track_start, track_hours)
        last = track[-1]
        ships.append({
            "id": ship_id, "mmsi": mmsi, "name": name, "vessel_type": vtype,
            "image_filename": f"{ship_id}.jpg",
            "latitude": last["lat"], "longitude": last["lon"],
            "speed_kt": last["speed_kt"], "course_deg": last["course_deg"],
            "track_points": len(track), "track": track,
        })

    return {
        "note": ("SYNTHETIC FLEET. Vessel identities and tracks are invented for the "
                 "Gujarat demo AOI; the bundled AIS corpus is US Gulf traffic and has "
                 "no Indian-flag vessels. Behaviour scores are still produced by the "
                 "trained Isolation Forest running over these tracks."),
        "synthetic": True,
        "region": "Arabian Sea — off the Gujarat coast (demo AOI)",
        "pass_interval_hours": PASS_INTERVAL_HOURS,
        "ais_interval_minutes": AIS_INTERVAL_MIN,
        "snapshot_times": snapshot_times,
        "ships": ships,
    }


# --- real SAR tiles for the clean passes -------------------------------------

RAW_BASE = ("https://raw.githubusercontent.com/Saisamarth21/"
            "Oil-Spill-Detection-in-Marine-Environments-Using-AIS-and-Satellite-Data/main")
TREE_API = ("https://api.github.com/repos/Saisamarth21/"
            "Oil-Spill-Detection-in-Marine-Environments-Using-AIS-and-Satellite-Data/"
            "git/trees/main?recursive=1")


def _clean_tile_paths(limit):
    with urllib.request.urlopen(TREE_API, timeout=60) as resp:
        tree = json.load(resp)["tree"]
    paths = sorted(t["path"] for t in tree
                   if t["type"] == "blob" and t["path"].startswith("SAR Image Dataset/0/"))
    stride = max(1, len(paths) // limit)
    return [paths[i * stride] for i in range(limit)]


def fill_clean_snapshots(passes=("t0", "t1")):
    """Real 'no oil' SAR tiles for the earlier passes. t2 is never touched."""
    needed = len(FLEET) * len(passes)
    print(f"  fetching {needed} clean SAR tiles...")
    paths = _clean_tile_paths(needed)
    i = 0
    for snapshot in passes:
        folder = SNAPSHOTS_DIR / snapshot
        folder.mkdir(parents=True, exist_ok=True)
        for ship in FLEET:
            url = f"{RAW_BASE}/{urllib.parse.quote(paths[i])}"
            with urllib.request.urlopen(url, timeout=60) as resp:
                (folder / f"{ship[0]}.jpg").write_bytes(resp.read())
            i += 1
        print(f"  {snapshot}: {len(FLEET)} real SAR tiles written")


def main():
    fleet = build_fleet()
    FLEET_FILE.write_text(json.dumps(fleet, indent=1))
    print(f"wrote {FLEET_FILE}")
    for s in fleet["ships"]:
        print(f"  {s['id']}  {s['name']:18} MMSI {s['mmsi']}  "
              f"{s['latitude']:.3f},{s['longitude']:.3f}  {s['track_points']} fixes")
    print("passes:", fleet["snapshot_times"])

    if "--skip-images" not in sys.argv:
        fill_clean_snapshots()
    print("Done.")


if __name__ == "__main__":
    main()
