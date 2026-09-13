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

  if (candidates.length === 0) {
    return (
      <>
        <h3>Candidate ranking</h3>
        <p className="reportempty">
          No candidates within the search radius.
        </p>
      </>
    );
  }

  return (
    <>
      <h3>Candidate ranking</h3>

      {candidates.map((c) => {
        return (
          <div className="reportcandidate" key={c.mmsi}>
            <b>#{c.rank} {c.name}</b>
            <strong>{fmt(c.final_suspect_score, 2)}</strong>
            <span>
              MMSI {c.mmsi} · closest {fmt(c.minimum_distance_km, 2)} km · {c.trajectory_status}

            </span>
          </div>
        );
      })}

    </>
  );
}
