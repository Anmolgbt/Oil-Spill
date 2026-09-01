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

from core.config import (AIS_REFERENCE_FILE, RISK_FORECAST_HOURS,
                         RISK_SAFETY_BUFFER_KM, SIMULATION_DIR, SIMULATION_SEED)
from services.damage import impact_envelope
from services.geo import angle_diff, bearing_deg, destination, haversine_km
from services.t3_simulation import CLEAN_POOL_DIR, write_t3_snapshot

FLEET_FILE = SIMULATION_DIR / "fleet.json"
SNAPSHOTS_DIR = SIMULATION_DIR / "snapshots"

FLEET_SIZE = 10
# A real, historically busy patch of Gulf traffic. This is only used to pick a
# CLUSTER out of the corpus — the vessels' own recorded coordinates, speed and
# course are what gets used everywhere downstream.
CLUSTER_CENTER_LAT = 28.57
CLUSTER_CENTER_LON = -94.80
CLUSTER_RADIUS_KM = 60
MIN_TRACK_POINTS = 30
MIN_TRACK_RANGE_KM = 1.5   # excludes vessels that barely moved (e.g. moored)

# The fleet is deliberately NOT one tight huddle: a huddle puts every vessel
# inside the spill's own impact envelope by construction, so nothing ever reads
# as "safe". The cluster is split using each vessel's own recorded end-of-
# session position, course and speed (real values, nothing invented):
#   NEAR         within NEAR_KM of the centre — where an oil-positive tile is
#                most demo-plausible, and the immediate neighbours of a spill.
#   CROSSING     starts in clear water, but projecting its own recorded course
#                and speed forward runs it into the zone.
#   MOVING AWAY  starts clear and never comes near the zone at all.
NEAR_KM = 30
# Only as many source candidates as can actually leak (T3_OIL_MAX). Every extra
# one consumes a vessel that would otherwise be traffic — and in this corpus the
# vessels nearest the anchorage are exactly the ones whose courses converge on
# it, so taking three sources left nothing to approach the spill.
NEAR_COUNT = 2
CROSS_COUNT = 4

# Two vessels leaking on top of each other is one spill drawn twice: the
# envelopes overlap, the two hindcasts land in the same water, and the response
# ranking has nothing to tell apart. Sources must therefore be far enough apart
# that their impact envelopes do not touch — which is a function of the envelope
# radius, not a fixed number.
def min_source_separation_km():
    return 2 * impact_envelope(PASS_INTERVAL_HOURS)["radius_km"] + 2

# Vessels kept out of the demo fleet by name/MMSI. Not a data-quality
# judgement — just fleet composition for the walkthrough.
EXCLUDE_MMSI = {
    636017298,   # KIDAN
    367441520,   # CAPT NICHOLAS
}

# CROSSING and MOVING-AWAY vessels must start beyond the spill's own impact
# envelope plus the reroute safety buffer, or they are inside the zone from the
# first frame and there is no approach to show. Derived from the envelope rather
# than fixed, because the envelope is sized from the assumed drift and the pass
# interval — a hardcoded standoff silently stops matching when either changes,
# which is how a 18 km constant tuned for an 11 km envelope ended up excluding
# every vessel that actually converges on a 5.6 km one.
def far_min_km():
    return impact_envelope(PASS_INTERVAL_HOURS)["radius_km"] + RISK_SAFETY_BUFFER_KM

MAX_SEGMENT_GAP_HOURS = 3   # splits a vessel's history into contiguous sessions
MAX_TRACK_POINTS = 80       # downsample cap per vessel, so the file stays small

# Revisit cadence, and the window the three passes span (t1 -> t3).
#
# This is 4 h rather than 8 h because of what the corpus actually contains. A
# vessel only appears to move between passes if its recorded session covers the
# whole t1..t3 window; at 8 h that window is 16 h, and only 8 vessels in the
# corpus hold a contiguous 16 h session, which is too few to fill the fleet.
# The result was every vessel frozen at the same coordinates on t1 and t2. At
# 4 h the window is 8 h and about 22 vessels qualify, so the fleet genuinely
# moves between passes. The interval also bounds spill age and therefore the
# impact envelope, so shortening it shrinks the envelope too.
PASS_INTERVAL_HOURS = 4
SNAPSHOT_IDS = ["t1", "t2", "t3"]

# A vessel's session must cover the whole pass window, with margin, or it has
# no fixes to report on the early passes and sits motionless there.
PASS_WINDOW_HOURS = PASS_INTERVAL_HOURS * (len(SNAPSHOT_IDS) - 1)
MIN_SESSION_SPAN_HOURS = PASS_WINDOW_HOURS + 1

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


def vessel_profile(corpus):
    """
    One row per vessel describing the state the demo will actually plot: the
    LAST fix of the contiguous session build_ship_track() keeps, not the mean of
    the vessel's whole multi-month history. Selecting on the mean was wrong —
    a vessel whose average position is 18 km out can finish its session right
    next to the cluster centre, which is how "far" vessels ended up inside the
    spill zone on the map.
    """
    rows = []
    for mmsi, vessel in corpus.groupby("MMSI"):
        vessel = vessel.sort_values("BaseDateTime").reset_index(drop=True)
        start, end = _longest_contiguous_segment(list(vessel["BaseDateTime"]))
        segment = vessel.iloc[start:end]
        if len(segment) < MIN_TRACK_POINTS:
            continue
        span_hours = ((segment["BaseDateTime"].iloc[-1] - segment["BaseDateTime"].iloc[0])
                      .total_seconds() / 3600)
        final = segment.iloc[-1]
        first = vessel.iloc[0]
        rows.append({
            "MMSI": mmsi,
            "n": len(segment),
            "span_hours": span_hours,
            "lat": float(final["LAT"]), "lon": float(final["LON"]),
            "course": float(final["COG"]), "speed_kt": float(final["SOG"]),
            "range_km": haversine_km(segment["LAT"].min(), segment["LON"].min(),
                                      segment["LAT"].max(), segment["LON"].max()),
            # A vessel the corpus actually identifies: named, typed and
            # dimensioned. The spill sources are picked from these so the demo
            # names a real vessel, and so the response-priority score has a
            # real size to weigh instead of a missing one.
            "identified": bool(pd.notna(first["VesselName"])
                               and pd.notna(first["Length"])
                               and pd.notna(first["VesselType"])),
        })

    profile = pd.DataFrame(rows)
    profile["dist_km"] = profile.apply(
        lambda r: haversine_km(CLUSTER_CENTER_LAT, CLUSTER_CENTER_LON, r["lat"], r["lon"]), axis=1)
    profile["heading_offset"] = profile.apply(
        lambda r: angle_diff(r["course"],
                             bearing_deg(r["lat"], r["lon"],
                                         CLUSTER_CENTER_LAT, CLUSTER_CENTER_LON)), axis=1)
    return profile


def _projected_endpoint(row):
    """Where this vessel gets to holding its final course/speed for the risk
    horizon — the same straight-line projection services/risk.py uses."""
    run_km = row["speed_kt"] * 1.852 * RISK_FORECAST_HOURS
    return destination(row["lat"], row["lon"], run_km, row["course"])


def _approach_km(row, targets):
    """
    Closest the vessel's projected track comes to any possible spill point.

    This is the criterion the risk engine itself applies, so selecting on it
    picks vessels that genuinely do (or genuinely do not) transit the area,
    rather than guessing from a heading angle.
    """
    end = _projected_endpoint(row)
    # Point-to-segment distance, walked in small steps — the leg is long
    # (hours of transit) and this keeps the maths obvious.
    steps = 60
    best = float("inf")
    for i in range(steps + 1):
        lat = row["lat"] + (end[0] - row["lat"]) * i / steps
        lon = row["lon"] + (end[1] - row["lon"]) * i / steps
        for target in targets:
            best = min(best, haversine_km(lat, lon, target["lat"], target["lon"]))
    return best


def select_cluster(corpus):
    """
    ~FLEET_SIZE real vessels split into NEAR / CROSSING / MOVING AWAY by the
    position and course each one actually ends its session on, so the fleet
    isn't one huddle where every vessel is trivially inside whatever spill
    appears.

    A spill lands on a NEAR vessel's own position, so the far buckets are
    measured from the NEAR vessels themselves, not from the nominal centre —
    that is what actually guarantees clear water between a vessel and the zone.
    """
    profile = vessel_profile(corpus)
    eligible = profile[(profile["dist_km"] <= CLUSTER_RADIUS_KM)
                       & (profile["range_km"] >= MIN_TRACK_RANGE_KM)
                       # Must be reporting across the whole pass window, or the
                       # vessel is frozen in place on the early passes.
                       & (profile["span_hours"] >= MIN_SESSION_SPAN_HOURS)
                       & (~profile["MMSI"].isin(EXCLUDE_MMSI))]

    # Spill sources come from identified vessels only — an unnamed, undimensioned
    # contact makes for a poor "who spilled" story and leaves the priority score
    # with no vessel size to weigh — and must be spread out, so two leaks are
    # two separate incidents rather than one circle drawn twice.
    near = eligible[(eligible["dist_km"] <= NEAR_KM)
                    & eligible["identified"]].sort_values("dist_km")

    sources = []
    for _, row in near.iterrows():
        if all(haversine_km(row["lat"], row["lon"], s["lat"], s["lon"])
               >= min_source_separation_km() for s in sources):
            sources.append(row)
        if len(sources) >= NEAR_COUNT:
            break

    near_rows = pd.DataFrame(sources) if sources else near.head(NEAR_COUNT)
    selected = near_rows["MMSI"].tolist()

    def clear_of_near(row):
        """Kilometres to the closest possible spill point (a NEAR vessel)."""
        return min(haversine_km(row["lat"], row["lon"], n["lat"], n["lon"])
                   for _, n in near_rows.iterrows())

    targets = [{"lat": n["lat"], "lon": n["lon"]} for _, n in near_rows.iterrows()]
    rest = eligible[~eligible["MMSI"].isin(selected)].copy()
    rest["clear_km"] = rest.apply(clear_of_near, axis=1)
    rest["approach_km"] = rest.apply(lambda r: _approach_km(r, targets), axis=1)
    far = rest[rest["clear_km"] >= far_min_km()]

    # CROSSING: starts in clear water but its projected track runs into the
    # zone. MOVING AWAY: never comes near it at all.
    #
    # The threshold is TWICE the envelope because the risk engine tests against
    # the union of the current envelope AND the forward forecast polygons, which
    # reach further downdrift than the envelope alone. Matching that here keeps
    # selection and assessment consistent — a vessel picked as CROSSING is one
    # the engine will actually flag.
    envelope_km = impact_envelope(PASS_INTERVAL_HOURS)["radius_km"]
    crossing = far[far["approach_km"] <= envelope_km * 2].sort_values("approach_km")
    moving_away = far[far["approach_km"] > envelope_km * 2].sort_values(
        "clear_km", ascending=False)

    selected += [m for m in crossing["MMSI"].tolist() if m not in selected][:CROSS_COUNT]
    remaining = FLEET_SIZE - len(selected)
    selected += [m for m in moving_away["MMSI"].tolist() if m not in selected][:remaining]

    # A bucket can come up short — this corpus is spatially concentrated and
    # real traffic does not always oblige. Fall back to the vessels furthest
    # from the NEAR trio, which is still the most useful thing to show.
    remaining = FLEET_SIZE - len(selected)
    if remaining > 0:
        for mmsi in rest.sort_values("clear_km", ascending=False)["MMSI"].tolist():
            if mmsi not in selected:
                selected.append(mmsi)
            if len(selected) >= FLEET_SIZE:
                break

    return selected[:FLEET_SIZE]


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
            # Real recorded dimensions where the corpus has them. Used only as a
            # size proxy when ranking response priority — never as a volume.
            "length_m": (float(first_row["Length"]) if pd.notna(first_row["Length"])
                         else None),
            "width_m": (float(first_row["Width"]) if pd.notna(first_row["Width"])
                        else None),
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
        # Oil only ever lands on a NEAR-cluster vessel (ship1..NEAR_COUNT, in
        # select_cluster's own ordering) — keeps the spill's location tied to
        # the cluster core the CROSSING/MOVING-AWAY vessels are plotted against.
        near_ids = [f"ship{i}" for i in range(1, NEAR_COUNT + 1)]
        assignments = write_t3_snapshot(fleet["ships"], oil_eligible_ids=near_ids)
        oil_ships = [a["ship_id"] for a in assignments
                     if a["ground_truth_for_simulation"] == "oil"]
        print(f"  t3: {len(assignments)} tiles written, seed={fleet['simulation_seed']}, "
              f"oil-positive (ground truth, debug only): {oil_ships}")
    print("Done.")


if __name__ == "__main__":
    main()
