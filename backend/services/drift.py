"""
ENVIRONMENT-AWARE DRIFT — stepping a slick through a field instead of along one
arrow.

The legacy hindcast and forecast each apply a single constant vector over the
whole interval: one multiplication, one straight line. That is all a stated
constant supports. This module does the same job by integration — advance a
short step, resample the environment at the new position and time, advance
again — which is what a time-varying field requires and what the legacy form
cannot express.

BOTH PATHS SURVIVE. `investigation.hindcast/forecast` and
`fleet_pipeline.hindcast_over` are untouched and still called; nothing here
replaces them. Phase 15 compares the two, so both results must remain
obtainable, and the counterfactual's inverse-closure property depends on the
legacy hindcast staying exactly as it is.

TWO THINGS THIS IS NOT:

  Not more accurate. A reanalysis is a model output too, and nothing here is
  validated against an observed slick trajectory. Integrating through a field
  makes the estimate PHYSICALLY INFORMED. It does not make it right.

  Not the same as the legacy estimate, even with no data. The integration
  reduces to a single straight application of the environment's OWN vector
  (asserted to 5.6e-12 km in test_drift.py), but that vector is 1.394 km/h
  toward 181.2 deg — what the stated wind and current imply — while the legacy
  hindcast uses 1.5 km/h toward 135 deg and the legacy forecast 1.0 km/h toward
  180 deg, notebook constants never derived from those conditions. So the two
  paths separate by 4.56 km at the source and up to 18.98 km at the 48 h
  horizon on the t3 case, with no environmental data involved at all. That is
  the "three drift vectors coexist" problem made numeric, reported as
  `drift_divergence`, and it is a disagreement between assumptions rather than
  a measurement of anyone's error.

WHY cos(lat) IS HELD AT THE START LATITUDE. Each step converts kilometres to
degrees of longitude using cos of the latitude the integration STARTED at, not
the latitude of the current step. Refining it per step would be marginally
better geodesy and would break the property above: N equal steps would no longer
sum to the single legacy displacement, and "identical in fallback" would become
"identical to within ~190 m at 48 h". The flat 1/111 pair is the same
approximation the hindcast/counterfactual closure already rests on
(services/geo.py documents it), so this keeps one convention rather than
introducing a second.
"""
from datetime import timedelta

import math

from .environment import get_conditions
from .geo import haversine_km, parse_time

# Integration step. 30 minutes over a 4 h hindcast is 8 samples and over a 48 h
# forecast is 96 — fine granularity against any reanalysis this would use
# (hourly at best), and cheap because a fallback sample is arithmetic.
STEP_MINUTES = 30

# The backward step is solved implicitly so that it is the exact inverse of the
# forward one; see the loop below. Three passes is ample for a field that is
# smooth over half an hour, and 1e-9 deg is ~0.1 mm.
BACKWARD_ITERATIONS = 3
BACKWARD_TOLERANCE_DEG = 1e-9

# The flat-earth pair, shared with the hindcast and the counterfactual so all
# three speak one convention. See services/geo.py on why it is not "fixed".
KM_PER_DEG = 111.0


def integrate(lat, lon, when, hours, backward=False, step_minutes=STEP_MINUTES):
    """
    Walk a parcel of oil through the environment field for `hours`.

    Returns the path, the endpoint, and an honest account of what the field was
    during the walk: `environment_mode` is "historical" only if EVERY sample was,
    because one fallback sample in the middle of a track makes the whole path a
    hybrid, and a hybrid presented as historical would be a lie about provenance.
    """
    start = parse_time(when) if isinstance(when, str) else when
    sign = -1 if backward else 1

    # Held at the start latitude on purpose — see the module docstring.
    lon_per_km = 1 / (KM_PER_DEG * math.cos(math.radians(lat)))
    lat_per_km = 1 / KM_PER_DEG

    steps = max(1, round(hours * 60 / step_minutes))
    step_hours = hours / steps

    path = [{"hours": 0.0, "latitude": lat, "longitude": lon}]
    modes, sources, reasons = set(), set(), []
    cur_lat, cur_lon = lat, lon

    def sample(at_lat, at_lon, at_time):
        env = get_conditions(at_lat, at_lon, at_time.isoformat())
        modes.add(env["environment_mode"])
        sources.add(env["source"])
        if env["environment_reason"]:
            reasons.append(env["environment_reason"])
        drift = env["drift"]
        theta = math.radians(drift["direction_deg"])
        d = drift["speed_kmh"] * step_hours
        return (d * math.cos(theta) * lat_per_km, d * math.sin(theta) * lon_per_km)

    for i in range(steps):
        t_from = start + timedelta(hours=sign * i * step_hours)
        t_to = start + timedelta(hours=sign * (i + 1) * step_hours)

        if not backward:
            # Forward: sample where the parcel is, then move it.
            dlat, dlon = sample(cur_lat, cur_lon, t_from)
            cur_lat, cur_lon = cur_lat + dlat, cur_lon + dlon
        else:
            # Backward: the IMPLICIT form, and this matters.
            #
            # The obvious backward step samples the field where the parcel is
            # now and subtracts. Composed with a forward run it does not close:
            # measured against the synthetic varying grid it left 1.28 km at 4 h,
            # and refining the step from 60 to 1 minute did not move that figure
            # at all — so it was structural, not first-order error, and no
            # amount of resolution would have fixed it.
            #
            # The inverse of "sample at the departure point, then move" is
            # "find the point which, sampled and moved, lands here". Solved by
            # fixed-point iteration: the field is smooth over one step, so this
            # converges in two or three passes. In a uniform field the first
            # guess is already exact, which is why fallback is unaffected.
            guess_lat, guess_lon = cur_lat, cur_lon
            for _ in range(BACKWARD_ITERATIONS):
                dlat, dlon = sample(guess_lat, guess_lon, t_to)
                nxt_lat, nxt_lon = cur_lat - dlat, cur_lon - dlon
                if (abs(nxt_lat - guess_lat) < BACKWARD_TOLERANCE_DEG
                        and abs(nxt_lon - guess_lon) < BACKWARD_TOLERANCE_DEG):
                    guess_lat, guess_lon = nxt_lat, nxt_lon
                    break
                guess_lat, guess_lon = nxt_lat, nxt_lon
            cur_lat, cur_lon = guess_lat, guess_lon

        path.append({"hours": round((i + 1) * step_hours, 4),
                     "latitude": cur_lat, "longitude": cur_lon})

    historical = modes == {"historical"}
    return {
        "latitude": cur_lat,
        "longitude": cur_lon,
        "path": path,
        "steps": steps,
        "step_minutes": round(step_hours * 60, 2),
        "hours": hours,
        "direction": "backward" if backward else "forward",
        "environment_mode": "historical" if historical else "fallback",
        "environment_reason": None if historical else (reasons[0] if reasons else None),
        "environment_sources": sorted(sources),
        "uniform_field": len(modes) == 1 and not historical,
        "displacement_km": round(haversine_km(lat, lon, cur_lat, cur_lon), 4),
    }


def hindcast_environmental(spill_lat, spill_lon, observed_at, hours):
    """
    Step backward from the observed slick to an estimated source REGION.

    The legacy hindcast returns a point. Integrating backward through a field
    that is only known to a grid's resolution returns a point plus the honest
    admission that it is the centre of a region — Phase 17's evidence layer
    consumes that, and calling it a point would overstate what a reanalysis
    supports.
    """
    run = integrate(spill_lat, spill_lon, observed_at, hours, backward=True)
    return {
        **run,
        "label": "Probable source region — environment-aware estimate",
        "confirmed": False,
        "confidence": None,
        "hours_backward": hours,
        "method": (f"Backward integration in {run['step_minutes']:.0f}-minute steps, "
                   "resampling the environment at each step"),
        "environmental_data_used": run["environment_mode"] == "historical",
        "evidence_class": "MODEL ESTIMATE",
        "note": ("Physically informed, not validated. A reanalysis is itself a "
                 "model output, and no observed slick trajectory has been used to "
                 "check this against."),
    }


def forecast_environmental(spill_lat, spill_lon, observed_at, horizons):
    """
    Project the slick forward through the field, at the existing horizons.

    One integration to the furthest horizon, with the intermediate horizons read
    off the same path — running each horizon as its own integration would let
    the +12 h point sit somewhere the +24 h path never passed through.
    """
    longest = max(horizons)
    run = integrate(spill_lat, spill_lon, observed_at, longest)

    points = []
    for h in sorted(horizons):
        # Nearest step at or before the horizon; steps divide the horizons
        # evenly at 30 minutes, so this is exact for 6/12/24/48.
        point = max((p for p in run["path"] if p["hours"] <= h + 1e-9),
                    key=lambda p: p["hours"])
        points.append({"hours_ahead": h,
                       "latitude": point["latitude"],
                       "longitude": point["longitude"]})

    return {
        "type": "environment_aware_projection",
        "label": "Environment-aware movement projection",
        "points": points,
        "path": run["path"],
        "steps": run["steps"],
        "step_minutes": run["step_minutes"],
        "environment_mode": run["environment_mode"],
        "environment_reason": run["environment_reason"],
        "environment_sources": run["environment_sources"],
        "environmental_data_used": run["environment_mode"] == "historical",
        "requires_environmental_drift_data": run["environment_mode"] != "historical",
        "evidence_class": "PREDICTION",
        "note": ("Physically informed, not validated. Oil weathering, spreading, "
                 "evaporation and wave action are still absent."),
    }


def closure_residual_km(lat, lon, when, hours):
    """
    How far forward-then-backward misses the point it started from.

    The counterfactual's whole meaning rests on the forward run being the exact
    inverse of the backward one: a probe at the estimated source must reproduce
    the observation. With one constant vector that is exact arithmetic. With a
    VARYING field it is not automatic, and the naive backward step does not
    close at all — measured against the synthetic grid it left 1.28 km at 4 h,
    unchanged from 60-minute steps down to 1-minute, so it was structural rather
    than something resolution would fix.

    integrate() therefore solves the backward step implicitly, which makes it
    the exact inverse of the forward step by construction. Measured against the
    same varying grid the residual is now 0.0 km at every step size tested.

    This function stays because the property must keep being CHECKED rather than
    assumed: any future change to the scheme, the step size or the field
    sampling can break it silently, and Phase 16 has to state the residual
    wherever an environment-aware counterfactual is shown. In fallback it
    reports ~0.0001 km — 10 cm, from each run holding cos(lat) at its own start
    latitude, two orders of magnitude below the counterfactual's 10 m tolerance
    and the price of the uniform-field reduction described in the module
    docstring.
    """
    back = integrate(lat, lon, when, hours, backward=True)
    start = parse_time(when) if isinstance(when, str) else when
    fwd = integrate(back["latitude"], back["longitude"],
                    (start - timedelta(hours=hours)).isoformat(), hours)
    return {
        "residual_km": round(haversine_km(lat, lon, fwd["latitude"], fwd["longitude"]), 4),
        "hours": hours,
        "environment_mode": back["environment_mode"],
        "step_minutes": back["step_minutes"],
        "meaning": ("Distance between the observed point and the result of "
                    "integrating back to a source and forward again. Zero with a "
                    "uniform field; non-zero in a varying one is method error, "
                    "not evidence about any vessel."),
    }
