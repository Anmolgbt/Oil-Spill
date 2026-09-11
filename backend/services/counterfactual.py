"""
COUNTERFACTUAL — "what if this vessel caused the spill?"

The hindcast asks: given oil observed here, where did it come from? This asks
the inverse: given that THIS vessel was where it actually was at the estimated
release time, and given the same drift, where would its oil be now — and does
that match where oil was actually seen?

The two must use the SAME drift vector, in opposite directions, or the question
is unanswerable. If the forward run used a different vector from the hindcast
that produced the source estimate, a vessel sitting exactly on that estimated
source would fail to reproduce the observation, and every result would be noise.
So this deliberately uses HINDCAST_DRIFT_* forward, not the envelope's
current+windage vector (damage.drift_vector) and not FORECAST_DRIFT_*. The repo
carries three different drift assumptions; only one of them is the inverse of
the hindcast, and that is the one this test needs.

What comes back is a distance, not a verdict. A small miss means the vessel's
real position is consistent with having been the source; a large one means it is
not. Both are results. The interface is expected to state the second as plainly
as the first — an exculpatory outcome is as much a finding as an incriminating
one, and this module never labels either as proof.

Nothing here runs a model. It is geometry over AIS fixes the fleet already
holds, using assumptions that are stated in the response.
"""
import math
from datetime import timedelta

from .geo import haversine_km, parse_time
from .investigation import HINDCAST_DRIFT_DIRECTION_DEG, HINDCAST_DRIFT_SPEED_KMH


def _drift_forward(lat, lon, hours,
                   speed_kmh=HINDCAST_DRIFT_SPEED_KMH,
                   bearing_deg=HINDCAST_DRIFT_DIRECTION_DEG):
    """
    Carry a release point forward along a drift vector.

    Deliberately the same flat-earth arithmetic hindcast_over() uses, sign
    reversed. Mirroring it exactly is what makes the counterfactual a true
    inverse: a vessel sitting on the estimated source must come back with a
    miss of ~0 km, and it does. Substituting the spherical destination() here
    would leave a small residual that is pure method mismatch, not evidence.

    `speed_kmh` and `bearing_deg` default to the hindcast's own vector, which is
    the only pairing that closes. They are parameters solely so the sensitivity
    sweep can perturb them through this one implementation rather than a second
    copy of it — a copy would eventually drift from this one and the closure
    property would be lost without any test noticing.
    """
    theta = math.radians(bearing_deg)
    distance_km = speed_kmh * hours
    dx_km = distance_km * math.sin(theta)
    dy_km = distance_km * math.cos(theta)
    return (lat + dy_km * (1 / 111),
            lon + dx_km * (1 / (111 * math.cos(math.radians(lat)))))


def _fix_at(track, when):
    """The vessel's AIS fix at or before `when`, else its earliest fix."""
    if not track:
        return None
    target = parse_time(when)
    prior = [p for p in track if parse_time(p["time"]) <= target]
    fix = prior[-1] if prior else track[0]
    gap_h = (target - parse_time(fix["time"])).total_seconds() / 3600
    return fix, round(gap_h, 2)


def consistency_radius_km(age_hours, speed_kmh=HINDCAST_DRIFT_SPEED_KMH):
    """
    How far the oil could have travelled in `age_hours` UNDER THE ASSUMPTION
    THIS TEST IS USING.

    This used to come from the caller, which passed the map's affected-area
    circle — and that circle is sized by damage.drift_vector(), a DIFFERENT
    vector (1.394 km/h toward 181.2 deg) from the 1.5 km/h toward 135 deg the
    legacy counterfactual drifts with. So the shipped test moved a parcel of oil
    one way and judged it against how far it could have gone another way. That
    was not defensible once it was noticed.

    Each mode now uses the envelope its own drift implies: 6.00 km for the
    legacy vector at 4 h, 5.58 km for the environment-derived one. Measured on
    t3 the correction changes no verdict (6.26 and 6.23 km sit outside both
    thresholds) and no miss distance, which are threshold-independent; it moves
    two robustness classifications, because those are margin questions.

    The map's affected-area circle stays at 5.58 km. It answers a different
    question — how far could the oil have reached — and is sized by the best
    available drift estimate rather than by whichever assumption a particular
    test happens to be probing.
    """
    return round(speed_kmh * age_hours, 2)


def environmental_counterfactual(fix, release_at, spill_lat, spill_lon, age_hours,
                                 legacy_within=None):
    """
    The same question, run through the environment field.

    Integrates the vessel's real AIS position forward with drift.integrate() —
    the same integrator the environment-aware hindcast uses, so this is that
    hindcast's exact inverse in the way the legacy pair are each other's.
    Measured: a probe at the environment-aware source reproduces the observation
    to 6e-05 km.

    Judged against the envelope THIS drift implies, not the legacy one. With no
    dataset loaded that is the environment-derived 1.394 km/h over the spill's
    age; the legacy path uses 1.5 km/h toward 135 deg and its own 6.00 km. Two
    assumptions, each tested against itself.

    NOT more accurate. With no dataset committed this is still an assumed
    vector, merely a different one — and even with a reanalysis loaded, a
    reanalysis is a model output. Nothing here is validated.
    """
    from .drift import integrate

    run = integrate(fix["lat"], fix["lon"], release_at, age_hours)
    miss_km = haversine_km(run["latitude"], run["longitude"], spill_lat, spill_lon)
    radius_km = round(run["displacement_km"], 2)
    within = bool(miss_km <= radius_km)

    return {
        "available": True,
        "miss_distance_km": round(miss_km, 2),
        "consistency_radius_km": radius_km,
        "within_envelope": within,
        "margin_km": round(radius_km - miss_km, 2),
        "simulated_now": {"latitude": round(run["latitude"], 5),
                          "longitude": round(run["longitude"], 5)},
        "environment_mode": run["environment_mode"],
        "environment_reason": run["environment_reason"],
        "steps": run["steps"],
        "step_minutes": run["step_minutes"],
        "agrees_with_legacy": None if legacy_within is None else (within == legacy_within),
        "method": (f"Forward integration in {run['step_minutes']:.0f}-minute steps, "
                   "resampling the environment at each step, judged against the "
                   "envelope that same drift implies"),
        "radius_basis": ("The distance this drift carries oil over the spill's "
                         "estimated age — the envelope this assumption implies, "
                         "not the legacy one."),
        "note": ("Physically informed, not validated" if run["environment_mode"] == "historical"
                 else "No environmental dataset is loaded, so this is still an assumed "
                      "vector — a different one from the legacy test's, not a measured field."),
    }


def test_candidate(ship, release_at, spill_lat, spill_lon, age_hours,
                   envelope_radius_km=None, source=None,
                   affected_area_radius_km=None):
    """
    Run the counterfactual for one candidate vessel, both ways.

    `ship` is a fleet entry carrying its AIS `track`. `release_at`, the spill
    position and `age_hours` all come from the scan that raised the detection.

    `envelope_radius_km` overrides the derived threshold; it exists so tests can
    pin a specific radius. Callers should leave it alone and let
    consistency_radius_km() decide.
    """
    found = _fix_at(ship.get("track") or [], release_at)
    if not found:
        return {
            "available": False,
            "reason": ("No AIS fix for this vessel at or before the estimated "
                       "release time, so its position then is unknown."),
        }
    fix, gap_hours = found

    if envelope_radius_km is None:
        envelope_radius_km = consistency_radius_km(age_hours)

    sim_lat, sim_lon = _drift_forward(fix["lat"], fix["lon"], age_hours)
    miss_km = haversine_km(sim_lat, sim_lon, spill_lat, spill_lon)

    # The only honest yardstick already on screen: the drift envelope is the sea
    # area the oil could have reached, so a miss inside it is not separable from
    # the observation given these assumptions.
    within = None if envelope_radius_km is None else bool(miss_km <= envelope_radius_km)

    _env_block = environmental_counterfactual(fix, release_at, spill_lat, spill_lon,
                                              age_hours, legacy_within=within)

    return {
        "available": True,
        "ship_id": ship["id"],
        "mmsi": ship.get("mmsi"),
        "name": ship.get("name"),
        "assumed_release": {
            "latitude": fix["lat"],
            "longitude": fix["lon"],
            "ais_fix_time": fix["time"],
            "fix_age_hours": gap_hours,
            "note": ("The vessel's own AIS position at the estimated release "
                     "time — an observation, not a hypothesis."),
        },
        "simulated_now": {
            "latitude": round(sim_lat, 5),
            "longitude": round(sim_lon, 5),
            "note": "Where oil released at that position would now be, under the stated drift.",
        },
        "observed_now": {
            "latitude": spill_lat,
            "longitude": spill_lon,
            "note": "Where the CNN actually found an oil signature.",
        },
        "miss_distance_km": round(miss_km, 2),
        "envelope_radius_km": envelope_radius_km,
        "within_envelope": within,
        "distance_from_estimated_source_km": (
            None if not source else
            round(haversine_km(fix["lat"], fix["lon"],
                               source["latitude"], source["longitude"]), 2)
        ),
        "drift": {
            "speed_kmh": HINDCAST_DRIFT_SPEED_KMH,
            "direction_deg": HINDCAST_DRIFT_DIRECTION_DEG,
            "hours_forward": age_hours,
            "environmental_data_used": False,
        },
        "method": ("The hindcast's drift vector, run forward from this vessel's "
                   "real AIS position over the spill's estimated age."),
        "interpretation": {
            "is_proof": False,
            "meaning": ("A small miss means this vessel's actual position is "
                        "consistent with having been the source. A large one "
                        "means it is not. Neither establishes causation, and "
                        "both inherit every assumption in the drift model."),
        },
        # The threshold, and why it is not the circle on the map.
        "consistency_radius_km": envelope_radius_km,
        "affected_area_radius_km": affected_area_radius_km,
        "radius_basis": ("The distance the hindcast's own drift carries oil over the "
                         "spill's estimated age. The map's affected-area circle is "
                         "sized by a different vector and answers a different "
                         "question — how far the oil could have reached at all."),
        "margin_km": round(envelope_radius_km - miss_km, 2),
        # Same question, same round trip: a verdict and how far the assumption
        # behind it can move before it changes belong together.
        "robustness": robustness(ship, release_at, spill_lat, spill_lon,
                                 age_hours, envelope_radius_km),
        # And the same question again, through the environment field.
        "environmental": _env_block,
        "mode_comparison": _mode_comparison(miss_km, envelope_radius_km, _env_block),
        "limits": ("Kinematic, with no wind, current, wave or oil-property data. "
                   "The release time is itself an estimate bounded by the "
                   "satellite revisit interval, so the forward run starts from "
                   "an uncertain moment."),
    }


# --- sensitivity sweep -------------------------------------------------------
#
# The counterfactual above answers one question under ONE set of assumptions.
# Those assumptions are not measured — no wind or current data is wired up
# anywhere in this system — so the honest follow-up is not "is the answer
# right?" but "how far can the assumption move before the answer changes?"
#
# Three things vary. Nothing else does, and the omissions are deliberate:
#
#   drift speed and bearing   The hindcast's vector. Nothing measured
#                             constrains it, so these two are the sweep proper
#                             and the classification is computed over them.
#   assumed age               Also assumed, but constrained by an OBSERVATION:
#                             the previous pass was clear and this one is not,
#                             so the release sits inside one revisit interval
#                             and the true age can only be YOUNGER, never
#                             older. Reported as its own margin rather than
#                             mixed into the grid — see the note below.
#   the observed spill        NOT swept. It is where the CNN found oil — an
#                             observation, not an assumption.
#   the vessel's AIS position NOT swept, for the same reason. It moves across
#                             the age axis only because a different assumed
#                             release time selects a different real fix.
#   the estimated source      NOT swept. It is not an input to the miss
#                             distance at all; it enters the response only as a
#                             reported distance. Perturbing it would manufacture
#                             variation the calculation does not actually have.
#
# Why age is not a third grid axis. A younger assumed age shrinks the drift and
# the envelope together, and as it approaches zero the only vessel that can be
# consistent is one sitting on the slick — correct physics (an hour-old spill
# must be where the ship is), but it drives EVERY candidate to "not consistent"
# at the young end. Averaged into a joint grid it dominates the other two axes
# and the fraction ends up reporting which verdict you started from rather than
# anything about the vessel: measured on the t3 case it labelled a candidate at
# half the envelope radius "highly sensitive" and one at nearly twice it
# "robust". So the age result is kept — as the youngest age the verdict
# survives, which is the more useful form of it anyway — but out of the grid.

# Half-widths. These are NOT error bars — no error distribution for the drift is
# known, and inventing one would be worse than having none. They are a
# deliberately wide band chosen to contain every drift assumption this system
# itself carries: the hindcast's 1.5 km/h at 135 deg, the forecast's 1.0 km/h at
# 180 deg, and the envelope's ~1.39 km/h at ~181 deg. The speed band spans
# 0.75-2.25 km/h and the bearing band 90-180 deg, which reaches the forecast
# bearing at its outer edge.
SWEEP_SPEED_FRACTION = 0.5
SWEEP_BEARING_DEG = 45.0

# Points per axis: 7 x 7 = 49 evaluations, each arithmetic over a track lookup,
# so a candidate's whole sweep costs a couple of milliseconds.
SWEEP_STEPS = 7

# Resolution of the single-axis flip search. Finer than the grid because the
# margin is the interpretable number and the fraction is not.
MARGIN_STEPS = 60

# Agreement thresholds. Rule-based and reported with the result, so the label
# can be argued with rather than taken on faith.
ROBUST_AGREEMENT = 0.90
MODERATE_AGREEMENT = 0.60


def _spread(half_width, steps=SWEEP_STEPS):
    """`steps` values from -half_width to +half_width, inclusive, centred on 0."""
    return [half_width * (-1 + 2 * i / (steps - 1)) for i in range(steps)]


def robustness(ship, release_at, spill_lat, spill_lon, age_hours,
               envelope_radius_km):
    """
    How far the drift assumption can move before this candidate's
    consistent / not-consistent verdict flips.

    This measures SENSITIVITY TO AN ASSUMPTION. It is not an accuracy, a
    confidence or a probability, and the sweep is a deterministic grid over a
    chosen band rather than a distribution over anything.
    """
    track = ship.get("track") or []
    if not track or not envelope_radius_km or not age_hours:
        return {
            "available": False,
            "reason": ("Robustness needs a track, an estimated age and a drift "
                       "envelope to test the verdict against; at least one is "
                       "absent, so there is no verdict to perturb."),
        }

    observed_at = parse_time(release_at) + timedelta(hours=age_hours)

    def verdict(age, speed_kmh, bearing_deg):
        """Would the vessel be called consistent under these assumptions?"""
        fix, _ = _fix_at(track, (observed_at - timedelta(hours=age)).isoformat())
        lat, lon = _drift_forward(fix["lat"], fix["lon"], age, speed_kmh, bearing_deg)
        miss_km = haversine_km(lat, lon, spill_lat, spill_lon)
        # The envelope is drift speed x age, so it is linear in age and scales
        # with it. Moving the assumed age without moving the envelope would
        # compare a shorter drift against an unchanged threshold and call the
        # result sensitivity, when it would only be an inconsistency in the
        # sweep. At age_hours this returns the caller's own radius exactly, so
        # the baseline below reproduces the verdict already reported.
        return miss_km <= envelope_radius_km * (age / age_hours)

    speed0, bearing0 = HINDCAST_DRIFT_SPEED_KMH, HINDCAST_DRIFT_DIRECTION_DEG
    baseline = verdict(age_hours, speed0, bearing0)

    speed_half = speed0 * SWEEP_SPEED_FRACTION
    speeds = [speed0 + d for d in _spread(speed_half)]
    bearings = [bearing0 + d for d in _spread(SWEEP_BEARING_DEG)]

    agree = sum(1 for s in speeds for b in bearings
                if verdict(age_hours, s, b) == baseline)
    total = len(speeds) * len(bearings)
    agreement = agree / total

    def flip(axis_bound, apply, directions):
        """
        Smallest single-axis perturbation that flips the verdict, with the other
        two axes held at their baseline. None means the verdict survives the
        whole band on this axis.
        """
        for i in range(1, MARGIN_STEPS + 1):
            delta = axis_bound * i / MARGIN_STEPS
            for sign, word in directions:
                if apply(sign * delta) != baseline:
                    return {"delta": round(delta, 2), "direction": word,
                            "bound": round(axis_bound, 2)}
        return None

    flips = {
        "drift_speed_kmh": flip(
            speed_half, lambda d: verdict(age_hours, speed0 + d, bearing0),
            [(1, "faster"), (-1, "slower")]),
        "drift_bearing_deg": flip(
            SWEEP_BEARING_DEG, lambda d: verdict(age_hours, speed0, bearing0 + d),
            [(1, "clockwise"), (-1, "anticlockwise")]),
        # One-sided: a clear previous pass bounds the age from above, not below.
        "assumed_age_hours": flip(
            age_hours, lambda d: verdict(max(age_hours + d, 1e-6), speed0, bearing0),
            [(-1, "younger")]),
    }

    if agreement >= ROBUST_AGREEMENT:
        label = "robust"
    elif agreement >= MODERATE_AGREEMENT:
        label = "moderately sensitive"
    else:
        label = "highly sensitive"

    scored = [(k, v) for k, v in flips.items() if v]
    smallest = min(scored, key=lambda kv: kv[1]["delta"] / kv[1]["bound"]) if scored else None

    return {
        "available": True,
        "baseline_verdict": "consistent" if baseline else "not consistent",
        "agreement_fraction": round(agreement, 3),
        "classification": label,
        "flips_at": flips,
        "smallest_flip": (None if not smallest else
                          {"axis": smallest[0], **smallest[1]}),
        "sweep": {
            "combinations": total,
            "over": "drift speed and bearing, at the stated age",
            "drift_speed_kmh": [round(min(speeds), 2), round(max(speeds), 2)],
            "drift_bearing_deg": [round(min(bearings), 1), round(max(bearings), 1)],
            "basis": ("The band contains every drift assumption this system "
                      "carries (1.0-1.5 km/h, 135-181 deg). The assumed age is "
                      "reported as its own margin instead of a grid axis: it is "
                      "bounded from above by an observation (the previous pass "
                      "was clear) and shrinking it collapses the envelope, which "
                      "would swamp the two axes nothing constrains."),
            "not_swept": ("The observed slick position and the vessel's own AIS "
                          "fixes are observations, not assumptions. The estimated "
                          "source is not an input to the miss distance."),
        },
        "rule": (f"agreement >= {ROBUST_AGREEMENT:.0%} is robust; "
                 f">= {MODERATE_AGREEMENT:.0%} is moderately sensitive; "
                 f"below that is highly sensitive."),
        "interpretation": {
            "is_accuracy": False,
            "is_probability": False,
            "meaning": ("How much of the swept assumption space returns the same "
                        "verdict as the stated assumptions do. The sweep is a "
                        "uniform grid over a band chosen by hand, not a "
                        "probability distribution, so this fraction is a property "
                        "of that grid and says nothing about how likely any drift "
                        "value is. A robust result is a verdict that does not "
                        "depend on getting the drift exactly right; a sensitive "
                        "one is a verdict that does."),
        },
    }


def _mode_comparison(legacy_miss_km, legacy_radius_km, env):
    """
    What changes between the two counterfactual modes, said plainly.

    Measured on t3: the VERDICTS agree for every candidate on both detections,
    and the MARGINS invert. The shipped top candidate goes from 2.70 km inside
    its threshold to 0.05 km inside — consistent either way, but by fifty metres
    rather than by nearly three kilometres. And the vessel that best reproduces
    the observation changes (MR CANOPUS legacy, ACHILLEAS environment-aware).

    Reporting only "both say consistent" would hide all of that, which is why
    the margin travels with the verdict.
    """
    if not env or not env.get("available"):
        return {"available": False,
                "reason": "The environment-aware run was unavailable, so there is "
                          "nothing to compare the legacy result against."}

    legacy_margin = round(legacy_radius_km - legacy_miss_km, 2)
    return {
        "available": True,
        "verdicts_agree": env["agrees_with_legacy"],
        "legacy": {"miss_km": round(legacy_miss_km, 2),
                   "radius_km": legacy_radius_km,
                   "margin_km": legacy_margin},
        "environmental": {"miss_km": env["miss_distance_km"],
                          "radius_km": env["consistency_radius_km"],
                          "margin_km": env["margin_km"]},
        "margin_shift_km": round(env["margin_km"] - legacy_margin, 2),
        "environment_mode": env["environment_mode"],
        "self_consistency": ("The environment-aware run uses one vector for both the "
                             "drift and the threshold. The legacy run now does too — "
                             "it used to be judged against the map's circle, which is "
                             "sized by a different vector."),
        "meaning": ("Two assumptions, each tested against itself. Agreement is not "
                    "corroboration — both are unmeasured, and with no dataset loaded "
                    "the environment-aware run is a different assumption rather than "
                    "an observation. A margin that moves while the verdict holds "
                    "means the verdict is resting on the assumption more than it "
                    "looks like it is."),
    }
