import {ChevronRight} from "lucide-react";
import {Badge} from "../ui";
import {STAGES} from "../stages";

export interface InvestigationBarProps {
  spillName?: string;
  candidateCount: number;
  ageHours?: number;
  onOpenFlow: () => void;
}

/**
 * What the pipeline did, stated once.
 *
 * This used to gate the findings behind five clicks. It no longer does: the
 * models run as soon as a pass lands, so the results exist before anyone looks
 * at them and pretending otherwise was theatre.
 *
 * What is kept is the claim the staging was really making — that only the
 * detection is measured and everything after it is inferred. The rail shows the
 * pipeline that ran, and the popup carries each stage's limit in full.
 */
export function InvestigationBar({
  spillName, candidateCount, ageHours, onOpenFlow,
}: InvestigationBarProps) {
  return (
    <div className="investbar">
      <div className="investhead">
        <div className="investnow">
          <span className="eyebrow">INVESTIGATION</span>
          <b>COMPLETE</b>
          <small>
            ran automatically on this pass
            {spillName ? ` · signature near ${spillName}` : ""}
            {typeof ageHours === "number" ? ` · ≤ ${ageHours} h old` : ""}
            {" · "}{candidateCount} candidate{candidateCount === 1 ? "" : "s"} ranked
          </small>
        </div>
        <button className="startbtn" onClick={onOpenFlow}>
          HOW THIS WAS DERIVED <ChevronRight size={15} />
        </button>
      </div>

      {/* The pipeline that ran. Stage 1 is the only measurement; the rest are
          inferences, and the rail says so rather than colouring them alike. */}
      <ol className="investsteps ran">
        {STAGES.map((s, i) => (
          <li key={s.key} className={i === 0 ? "measured" : "inferred"}>
            <i aria-hidden="true" />
            <span className="visually-hidden">
              {i === 0 ? "Measured: " : "Inferred: "}
            </span>
            {s.label}
          </li>
        ))}
      </ol>

      <div className="investnote">
        <p>
          <b>Measured.</b> {STAGES[0].establishes}
        </p>
        <p className="limit">
          <b>Inferred.</b> Source, release window, ranking and forecast are all derived
          from that one detection — each inherits the error of the step before it.
          {" "}<button className="linkish" onClick={onOpenFlow}>See what each stage does not establish.</button>
        </p>
      </div>
    </div>
  );
}
