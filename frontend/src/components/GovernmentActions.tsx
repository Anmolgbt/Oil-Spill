import {Bell, Search, Shield, Waves} from "lucide-react";
const actions = [
  {title: "Investigate", icon: Search, text: "Verify candidate AIS, voyage, cargo and operational records."},
  {title: "Alert", icon: Bell, text: "Notify nearby vessels and maritime authorities."},
  {title: "Contain", icon: Waves, text: "Task response assets; monitor spill movement and affected waters."},
  {title: "Enforce", icon: Shield, text: "Review reporting and routing compliance where evidence warrants."},
];
export function GovernmentActions() {
  return <section className="government-actions"><div className="eyebrow">INCIDENT RESPONSE <span className="eyebrowright">Recommended actions</span></div>
    <div className="action-grid">{actions.map(({title, icon: Icon, text}) => <article key={title}><Icon size={19} /><div><b>{title}</b><p>{text}</p></div></article>)}</div>
  </section>;
}
