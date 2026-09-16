import {ModalFrame} from "./ModalFrame";
import {STAGES} from "../stages";

export interface FlowModalProps { onClose: () => void; spillName?: string; }

/**
 * HOW THIS WAS DERIVED — every stage runs automatically the moment a pass
 * arrives; nothing here is a gate the person has to click through. What
 * matters is the distinction each stage carries: what it establishes, and
 * what it does not. Only stage one is a measurement — everything after it
 * inherits the error of the step before.
 */
export function FlowModal({onClose, spillName}: FlowModalProps) {
  return <ModalFrame title="How this was derived" onClose={onClose} className="reportbox flowbox">
    <p className="flowintro">{spillName ? `The signature near ${spillName}, traced stage by stage.` : "The investigation pipeline, in the order it actually runs."}</p>
    <ol className="flowstages">
      {STAGES.map((s, i) => <li key={s.key}>
        <span className="flownum" aria-hidden="true">{i + 1}</span>
        <div><b>{s.label}</b><span>{s.establishes}</span><em>{s.limits}</em></div>
      </li>)}
    </ol>
  </ModalFrame>;
}
