/**
 * The investigation, in the order the method actually runs.
 *
 * Every value for every stage arrives in the single /fleet/scan response — this
 * is disclosure sequencing, not fetching. Revealing it a step at a time is the
 * point: it keeps each claim next to the evidence that supports it, and stops
 * the interface from presenting an estimated source and a ranked suspect as if
 * they were both simply observed.
 *
 * `establishes` and `limits` are shown together, always. A stage that cannot
 * state its own limit does not belong in the sequence.
 */
export const STAGES = [
  {
    key: "detection",
    label: "DETECTION",
    establishes: "The CNN classified each vessel's SAR tile and found an oil signature.",
    limits: "A classifier, not a segmentation model — it gives a class and a confidence, no mask, no boundary, no area.",
  },
  {
    key: "characterization",
    label: "CHARACTERIZATION",
    establishes: "The previous pass was clear, so the oil is at most one revisit interval old.",
    limits: "An upper bound derived from the satellite cadence, not an age measured from the imagery.",
  },
  {
    key: "hindcast",
    label: "HINDCAST",
    establishes: "Drift traced backwards from the detection to a probable source position and release window.",
    limits: "A kinematic projection along an assumed drift vector. No wind, current or wave feed is connected.",
  },
  {
    key: "ais",
    label: "AIS SEARCH",
    establishes: "Historic AIS searched around the estimated release time and clipped to the search radius.",
    limits: "Filters traffic against an estimated source and an estimated window — both carry the hindcast's error.",
  },
  {
    key: "candidates",
    label: "CANDIDATES",
    establishes: "Surviving vessels scored on proximity, trajectory and the Isolation Forest's behaviour verdict.",
    limits: "Analytical association only. A high score means a vessel was plausibly present, never that it caused the spill.",
  },
] as const;

export const LAST_STAGE = STAGES.length - 1;
