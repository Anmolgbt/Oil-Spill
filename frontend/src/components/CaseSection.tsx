import type {ReactNode} from "react";
export function CaseSection({id, number, title, question, children, action}: {id: string; number: string; title: string; question: string; children: ReactNode; action?: ReactNode}) {
  return <section id={id} className="case-section" aria-labelledby={`${id}-title`}><div className="case-section-heading"><span className="case-index">{number}</span><div><small>{question}</small><h2 id={`${id}-title`}>{title}</h2></div>{action && <div className="case-heading-action">{action}</div>}</div><div className="case-section-body">{children}</div></section>;
}
