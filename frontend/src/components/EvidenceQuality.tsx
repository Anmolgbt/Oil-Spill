import type {CandidateEvidence, EvidenceStream, Grade} from "../types";

export interface EvidenceQualityProps {
  evidence?: CandidateEvidence | null;
}

/** Human labels for the payload's stream keys. */
const STREAM_LABEL: Record<string, string> = {
  ais_coverage: "AIS coverage",
  trajectory: "Trajectory",
  behaviour: "Behaviour model",
  environment: "Environmental data",
  counterfactual: "Counterfactual",
};

const ORDER = ["ais_coverage", "trajectory", "behaviour", "environment", "counterfactual"];

/**
 * EVIDENCE QUALITY — what each stream can actually tell us about this vessel.
 *
 * The grade is NOT a second suspicion score. It says how much weight the stream
 * can bear: a behaviour model that ran and found nothing is HIGH-quality
 * evidence of normality, and one that could not run is UNAVAILABLE. That
 * distinction is the whole point, and it is why UNAVAILABLE is styled apart
 * from LOW rather than below it.
 *
 * Each row carries the rule that produced it, on hover, so a reader can
 * disagree with the threshold rather than only with the verdict.
 */
export function EvidenceQuality({evidence}: EvidenceQualityProps) {
  if (!evidence) return null;
  const missing = evidence.unavailable ?? [];

  return (
    <div className="evidence">
      <div className="evidencehead">
        EVIDENCE QUALITY
        <small>how much each stream can tell us — not how suspicious it is</small>
      </div>

      {ORDER.map((key) => {
        const s = evidence.streams[key as keyof typeof evidence.streams] as EvidenceStream;
        if (!s) return null;
        return (
          <div key={key} className="evidencerow" title={s.rule}>
            <GradePill grade={s.grade} />
            <span className="evidencename">{STREAM_LABEL[key] ?? key}</span>
            <span className="evidencewhy">{s.reason}</span>
          </div>
        );
      })}

      {missing.length > 0 && (
        <div className="evidencemissing">
          <b>Missing evidence:</b>{" "}
          {missing.map((k) => STREAM_LABEL[k] ?? k).join(", ")}. Absent evidence is not
          evidence of anything — it is neither for nor against this vessel.
        </div>
      )}
    </div>
  );
}

/** UNAVAILABLE is deliberately not the bottom of a red-to-green ramp. */
function GradePill({grade}: {grade: Grade}) {
  return <span className={"gradepill g" + grade.toLowerCase()}>{grade}</span>;
}
