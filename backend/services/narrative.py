"""
WHY THIS VESSEL, in sentences.

Everything about a candidate is already on screen as numbers: three weighted
terms with their arithmetic, a robustness classification, a two-mode
counterfactual comparison, five evidence grades. What was missing was a reading
of them. This builds that reading.

WHY THIS IS BACKEND CODE. services/evidence.py already owns the grade reasons
and the assessment's `means`, and routes/models.py owns the model statements for
the same reason: one place to correct the wording. Prose in the frontend
describing facts the backend also describes is how two wordings end up
contradicting each other, and Phase 19's report and Phase 20's demo mode would
each need their own copy.

TWO RULES THAT SHAPE EVERYTHING BELOW.

  Beats are built from the GRADED STREAMS, not from raw fields. An unavailable
  stream therefore changes its sentence rather than losing it. Omission is the
  easiest way to lose the Phase 17 rule that UNAVAILABLE is not LOW: a narrative
  that simply says nothing about the environment reads as though the environment
  were fine.

  The opening depends on the DETECTION OUTCOME, not the rank. On a detection
  where the system has just declined to name anyone, opening "Ranked #1
  because..." for the top vessel would be an accusation it explicitly refused to
  make one panel earlier.

Nothing here asserts causation. "Ranked #1 because" describes consistency with
an estimated source and window.
"""
SUPPORTS, WEAKENS, MISSING, NEUTRAL = "supports", "weakens", "missing", "neutral"

# The streams a reader should be told about even when they say nothing, in the
# order the narrative walks them.
STREAM_ORDER = ("ais_coverage", "trajectory", "behaviour", "counterfactual", "environment")


def _beat(text, tone=NEUTRAL):
    return {"text": text, "tone": tone}


def _opening(candidate, outcome, consistent):
    """
    How the explanation starts — set by the detection's outcome, not the rank.
    """
    name, rank = candidate["name"], candidate.get("rank")
    score = candidate.get("final_suspect_score")

    if outcome == "NO_STRONG_CANDIDATE":
        return _beat(
            f"{name} ranks #{rank} on proximity, trajectory and behaviour, scoring "
            f"{score:.2f} of 100 — but on this detection no vessel's oil could have "
            "reached where oil was actually seen, this one included. The ranking says "
            "it was the closest match among the vessels present; it does not say it "
            "was the source.", WEAKENS)

    if not consistent:
        return _beat(
            f"{name} ranks #{rank} at {score:.2f} of 100, but its own counterfactual "
            "rules it out: drifting its real position forward does not reproduce the "
            "observed slick. Other candidates below it in the ranking do.", WEAKENS)

    if outcome == "LEADING_CANDIDATE_UNSTABLE" and rank == 1:
        return _beat(
            f"{name} ranks #1 at {score:.2f} of 100 and its oil could have reached the "
            "observed slick — but which vessel leads depends on a drift assumption "
            "nobody measured. Read this as where to start looking, not as an answer.",
            NEUTRAL)

    return _beat(
        f"{name} ranks #{rank} at {score:.2f} of 100, and drifting its real position "
        "forward does reproduce the observed slick. That is consistency with an "
        "estimated source and release window — not evidence that it caused the spill.",
        SUPPORTS)


def _where_and_when(candidate, coverage):
    """Where the vessel was, when, and how well that is actually known."""
    distance = candidate.get("minimum_distance_km")
    closest = candidate.get("closest_time")
    when = f" at {str(closest)[11:16]} UTC" if closest else ""

    if distance is None:
        return _beat("No closest approach was computed for this vessel.", MISSING)

    tone = SUPPORTS if distance < 5 else NEUTRAL
    fixes, gap = coverage.get("fixes"), coverage.get("largest_gap_minutes")
    if coverage.get("grade") == "UNAVAILABLE":
        detail = " Its position through the window is not observed at all."
        tone = MISSING
    elif coverage.get("grade") == "LOW":
        detail = (f" That is drawn from {fixes} fixes with a {gap:.0f}-minute gap, so "
                  "much of its path through the window is inferred rather than seen.")
        tone = WEAKENS
    else:
        detail = f" Tracked by {fixes} AIS fixes, largest gap {gap:.0f} minutes."

    return _beat(f"It came within {distance:.2f} km of the estimated source{when}.{detail}",
                 tone)


def _route(trajectory):
    """How the vessel's route relates to the estimated source."""
    grade = trajectory.get("grade")
    if grade == "UNAVAILABLE":
        return _beat("No trajectory could be computed, so how it was moving relative "
                     "to the estimated source is unknown.", MISSING)

    score, status = trajectory.get("score"), trajectory.get("status") or ""
    approaching = status.startswith("Approaching")

    if approaching and grade == "HIGH":
        return _beat(f"Its route closed on the estimated source across the window — "
                     f"{score:.0f}% of its starting distance — and it was still "
                     "approaching at the end.", SUPPORTS)
    if approaching:
        return _beat(f"It was approaching the estimated source, but only closed "
                     f"{score:.0f}% of its starting distance.", NEUTRAL)
    if grade == "MEDIUM":
        return _beat(f"It closed {score:.0f}% of its starting distance and then moved "
                     "away — it passed the estimated source rather than heading for it.",
                     NEUTRAL)
    return _beat(f"It was moving away from the estimated source and never came "
                 f"appreciably closer ({score:.0f}%).", WEAKENS)


def _behaviour(behaviour):
    """What the trained anomaly model made of the track, or why it could not."""
    if behaviour.get("grade") == "UNAVAILABLE":
        return _beat(
            f"The behaviour model produced no score for this vessel — "
            f"{behaviour.get('reason', 'it could not run')} That is missing evidence, "
            "not evidence that it behaved normally.", MISSING)

    points = behaviour.get("anomalous_points")
    if not points:
        return _beat("The Isolation Forest scored its track and flagged nothing "
                     "unusual. Unremarkable movement is a real finding, and it counts "
                     "against this vessel being the source no more than it counts for "
                     "it.", NEUTRAL)
    return _beat(f"The Isolation Forest flagged {points} of its AIS fixes as unusual "
                 "movement for this corpus. An anomaly is not a discharge, and not "
                 "causation.",
                 SUPPORTS if points > 5 else NEUTRAL)


def _counterfactual(name, counterfactual):
    """
    The independent test, and how much weight it can bear.

    Reads ONLY the graded stream, never the raw counterfactual — every number it
    needs travels with the grade. Reaching into the result made this throw the
    moment a caller had grades but no result object, which a test caught, and it
    was the one place the narrative broke its own rule about being built from
    the grades.
    """
    grade = counterfactual.get("grade")
    if grade == "UNAVAILABLE":
        return [_beat("The counterfactual could not be run for this vessel, so nothing "
                      "independently tests whether its oil would have reached the "
                      "slick.", MISSING)]

    verdict = counterfactual.get("verdict")
    consistent = verdict == "consistent"
    miss = counterfactual.get("miss_km")
    radius = counterfactual.get("threshold_km")
    if miss is None or radius is None:
        return [_beat("The counterfactual ran but reported no distance, so it cannot be "
                      "read here.", MISSING)]

    beats = [_beat(
        f"Drifting {name}'s real position forward puts its oil {miss:.2f} km from where "
        f"oil was actually seen, against the {radius:.2f} km that drift could have "
        f"carried it — {'consistent' if consistent else 'not consistent'} with the "
        "observation.", SUPPORTS if consistent else WEAKENS)]

    if grade == "LOW":
        thin = counterfactual.get("thinnest_margin_km")
        under = counterfactual.get("thinnest_margin_under") or "one of the two drifts"
        beats.append(_beat(
            f"That verdict is fragile. Under {under} it holds by only {thin:.2f} km, so "
            "it turns on the drift assumption rather than on where the vessel actually "
            "was.", WEAKENS))
    elif grade == "HIGH":
        beats.append(_beat("The verdict holds across the whole swept drift band and "
                           "under both drift assumptions, so it does not depend on "
                           "getting the drift exactly right.", NEUTRAL))

    if counterfactual.get("modes_agree") is False:
        beats.append(_beat("The two drift assumptions reach different verdicts for this "
                           "vessel, and neither is measured.", WEAKENS))
    return beats


def _environment(environment):
    """What the environmental reconstruction contributed — usually nothing yet."""
    if environment.get("grade") == "UNAVAILABLE":
        return _beat("No historical wind or current data stands behind any of this. "
                     "Every drift figure above comes from a stated constant, so the "
                     "estimated source and this vessel's distance from it inherit that "
                     "assumption.", MISSING)
    return _beat("Wind and current came from the loaded historical dataset rather than "
                 "a stated constant. A reanalysis is itself a model output, so this is "
                 "physically informed rather than measured.", NEUTRAL)


def build(candidate, streams, outcome, consistent):
    """
    The full explanation for one candidate, as ordered beats.

    `streams` is the graded evidence from services/evidence.py, and it is the
    ONLY input besides the candidate row. Passing grades rather than raw fields
    is what makes an unavailable stream change its sentence instead of vanishing
    from the narrative.
    """
    beats = [
        _opening(candidate, outcome, consistent),
        _where_and_when(candidate, streams.get("ais_coverage", {})),
        _route(streams.get("trajectory", {})),
        _behaviour(streams.get("behaviour", {})),
        *_counterfactual(candidate["name"], streams.get("counterfactual", {})),
        _environment(streams.get("environment", {})),
    ]

    missing = [name for name in STREAM_ORDER
               if streams.get(name, {}).get("grade") == "UNAVAILABLE"]
    return {
        "beats": beats,
        "missing_streams": missing,
        "counts": {tone: sum(1 for b in beats if b["tone"] == tone)
                   for tone in (SUPPORTS, WEAKENS, MISSING, NEUTRAL)},
        "disclaimer": ("Every line above describes consistency between this vessel's "
                       "recorded movement and an estimated source and release window. "
                       "None of it establishes that this vessel caused the spill."),
    }
