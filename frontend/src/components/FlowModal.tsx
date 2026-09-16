import {ModalFrame} from "./ModalFrame";
import type {Traffic} from "../types";
export interface FlowModalProps { onClose: () => void; spillName?: string; traffic?: Traffic | null; }
const pipeline = [
  ["SAR image", "Satellite image input"],
  ["Spill detection", "CNN classification"],
  ["Look-alike filter", "No separate filter supplied"],
  ["Backward hindcast", "Estimated release position"],
  ["AIS correlation", "Vessels in the release window"],
  ["Attribution score", "Proximity · trajectory · behaviour"],
  ["Forecast", "Projected drift"],
];
export function FlowModal({onClose, traffic}: FlowModalProps) {
  return <ModalFrame title="How this was derived" onClose={onClose}>
    <ol className="method-steps">{pipeline.map(([label, detail], index) => <li key={label}><span>{String(index + 1).padStart(2, "0")}</span><div><b>{label}</b><small>{detail}</small></div></li>)}</ol>
    {traffic?.co_presence === "constructed" && <small className="subtle">Recorded AIS · aligned scenario timestamps</small>}
  </ModalFrame>;
}
