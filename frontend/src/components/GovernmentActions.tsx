import {Bell, Search, Shield, Waves} from "lucide-react";

export interface GovernmentActionsProps {
  /** Name of the leading candidate, if one exists — sharpens "Investigate". */
  topCandidate?: string | null;
  /** URGENT / ELEVATED / ROUTINE, from the response advisory. */
  urgency?: string | null;
}

/**
 * Recommended next steps for the authority handling the case. Framed as
 * actions to take, not background — this is a checklist, not an essay.
 */
export function GovernmentActions({topCandidate, urgency}: GovernmentActionsProps = {}) {
  const serious = urgency === "URGENT" || urgency === "ELEVATED";
  const actions = [
    {title: "Investigate", icon: Search, text: topCandidate
      ? `Pull AIS, voyage and cargo records for ${topCandidate} and the next-ranked candidates.`
      : "Pull AIS, voyage and cargo records for the ranked candidates."},
    {title: "Alert", icon: Bell, text: "Notify the port authority, flag state and vessels operating nearby."},
    {title: "Contain", icon: Waves, text: "Task containment and skimming assets to the modelled envelope."},
    {title: "Enforce", icon: Shield, text: serious
      ? "Detain the leading candidate pending inspection; refer for prosecution if evidence holds."
      : "Hold reporting and routing records on file for review."},
  ];
  return <section className="government-actions"><div className="eyebrow">RECOMMENDED ACTIONS</div>
    <div className="action-grid">{actions.map(({title, icon: Icon, text}) => <article key={title}><Icon size={19} /><div><b>{title}</b><p>{text}</p></div></article>)}</div>
  </section>;
}
