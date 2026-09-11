"""
EVIDENCE QUALITY — how much each stream can actually tell us, and whether any
candidate is supported at all.

The dashboard's answer to "who did it" was one percentage. A percentage cannot
say whether the AIS behind it had a 72-minute gap, whether the behaviour model
declined to answer, or whether the vessel's own counterfactual says it could not
have been the source. This grades each stream separately so the total can be
argued with rather than believed.

THE GRADE AXIS, DECIDED ONCE AND HELD.

    A grade says HOW MUCH THIS STREAM CAN TELL US.
    It does NOT say how guilty the vessel is.

That is the only reading under which "UNAVAILABLE is not LOW" makes sense, and
it is what keeps evidence quality from quietly becoming a second suspicion
score. A behaviour model that ran and found nothing unusual is HIGH-quality
evidence of normality. One that could not run is UNAVAILABLE, and Phase 9
already established that a model which could not answer is not evidence a vessel
behaved normally.

Every threshold below is stated in the payload alongside the grade it produced,
so a reader can disagree with the rule rather than only with the verdict.
Nothing here is learned, fitted or validated.
"""
from datetime import timedelta

from . import narrative
from .geo import parse_time

HIGH, MEDIUM, LOW, UNAVAILABLE = "HIGH", "MEDIUM", "LOW", "UNAVAILABLE"

# --- AIS coverage ------------------------------------------------------------
# Thresholds sized against the measured spread rather than picked: across the t3
# candidates the release window holds 19-38 fixes with largest gaps from 7.2 to
# 72 minutes, so these separate the well-tracked vessels from the patchy one
# instead of grading everybody alike.
COVERAGE_HIGH_FIXES, COVERAGE_HIGH_GAP_MIN = 25, 15
COVERAGE_MEDIUM_FIXES, COVERAGE_MEDIUM_GAP_MIN = 10, 30

# --- trajectory --------------------------------------------------------------
TRAJECTORY_STRONG, TRAJECTORY_WEAK = 60.0, 20.0

# --- counterfactual ----------------------------------------------------------
# A margin thinner than this fraction of the threshold means the verdict is
# resting on the drift assumption rather than on the geometry.
THIN_MARGIN_FRACTION = 0.10

OUTCOMES = ("CANDIDATE_SUPPORTED", "LEADING_CANDIDATE_UNSTABLE", "NO_STRONG_CANDIDATE")


def _grade(value, reason, rule, **numbers):
    return {"grade": value, "reason": reason, "rule": rule, **numbers}


def grade_ais_coverage(track, release_at):
    """
    How well the vessel was tracked through the release window.

    Coverage is the precondition for every other AIS-derived term: a proximity
    score computed from four fixes across four hours is arithmetic on very
    little.
    """
    rule = (f"HIGH: >= {COVERAGE_HIGH_FIXES} fixes in the release window and no gap "
            f"over {COVERAGE_HIGH_GAP_MIN} min. MEDIUM: >= {COVERAGE_MEDIUM_FIXES} "
            f"fixes and no gap over {COVERAGE_MEDIUM_GAP_MIN} min. LOW otherwise. "
            "UNAVAILABLE: no fixes in the window at all.")

    release = parse_time(release_at)
    window = [p for p in (track or [])
              if release - timedelta(hours=2) <= parse_time(p["time"])
              <= release + timedelta(hours=2)]
    if not window:
        return _grade(UNAVAILABLE, "No AIS fix inside the release window.", rule,
                      fixes=0, largest_gap_minutes=None)

    times = sorted(parse_time(p["time"]) for p in window)
    gaps = [(times[i + 1] - times[i]).total_seconds() / 60 for i in range(len(times) - 1)]
    largest = round(max(gaps), 1) if gaps else 0.0

    if len(window) >= COVERAGE_HIGH_FIXES and largest <= COVERAGE_HIGH_GAP_MIN:
        g, why = HIGH, f"{len(window)} fixes, largest gap {largest:.0f} min."
    elif len(window) >= COVERAGE_MEDIUM_FIXES and largest <= COVERAGE_MEDIUM_GAP_MIN:
        g, why = MEDIUM, (f"{len(window)} fixes, but a {largest:.0f} min gap leaves the "
                          "track incompletely observed.")
    else:
        g, why = LOW, (f"{len(window)} fixes with a {largest:.0f} min gap — the vessel's "
                       "position through the window is largely inferred.")
    return _grade(g, why, rule, fixes=len(window), largest_gap_minutes=largest)


def grade_trajectory(trajectory_score, trajectory_status):
    """
    How much the vessel's movement relative to the estimated source tells us.

    Score and status answer different questions and can disagree: a vessel that
    closed on the source and then left scores high while its status reads
    "moving away". On t3 GRAND DOLPHIN does exactly that at 92.35. Reading either
    field alone would misreport it, so both are used and the disagreement is
    named rather than resolved.
    """
    rule = (f"HIGH: approaching and closed >= {TRAJECTORY_STRONG:.0f}% of its starting "
            f"distance. MEDIUM: approaching, or closed >= {TRAJECTORY_STRONG:.0f}% before "
            f"leaving. LOW: closed < {TRAJECTORY_WEAK:.0f}% and not approaching. "
            "UNAVAILABLE: no trajectory could be computed.")

    if trajectory_score is None or not trajectory_status:
        return _grade(UNAVAILABLE, "No trajectory was computed for this vessel.", rule,
                      score=None, status=None)

    approaching = trajectory_status.startswith("Approaching")
    if approaching and trajectory_score >= TRAJECTORY_STRONG:
        g, why = HIGH, (f"Approaching the estimated source and closed "
                        f"{trajectory_score:.0f}% of its starting distance.")
    elif approaching:
        g, why = MEDIUM, (f"Approaching, but only closed {trajectory_score:.0f}% of its "
                          "starting distance.")
    elif trajectory_score >= TRAJECTORY_STRONG:
        g, why = MEDIUM, (f"Closed {trajectory_score:.0f}% of its starting distance and "
                          "then moved away — it passed the source rather than heading "
                          "for it, which the status alone does not show.")
    elif trajectory_score >= TRAJECTORY_WEAK:
        g, why = LOW, (f"Moving away, having closed only {trajectory_score:.0f}%.")
    else:
        g, why = LOW, (f"Never came appreciably closer ({trajectory_score:.0f}%) and is "
                       "moving away.")
    return _grade(g, why, rule, score=round(trajectory_score, 2), status=trajectory_status)


def grade_behaviour(candidate):
    """
    Whether the Isolation Forest could speak, not whether it accused.

    Anything but `ok` is UNAVAILABLE. Grading a failed inference LOW would say
    the vessel behaved unremarkably, which is precisely the silent failure
    Phase 9 removed.
    """
    rule = ("HIGH: the model ran on this vessel's track. UNAVAILABLE: it did not — "
            "track too short, model unavailable, declined, or an inference error. "
            "A model that could not answer is never graded LOW.")

    status = candidate.get("behaviour_status")
    if not candidate.get("behaviour_available") or status != "ok":
        return _grade(UNAVAILABLE,
                      candidate.get("behaviour_reason")
                      or f"The behaviour model did not produce a score ({status}).",
                      rule, status=status, anomalous_points=None)

    points = candidate.get("anomalous_points")
    return _grade(HIGH,
                  (f"The model scored this track and flagged {points} fix"
                   f"{'' if points == 1 else 'es'} as anomalous."
                   if points is not None else "The model scored this track."),
                  rule, status=status, anomalous_points=points)


def grade_environment(environment_mode, environment_reason=None):
    """
    Whether any measured environmental data stood behind the drift at all.

    UNAVAILABLE for every candidate while no dataset is committed. That is the
    honest grade, not a gap to be filled: the drift is a stated constant and
    saying so is the point of the whole environment service.
    """
    rule = ("HIGH: sampled from a committed historical dataset covering this point "
            "and time. UNAVAILABLE: no dataset, or the point falls outside its "
            "coverage — the drift is then a stated assumption.")

    if environment_mode == "historical":
        return _grade(HIGH, "Current and wind came from the loaded dataset. A "
                            "reanalysis is itself a model output.", rule,
                      environment_mode=environment_mode)
    return _grade(UNAVAILABLE,
                  environment_reason or "No environmental dataset is loaded, so the "
                                        "drift behind this result is an assumption.",
                  rule, environment_mode=environment_mode)


def grade_counterfactual(result):
    """
    How much weight the vessel's own independent test can bear.

    Not whether it exonerates. A robust "not consistent" and a robust
    "consistent" are equally strong evidence; a verdict sitting 60 m from
    flipping is weak whichever way it points.
    """
    rule = (f"HIGH: the verdict survives the whole swept drift band and both modes "
            f"agree. MEDIUM: it holds but is sensitive to the drift, or the two modes "
            f"disagree. LOW: under EITHER drift mode the margin is under "
            f"{THIN_MARGIN_FRACTION:.0%} of that mode's own threshold, so the verdict "
            "rests on the assumption rather than the geometry. UNAVAILABLE: the test "
            "could not run.")

    if not result or not result.get("available"):
        return _grade(UNAVAILABLE,
                      (result or {}).get("reason")
                      or "The counterfactual could not be run for this vessel.",
                      rule, verdict=None)

    robustness = (result.get("robustness") or {})
    classification = robustness.get("classification")
    radius = result.get("consistency_radius_km") or 0
    margin = abs(result.get("margin_km") or 0)
    agree = (result.get("mode_comparison") or {}).get("verdicts_agree")
    verdict = "consistent" if result.get("within_envelope") else "not consistent"

    # The THINNER of the two modes decides, each against its own threshold.
    # Reading only the legacy margin misses the case Phase 16 exists to surface:
    # on t3 the top-ranked vessel holds its legacy verdict by 3.12 km of a 6.00 km
    # threshold and its environment-aware one by 0.06 km of 5.59. A verdict that
    # fragile under either assumption is fragile.
    env = result.get("environmental") or {}
    fractions = [(margin / radius, margin, radius, "the shipped drift")] if radius else []
    env_radius = env.get("consistency_radius_km") or 0
    if env.get("available") and env_radius:
        env_margin = abs(env.get("margin_km") or 0)
        fractions.append((env_margin / env_radius, env_margin, env_radius,
                          "the environment-aware drift"))
    thinnest = min(fractions) if fractions else None
    thin = bool(thinnest) and thinnest[0] < THIN_MARGIN_FRACTION

    if thin:
        _, thin_margin, thin_radius, which = thinnest
        g, why = LOW, (f"The verdict is {verdict}, but under {which} it holds by only "
                       f"{thin_margin:.2f} km against a {thin_radius:.2f} km threshold — "
                       "it turns on the drift assumption, not on where the vessel was.")
    elif classification == "robust" and agree is not False:
        # "Not consistent across the whole band" reads as "the results were
        # inconsistent" — the opposite of what it means. Name the verdict first.
        g, why = HIGH, (f'The verdict — {verdict} — holds across the whole swept drift '
                        "band, and both drift modes agree.")
    elif agree is False:
        g, why = MEDIUM, ("The two drift modes reach different verdicts for this vessel.")
    else:
        g, why = MEDIUM, (f"The verdict — {verdict} — holds, but it is "
                          f"{classification or 'sensitive'} to the drift assumption.")

    return _grade(g, why, rule, verdict=verdict,
                  miss_km=round(result.get("miss_distance_km"), 2)
                  if result.get("miss_distance_km") is not None else None,
                  margin_km=round(margin, 2),
                  threshold_km=radius, robustness=classification,
                  modes_agree=agree,
                  thinnest_margin_km=round(thinnest[1], 2) if thinnest else None,
                  thinnest_margin_under=thinnest[3] if thinnest else None)


# --- assembly ----------------------------------------------------------------

def grade_candidate(candidate, track, release_at, counterfactual, environment_mode,
                    environment_reason=None, outcome=None, consistent=None):
    """
    Every stream for one candidate, plus what is missing and the narrative.

    `outcome` and `consistent` are only needed for the narrative's opening line,
    which is set by the detection's verdict rather than the vessel's rank — see
    services/narrative.py. They arrive on a second pass, because the outcome
    cannot be known until every candidate has been graded.
    """
    streams = {
        "ais_coverage": grade_ais_coverage(track, release_at),
        "trajectory": grade_trajectory(candidate.get("trajectory_score"),
                                       candidate.get("trajectory_status")),
        "behaviour": grade_behaviour(candidate),
        "environment": grade_environment(environment_mode, environment_reason),
        "counterfactual": grade_counterfactual(counterfactual),
    }
    missing = [name for name, s in streams.items() if s["grade"] == UNAVAILABLE]
    return {
        "mmsi": candidate["mmsi"],
        "name": candidate["name"],
        "streams": streams,
        "narrative": (None if outcome is None else
                      narrative.build(candidate, streams, outcome,
                                      bool(consistent))),
        "unavailable": missing,
        "counts": {g: sum(1 for s in streams.values() if s["grade"] == g)
                   for g in (HIGH, MEDIUM, LOW, UNAVAILABLE)},
        "note": ("Grades say how much each stream can tell us, not how guilty the "
                 "vessel is. UNAVAILABLE is not a low score — it is no evidence "
                 "either way."),
    }


def assess_detection(candidates, graded, consistent_mmsis, ranking_change=None):
    """
    Whether ANY candidate is supported, and if one leads, whether that leader is
    stable.

    Three states rather than two, because the shipped demo produces both of the
    interesting ones. On the t3 GRAND DOLPHIN detection every candidate's
    counterfactual robustly says it could not have been the source, while the
    ranking still names a #1 at 70.54/100 — the system must be able to say that
    nobody is supported. On the NISALAH detection candidates ARE consistent, but
    which one leads changes with the drift assumption, and flattening that into
    "supported" would hide a finding the previous two phases went to some length
    to measure.

    Declining to name a vessel is a statement about evidence, never about
    innocence.
    """
    rules = {
        "NO_STRONG_CANDIDATE": ("No candidate's counterfactual is consistent, or there "
                                "are no candidates at all."),
        "LEADING_CANDIDATE_UNSTABLE": ("A consistent leader exists, but which vessel "
                                       "leads changes with the drift assumption, or its "
                                       "counterfactual margin is thin."),
        "CANDIDATE_SUPPORTED": "A consistent leader exists and it is stable.",
    }

    if not candidates:
        return {
            "outcome": "NO_STRONG_CANDIDATE",
            "leader": None, "reasons": ["No vessel was inside the search radius during "
                                        "the estimated release window."],
            "consistent_count": 0, "candidate_count": 0, "rules": rules,
            "means": _means("NO_STRONG_CANDIDATE"),
        }

    leader = candidates[0]
    reasons = []

    if not consistent_mmsis:
        outcome = "NO_STRONG_CANDIDATE"
        reasons.append(
            f"None of the {len(candidates)} candidates could have produced the observed "
            "slick under either drift assumption — every counterfactual misses by more "
            "than that drift could carry oil in the estimated time.")
        reasons.append(
            f"The ranking still orders them, and {leader['name']} still scores "
            f"{leader['final_suspect_score']:.2f}. That score measures proximity, "
            "trajectory and behaviour; it does not test whether the vessel's oil would "
            "have ended up where oil was seen. Here that test fails for all of them.")
    else:
        by_mmsi = {g["mmsi"]: g for g in graded}
        leader_graded = by_mmsi.get(leader["mmsi"], {})
        leader_cf = leader_graded.get("streams", {}).get("counterfactual", {})
        unstable = []

        if leader["mmsi"] not in consistent_mmsis:
            unstable.append(
                f"The top-ranked vessel, {leader['name']}, is not itself consistent — "
                "the candidates that are sit below it in the ranking.")
        if ranking_change and ranking_change.get("available") and ranking_change.get("top_changes"):
            unstable.append(
                f"Which vessel ranks first depends on the drift assumption: "
                f"{ranking_change['legacy_top']} under the shipped estimate, "
                f"{ranking_change['environmental_top']} under the environment-aware one.")
        if leader_cf.get("grade") == LOW:
            unstable.append(f"{leader['name']}'s counterfactual: {leader_cf.get('reason')}")

        outcome = "LEADING_CANDIDATE_UNSTABLE" if unstable else "CANDIDATE_SUPPORTED"
        reasons = unstable or [
            f"{leader['name']} leads the ranking, its counterfactual is consistent, and "
            "that verdict holds across the swept drift band."]

    return {
        "outcome": outcome,
        "leader": {"mmsi": leader["mmsi"], "name": leader["name"],
                   "score": leader["final_suspect_score"],
                   "counterfactual_consistent": leader["mmsi"] in consistent_mmsis},
        "reasons": reasons,
        "consistent_count": len(consistent_mmsis),
        "candidate_count": len(candidates),
        "rules": rules,
        "means": _means(outcome),
    }


def _means(outcome):
    """What the outcome does and does not claim. Stated, not left to the reader."""
    return {
        "NO_STRONG_CANDIDATE": (
            "The evidence available does not support naming any of these vessels as "
            "the source. That is a statement about the evidence, NOT a finding that "
            "any vessel is innocent, and not a claim that the spill had no source."),
        "LEADING_CANDIDATE_UNSTABLE": (
            "A vessel leads and its counterfactual is consistent, but the lead depends "
            "on an assumption nobody measured. Treat the ranking as a place to start "
            "looking rather than an answer."),
        "CANDIDATE_SUPPORTED": (
            "One vessel leads on evidence that holds up across the assumptions tested. "
            "Consistency with an estimated source is not proof of causation."),
    }[outcome]
