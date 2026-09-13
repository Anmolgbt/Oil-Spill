import {fmt} from "../ui";
import type {Counterfactual, Robustness, RobustnessFlip} from "../types";

/** The swept axes, in the words a reader uses rather than the payload's keys. */
const FLIP_PHRASE: Record<string, (f: RobustnessFlip) => string> = {
  drift_speed_kmh: (f) => `the drift were ${f.delta} km/h ${f.direction}`,
  drift_bearing_deg: (f) => `the drift bearing were ${f.delta}\u00b0 ${f.direction}`,
};

const ROBUST_LABEL: Record<string, string> = {
  robust: "Robust",
  "moderately sensitive": "Moderately sensitive",
  "highly sensitive": "Highly sensitive",
};

/**
 * COUNTERFACTUAL ROBUSTNESS — one line, deliberately.
 *
 * The verdict above rests on a drift vector nobody measured. This says how far
 * that assumption can move before the verdict changes, which is the honest
 * thing to report when the assumption cannot be checked. It is a sensitivity,
 * not an accuracy and not a probability: the backend sweeps a band chosen by
 * hand, so the percentage is a property of that band and is worded to say so.
 *
 * The drift band and the assumed age are stated separately because the backend
 * treats them separately — the age is bounded by an observation (the previous
 * pass was clear) and the drift vector by nothing at all. Quoting an age flip
 * against a drift-only percentage would read as one number contradicting the
 * other.
 */
export function RobustnessLine({robustness: r}: {robustness?: Robustness}) {
  if (!r || !r.available) return null;

  // Whichever of the two swept axes gives way first, measured as a share of
  // its own band so km/h and degrees can be compared at all.
  const drift = ([r.flips_at.drift_speed_kmh, r.flips_at.drift_bearing_deg]
    .filter(Boolean) as RobustnessFlip[]);
  const first = drift.length
    ? drift.reduce((a, b) => (a.delta / a.bound <= b.delta / b.bound ? a : b))
    : null;
  const axis = first === r.flips_at.drift_speed_kmh ? "drift_speed_kmh" : "drift_bearing_deg";
  const age = r.flips_at.assumed_age_hours;

  return (
    <div className={"robustline " + r.classification.split(" ")[0]} title={r.rule}>
      <span className="robusttag">{ROBUST_LABEL[r.classification] ?? r.classification}</span>
      <span>
        {Math.round(r.agreement_fraction * 100)}% agreement across tested drift assumptions.
        {first && <> Flips if {FLIP_PHRASE[axis](first)}.</>}
        {age && <> Age sensitivity: {age.delta} h {age.direction}.</>}
      </span>
    </div>
  );
}

/**
 * THE SAME TEST, THE OTHER WAY ROUND.
 *
 * The legacy counterfactual drifts at the hindcast's 1.5 km/h toward 135 deg;
 * the environment-aware one integrates through the field. Each is now judged
 * against the envelope its OWN drift implies — the legacy one used to be judged
 * against the map's circle, which is sized by a different vector.
 *
 * Measured on t3 the two AGREE on every candidate, and the margins invert. The
 * shipped top candidate is consistent by 3.12 km one way and by 0.06 km the
 * other. Reporting only "both say consistent" would hide exactly the thing
 * worth knowing, so the margin travels with the verdict.
 *
 * Agreement is not corroboration: with no dataset loaded, both runs are
 * unmeasured assumptions, merely different ones.
 */
export function ModeCompareLine({result}: {result: Counterfactual}) {
  if (!result.available) return null;
  const cmp = result.mode_comparison;
  const env = result.environmental;
  if (!cmp?.available || !env?.available) return null;

  // How close to the boundary the verdict sits, NOT the signed shift. For an
  // exculpatory verdict the margin is negative, so a "narrowing" signed shift
  // actually means the vessel is further outside and the verdict is FIRMER.
  // Reading the sign alone printed "the margin narrows from 8.20 km to
  // 13.12 km" for a vessel that had moved further from flipping.
  const wasFrom = Math.abs(cmp.legacy.margin_km);
  const nowFrom = Math.abs(env.margin_km);
  const closer = nowFrom < wasFrom;
  const agree = cmp.verdicts_agree;

  return (
    <div className="modecompare" title={cmp.meaning}>
      <span className="modetag">Environment-aware</span>
      <span>
        <b>{agree ? "Same verdict" : "Different verdict"}</b> · {env.within_envelope ? "consistent" : "not consistent"}
        {" · "}Miss {fmt(env.miss_distance_km, 2)} km · tolerance {fmt(env.consistency_radius_km, 2)} km
      </span>
    </div>
  );
}

/**
 * Both lines about the counterfactual, in the order they read: what the other
 * drift assumption says, then how far either assumption can move before the
 * verdict changes.
 */
export function CounterfactualLines({result}: {result: Counterfactual}) {
  if (!result.available) return null;
  return (
    <>
      <ModeCompareLine result={result} />
      <RobustnessLine robustness={result.robustness} />
    </>
  );
}
