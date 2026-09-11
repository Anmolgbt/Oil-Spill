import {NOT_AVAILABLE} from "../../lib/oiltrace";
import {fmt} from "../../ui";
import type {Candidate, CandidateEvidence, DetectionAssessment, Weights} from "../../types";

const OUTCOME_TITLE: Record<string, string> = {
  NO_STRONG_CANDIDATE: "No strong candidate",
  LEADING_CANDIDATE_UNSTABLE: "Leading candidate not stable",
  CANDIDATE_SUPPORTED: "Leading candidate supported",
};

/**
 * The conclusion, before the ranking that would otherwise imply one.
 *
 * A report is read after the screen is gone. If the ranked list came first, a
 * reader would have formed a view of who did it before reaching the paragraph
 * saying nobody is supported — so the outcome leads, exactly as it does on
 * screen.
 */
export function ReportOutcome({assessment}: {assessment?: DetectionAssessment | null}) {
  if (!assessment) return null;
  return (
    <>
      <h3>Investigation outcome</h3>
      <div className={"reportoutcome " + assessment.outcome.toLowerCase()}>
        <b>{OUTCOME_TITLE[assessment.outcome] ?? assessment.outcome}</b>
        <span className="reportoutcomecount">
          {assessment.consistent_count} of {assessment.candidate_count} candidates
          consistent with the observation
        </span>
        <ul>{assessment.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        <em>{assessment.means}</em>
      </div>
    </>
  );
}

/**
 * Candidate ranking with its arithmetic, then the evidence behind each one.
 *
 * The arithmetic uses each candidate's OWN applied weights. The report used to
 * print the headline weights and "0.00 (no verdict returned)" for a missing
 * behaviour term, which contradicts the re-weighting rule and would have shown
 * a sum that does not equal the printed total. Latent on the current demo,
 * where every behaviour score is available — wrong the moment one is not.
 */
export function ReportCandidates({candidates, weights, evidence}: {
  candidates: Candidate[];
  weights: Weights;
  evidence?: CandidateEvidence[];
}) {
  const byMmsi = Object.fromEntries((evidence ?? []).map((e) => [e.mmsi, e]));

  if (candidates.length === 0) {
    return (
      <>
        <h3>Candidate ranking</h3>
        <p className="reportempty">
          No vessel was within the AIS search radius during the estimated release
          window. A detection without a candidate is a finding, not a gap — nothing is
          inferred to fill it.
        </p>
      </>
    );
  }

  return (
    <>
      <h3>Candidate ranking</h3>
      <p className="reportnote">
        Score = {weights.proximity.toFixed(2)} × proximity
        {" + "}{weights.trajectory.toFixed(2)} × trajectory
        {" + "}{weights.behaviour.toFixed(2)} × behaviour, each term out of 100. Where a
        term could not be computed the remaining weights are renormalised rather than
        the missing term scoring zero, so a candidate's own weights are shown below.
      </p>
      {candidates.map((c) => {
        const w = c.weights_applied ?? weights;
        return (
          <div className="reportcandidate" key={c.mmsi}>
            <b>#{c.rank} {c.name}</b>
            <strong>{fmt(c.final_suspect_score, 2)}</strong>
            <span>
              MMSI {c.mmsi} · closest {fmt(c.minimum_distance_km, 2)} km · {c.trajectory_status}
              <br />
              {fmt(c.proximity_score, 2)} × {w.proximity.toFixed(2)}
              {" + "}{fmt(c.trajectory_score, 2)} × {w.trajectory.toFixed(2)}
              {c.behaviour_score == null
                ? ` (behaviour omitted — ${c.behaviour_reason ?? "no verdict returned"})`
                : ` + ${fmt(c.behaviour_score, 2)} × ${w.behaviour.toFixed(2)}`}
              {" = "}{fmt(c.final_suspect_score, 2)}
            </span>
          </div>
        );
      })}

      <h3>Evidence behind each candidate</h3>
      <p className="reportnote">
        Each grade says how much that stream can tell us, not how suspicious the vessel
        is. UNAVAILABLE is not a low score — it is no evidence either way.
      </p>
      {candidates.map((c) => {
        const e = byMmsi[c.mmsi];
        if (!e) return null;
        return (
          <div className="reportevidence" key={`ev-${c.mmsi}`}>
            <b>#{c.rank} {c.name}</b>
            <div className="reportgrades">
              {Object.entries(e.streams).map(([key, s]) => (
                <span key={key} className={"g" + s.grade.toLowerCase()}>
                  {key.replace("_", " ")}: <b>{s.grade}</b>
                </span>
              ))}
            </div>
            {/* The backend's sentences, not a second wording of the same facts. */}
            <ul className="reportbeats">
              {(e.narrative?.beats ?? []).map((b, i) => (
                <li key={i} className={b.tone}>{b.text}</li>
              ))}
            </ul>
            {e.narrative?.missing_streams?.length ? (
              <em className="reportmissing">
                Evidence not available: {e.narrative.missing_streams
                  .map((k) => k.replace("_", " ")).join(", ")}.
              </em>
            ) : null}
          </div>
        );
      })}
      <p className="reportnote">{evidence?.[0]?.narrative?.disclaimer ?? NOT_AVAILABLE}</p>
    </>
  );
}
