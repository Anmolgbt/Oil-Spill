import {Check, CircleDashed, Minus, TriangleAlert} from "lucide-react";
import type {CandidateNarrativeData, NarrativeTone} from "../types";

export interface CandidateNarrativeProps {
  narrative?: CandidateNarrativeData | null;
}

const MARK: Record<NarrativeTone, {icon: typeof Check; label: string}> = {
  supports: {icon: Check, label: "Supports the association"},
  weakens: {icon: TriangleAlert, label: "Weakens the association"},
  missing: {icon: CircleDashed, label: "Evidence not available"},
  neutral: {icon: Minus, label: "Neither for nor against"},
};

/**
 * WHY THIS VESSEL, in sentences.
 *
 * Everything here comes from the backend (services/narrative.py) rather than
 * being composed in this file. The grade reasons, the assessment's meaning and
 * the model statements are all backend-owned for the same reason — one place to
 * correct the wording — and prose here describing the same facts is how two
 * wordings drift into contradicting each other.
 *
 * A `missing` beat is rendered exactly as prominently as a `supports` one. The
 * easiest way to lose the Phase 17 rule that UNAVAILABLE is not LOW is to let
 * the absent streams fall quietly to the bottom in grey.
 */
export function CandidateNarrative({narrative}: CandidateNarrativeProps) {
  if (!narrative?.beats?.length) return null;

  return (
    <div className="narrative">
      <div className="narrativehead">IN PLAIN TERMS</div>
      <ul className="narrativebeats">
        {narrative.beats.map((b, i) => {
          const {icon: Icon, label} = MARK[b.tone] ?? MARK.neutral;
          return (
            <li key={i} className={"beat " + b.tone}>
              <Icon size={14} aria-label={label} />
              <span>{b.text}</span>
            </li>
          );
        })}
      </ul>
      <div className="narrativedisclaimer">{narrative.disclaimer}</div>
    </div>
  );
}
