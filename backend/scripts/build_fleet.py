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
import itertools
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
from services.investigation import FORECAST_DRIFT_SPEED_KMH
from services.geo import angle_diff, bearing_deg, destination, haversine_km
from services.t3_simulation import CLEAN_POOL_DIR, write_t3_snapshot

FLEET_FILE = SIMULATION_DIR / "fleet.json"
SNAPSHOTS_DIR = SIMULATION_DIR / "snapshots"

# Keep the monitored roster to vessels that the source corpus identifies by
# name. The four anonymous records previously shown as "VESSEL <MMSI>" are
# intentionally omitted from the walkthrough.
FLEET_SIZE = 6
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
    369093000,   # KOLT LEVI — the track-quality filter also rejects it (it ran
                 # 194 km to net 38 km), but the exclusion is explicit so the
                 # removal holds if those thresholds are ever retuned.
    636019218,   # unnamed in the corpus (displayed as VESSEL 636019218)
    219025316,   # unnamed in the corpus (displayed as VESSEL 219025316)
    636018579,   # unnamed in the corpus (displayed as VESSEL 636018579)
    477430900,   # unnamed in the corpus (displayed as VESSEL 477430900)
}

# CROSSING and MOVING-AWAY vessels must start outside the obstacle the reroute
# actually routes around, or they begin the demo inside the zone and the map can
# only offer an exit route rather than an approach-and-turn.
#
# That obstacle is NOT just the impact envelope: services/reroute.py buffers the
# union of the envelope AND the forward forecast circles, then circumscribes it.
# Measured, that comes to ~14 km where the envelope alone is 9 km, which is why
# a standoff of envelope + buffer still left every vessel inside. Reconstruct
# the same reach here: envelope + how far the forecast runs + the buffer.
def far_min_km():
    forecast_reach_km = FORECAST_DRIFT_SPEED_KMH * RISK_FORECAST_HOURS
    return (impact_envelope(PASS_INTERVAL_HOURS)["radius_km"]
            + forecast_reach_km + RISK_SAFETY_BUFFER_KM)

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

# Track legibility. A monitored vessel should read as one coherent voyage:
# roughly straight, and covering comparable ground between each pass. See
# _window_quality() for what each term measures.
TRACK_MAX_WANDER = 2.0      # path travelled / net displacement
TRACK_MIN_LEG_KM = 1.5      # the shorter pass-to-pass hop
TRACK_MIN_BALANCE = 0.35    # shorter hop / longer hop

# Real fixes kept BEFORE the displayed window, purely so the grey "where it has
# been" track is not empty on the first pass. Best effort: a vessel with no
# earlier history is still fine, and requiring this would shrink the candidate
# pool below the fleet size.
LEAD_IN_HOURS = 4

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


def _window_quality(window):
    """
    How well one candidate window reads as a coherent voyage.

    * wander  - distance travelled over net displacement. A vessel running a
                survey or holding pattern racks up kilometres without going
                anywhere, which draws as a scribble on the map.
    * min_leg - the shorter of the two pass-to-pass hops. Near zero means the
                vessel is parked for one pass and then leaps on the next.
    * balance - shorter hop over longer hop. Low means the same thing.

    None when the window has too few fixes or the vessel never really moved.
    """
    if len(window) < 4:
        return None

    points = list(zip(window["LAT"], window["LON"]))
    path_km = sum(haversine_km(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
                  for i in range(len(points) - 1))
    net_km = haversine_km(points[0][0], points[0][1], points[-1][0], points[-1][1])
    if net_km <= 0.05:
        return None

    start = window["BaseDateTime"].iloc[0]
    span = (window["BaseDateTime"].iloc[-1] - start).total_seconds() / 3600

    def at(hours_in):
        prior = window[window["BaseDateTime"] <= start + timedelta(hours=hours_in)]
        row = prior.iloc[-1] if len(prior) else window.iloc[0]
        return row["LAT"], row["LON"]

    first_leg = haversine_km(*at(0), *at(span / 2))
    second_leg = haversine_km(*at(span / 2), *at(span))
    longest_leg = max(first_leg, second_leg)

    return {
        "wander": path_km / net_km,
        "min_leg_km": min(first_leg, second_leg),
        "balance": (min(first_leg, second_leg) / longest_leg) if longest_leg > 0 else 0.0,
    }


def _best_window(segment):
    """
    The stretch of this vessel's session that the demo should display.

    Showing the LAST hours of a session is what produced both the scribbled
    tracks and the park-then-leap movement between passes: the end of a
    session is usually the vessel manoeuvring onto a berth or anchor. Sliding
    a window over the session and keeping its best-moving stretch instead
    triples the number of usable vessels at the same pass interval.

    Every coordinate, speed and course stays exactly as recorded — this only
    chooses WHICH real hours of the voyage to show, in the same spirit as the
    per-vessel time shift onto the shared demo clock.

    Returns (window_start, window_end, quality).
    """
    window = timedelta(hours=PASS_WINDOW_HOURS)
    times = segment["BaseDateTime"]
    first, last = times.iloc[0], times.iloc[-1]

    best = None
    starts = pd.date_range(first, last - window, freq="30min")
    for start in starts:
        end = start + window
        quality = _window_quality(segment[(times >= start) & (times <= end)])
        if quality is None:
            continue
        passes = (quality["wander"] <= TRACK_MAX_WANDER
                  and quality["min_leg_km"] >= TRACK_MIN_LEG_KM
                  and quality["balance"] >= TRACK_MIN_BALANCE)
        # Prefer a window that clears every threshold; among those, one with
        # real history behind it, so the vessel has a "where it has been" track
        # on the FIRST pass rather than a bare marker; then the one covering the
        # most ground. Windows that clear nothing are still scored so the vessel
        # gets a sensible track before being filtered out.
        lead_in = min((start - first).total_seconds() / 3600, LEAD_IN_HOURS)
        score = (passes, lead_in, quality["min_leg_km"])
        if best is None or score > best[0]:
            best = (score, start, end, quality)

    if best is None:
        return last - window, last, None
    return best[1], best[2], best[3]


def vessel_profile(corpus):
    """
    One row per vessel describing the state the demo will actually plot: the
    last fix of the window _best_window() picks, not the mean of the vessel's
    whole multi-month history. Selecting on the mean was wrong — a vessel whose
    average position is 18 km out can finish right next to the cluster centre,
    which is how "far" vessels ended up inside the spill zone on the map.

    The chosen window bounds travel with the row so build_ship_track() displays
    exactly the stretch that was selected on. Deriving them twice is what let
    selection and display disagree before.
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
        if span_hours < MIN_SESSION_SPAN_HOURS:
            continue

        win_start, win_end, quality = _best_window(segment)
        if quality is None:
            continue
        window = segment[(segment["BaseDateTime"] >= win_start)
                         & (segment["BaseDateTime"] <= win_end)]
        final = window.iloc[-1]
        first = vessel.iloc[0]
        rows.append({
            "MMSI": mmsi,
            "n": len(segment),
            "span_hours": span_hours,
            "win_start": win_start, "win_end": win_end,
            "wander": quality["wander"],
            "min_leg_km": quality["min_leg_km"],
            "balance": quality["balance"],
            "lat": float(final["LAT"]), "lon": float(final["LON"]),
            "course": float(final["COG"]), "speed_kt": float(final["SOG"]),
            "range_km": haversine_km(window["LAT"].min(), window["LON"].min(),
                                      window["LAT"].max(), window["LON"].max()),
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


def _pick_sources(eligible):
    """
    Choose which vessels leak.

    NOT simply the ones nearest the cluster centre. Where the sources sit
    decides how much of the rest of the fleet starts in clear water: putting
    them in the middle of the anchorage left every other vessel inside the
    impact envelope, so the map could only ever show exit routes and never a
    vessel approaching and turning away.

    So score every admissible pair by how much CROSSING traffic it leaves —
    vessels that begin outside the zone and whose own recorded course runs them
    into it — and take the best. Sources must still be identified (named, typed
    and dimensioned) and far enough apart that their envelopes do not touch.
    """
    identified = eligible[eligible["identified"]]
    separation = min_source_separation_km()
    envelope_km = impact_envelope(PASS_INTERVAL_HOURS)["radius_km"]

    best = None
    for pair in itertools.combinations(identified.itertuples(index=False), NEAR_COUNT):
        if any(haversine_km(a.lat, a.lon, b.lat, b.lon) < separation
               for a, b in itertools.combinations(pair, 2)):
            continue
        targets = [{"lat": p.lat, "lon": p.lon} for p in pair]
        others = eligible[~eligible["MMSI"].isin([p.MMSI for p in pair])]
        clear = others.apply(
            lambda r: min(haversine_km(r["lat"], r["lon"], t["lat"], t["lon"])
                          for t in targets), axis=1)
        approach = others.apply(lambda r: _approach_km(r, targets), axis=1)
        far = clear >= far_min_km()
        score = (int((far & (approach <= envelope_km * 2)).sum()), int(far.sum()))
        if best is None or score > best[0]:
            best = (score, pair)

    if best is None:      # no admissible pair — fall back to the most central
        return identified.sort_values("dist_km").head(NEAR_COUNT)
    return pd.DataFrame(list(best[1]))


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
                       # Reads as one coherent voyage rather than a scribble,
                       # and covers comparable ground between each pass.
                       & (profile["wander"] <= TRACK_MAX_WANDER)
                       & (profile["min_leg_km"] >= TRACK_MIN_LEG_KM)
                       & (profile["balance"] >= TRACK_MIN_BALANCE)
                       & (~profile["MMSI"].isin(EXCLUDE_MMSI))]

    near_rows = _pick_sources(eligible)
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

    # Carry each vessel's chosen window along with it, so the track built later
    # is the same stretch that was selected on.
    windows = profile.set_index("MMSI")[["win_start", "win_end"]]
    return {m: (windows.loc[m, "win_start"], windows.loc[m, "win_end"])
            for m in selected[:FLEET_SIZE]}


def build_ship_track(vessel_rows, track_end, win_start, win_end):
    """
    The window _best_window() chose for this vessel, plus up to LEAD_IN_HOURS of
    real fixes before it as trailing history, downsampled and re-indexed so the
    window's end lands on `track_end` (the latest pass).

    lat/lon/speed/course are the corpus's own recorded values, verbatim.
    """
    vessel_rows = vessel_rows.sort_values("BaseDateTime").reset_index(drop=True)
    times = vessel_rows["BaseDateTime"]
    shown = vessel_rows[(times >= win_start - timedelta(hours=LEAD_IN_HOURS))
                        & (times <= win_end)]

    rows = _downsample(shown.to_dict("records"), MAX_TRACK_POINTS)

    # Anchor the WINDOW end to the pass, not the lead-in, so t1..t3 lands on the
    # stretch that was selected for its movement.
    shift = track_end - win_end
    track = [{
        "time": (r["BaseDateTime"] + shift).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lat": round(float(r["LAT"]), 5), "lon": round(float(r["LON"]), 5),
        "speed_kt": round(float(r["SOG"]), 1), "course_deg": round(float(r["COG"]), 1),
    } for r in rows]
    return track


def build_fleet():
    corpus = pd.read_csv(AIS_REFERENCE_FILE, parse_dates=["BaseDateTime"])
    windows = select_cluster(corpus)
    mmsis = list(windows)
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
        win_start, win_end = windows[mmsi]
        track = build_ship_track(rows, last_pass, win_start, win_end)
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
