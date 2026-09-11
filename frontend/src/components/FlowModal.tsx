import {Info, X} from "lucide-react";
import {Badge} from "../ui";
import {STAGES} from "../stages";
import type {Traffic} from "../types";

export interface FlowModalProps {
  onClose: () => void;
  spillName?: string;
  traffic?: Traffic | null;
}

/**
 * HOW THIS WAS DERIVED — the investigation, as a document rather than a gate.
 *
 * The pipeline runs the moment images arrive; there is nothing for a user to
 * authorise, and making them click through five stages to see results they
 * already had was friction pretending to be rigour.
 *
 * What the staging was actually for still matters: a detection is a fact and
 * everything after it is an inference, and each inference has a limit that
 * belongs beside it. That survives here — every stage states what it
 * establishes and what it does not, in one place, on demand.
 */
export function FlowModal({onClose, spillName, traffic}: FlowModalProps) {
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="flowtitle">
      <div className="modalbox flowbox">
        <button className="close" onClick={onClose} aria-label="Close"><X /></button>

        <div className="reporthead">
          <div>
            <b>HOW THIS WAS DERIVED</b>
            <small>
              {spillName ? `THE SIGNATURE NEAR ${spillName.toUpperCase()}` : "THE INVESTIGATION PIPELINE"}
            </small>
          </div>
          <Badge tone="blue">AUTOMATIC</Badge>
        </div>

        <p className="flowintro">
          Every stage below runs on its own as soon as a satellite pass arrives — nothing
          here waits on an operator. They are listed in the order they execute, and each
          one states what it establishes <b>and what it does not</b>, because only the
          first is an observation.
        </p>

        <ol className="flowstages">
          {STAGES.map((s, i) => (
            <li key={s.key}>
              <span className="flownum" aria-hidden="true">{i + 1}</span>
              <div>
                <b>{s.label}</b>
                <span>{s.establishes}</span>
                <em>{s.limits}</em>
              </div>
            </li>
          ))}
        </ol>

        {/* The one thing about this demo that is constructed rather than
            recorded. It belongs next to the method, not buried in a data file. */}
        {traffic?.co_presence === "constructed" && (
          <div className="copresence">
            <b>These vessels were not at sea at the same time.</b>
            <span>
              Every identity, position, speed and course below is exactly as recorded in
              the AIS corpus — nothing is invented and no position is altered. What is
              constructed is the <b>timing</b>: each vessel's own timestamps are shifted by
              a constant offset so the fleet can be observed together across three passes.
              {traffic.co_presence_reason ? ` ${traffic.co_presence_reason}` : ""}
            </span>
          </div>
        )}

        <div className="disclaimer" style={{marginTop: 14}}>
          <Info size={14} />
          Only stage 1 is a measurement. Stages 2–5 are inferences built on it, and each
          inherits the error of the one before — the release window bounds the AIS search,
          and the estimated source positions it. A vessel ranked here was plausibly
          present; that is not the same as responsible.
        </div>
      </div>
    </div>
  );
}
