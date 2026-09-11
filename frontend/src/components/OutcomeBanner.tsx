import {AlertOctagon, AlertTriangle, CheckCircle2} from "lucide-react";
import type {DetectionAssessment, Outcome} from "../types";

export interface OutcomeBannerProps {
  assessment?: DetectionAssessment | null;
}

const PRESENTATION: Record<Outcome, {title: string; icon: typeof AlertOctagon; tone: string}> = {
  NO_STRONG_CANDIDATE: {
    title: "NO STRONG CANDIDATE",
    icon: AlertOctagon,
    tone: "none",
  },
  LEADING_CANDIDATE_UNSTABLE: {
    title: "LEADING CANDIDATE NOT STABLE",
    icon: AlertTriangle,
    tone: "unstable",
  },
  CANDIDATE_SUPPORTED: {
    title: "LEADING CANDIDATE SUPPORTED",
    icon: CheckCircle2,
    tone: "supported",
  },
};

/**
 * Whether the evidence supports naming anyone — stated above the ranking rather
 * than left for a reader to infer from it.
 *
 * The case this exists for is real and shipped: on the t3 GRAND DOLPHIN
 * detection every candidate's counterfactual says it could not have been the
 * source, while the ranking still shows a leader at 70.54/100. The list stays
 * visible below with its scores intact — a judge should be able to see that
 * number and see why it does not amount to support — but the top-level answer
 * is that nobody is supported.
 *
 * Declining to name a vessel is a statement about EVIDENCE. It is not a finding
 * that any vessel is innocent, and the banner says so in the backend's own
 * words rather than this file's.
 */
export function OutcomeBanner({assessment}: OutcomeBannerProps) {
  if (!assessment) return null;
  const {title, icon: Icon, tone} = PRESENTATION[assessment.outcome]
    ?? PRESENTATION.NO_STRONG_CANDIDATE;

  return (
    <div className={"outcome " + tone} role="status" title={assessment.rules?.[assessment.outcome]}>
      <div className="outcomehead">
        <Icon size={17} />
        <b>{title}</b>
        <span className="outcomecount">
          {assessment.consistent_count} of {assessment.candidate_count} candidate
          {assessment.candidate_count === 1 ? "" : "s"} consistent with the observation
        </span>
      </div>
      <ul className="outcomereasons">
        {assessment.reasons.map((r, i) => <li key={i}>{r}</li>)}
      </ul>
      <div className="outcomemeans">{assessment.means}</div>
    </div>
  );
}
