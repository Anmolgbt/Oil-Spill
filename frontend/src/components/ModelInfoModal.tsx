import {useEffect, useState} from "react";
import {Brain, Info, X} from "lucide-react";
import {Badge} from "../ui";
import {API, NOT_AVAILABLE} from "../lib/oiltrace";

export interface ModelInfoModalProps {
  onClose: () => void;
}

/**
 * The shape of GET /api/models, as far as this card reads it.
 *
 * Everything is optional on purpose: the endpoint omits what the artifacts do
 * not carry rather than substituting a zero, so the renderer has to cope with
 * absence at every level.
 */
interface ModelCard {
  name: string;
  kind: string;
  role?: string;
  task?: string;
  statement?: string;
  limitations?: string[];
  available?: boolean;
  device?: string | null;
  parameters?: number | null;
  input?: {format?: string; size?: string; preprocessing?: string[] | null;
           features?: string[] | null};
  output?: {returns?: string; normalisation?: string};
  validation?: Record<string, number | string | string[]> | null;
  validation_source?: string;
  model_type?: string | null;
  hyperparameters?: {n_estimators?: number | null; contamination?: number | null};
  corpus_reason?: string;
  known_flaw?: {detail: string} | null;
}

interface AttributionCard {
  name: string;
  kind: string;
  weights: {proximity: number; trajectory: number; behaviour: number};
  components: Record<string, string>;
  search_radius: {derivation: string; note: string};
  unavailable_term_rule: {rule: string; detail: string};
  statement: string;
  validation_note: string;
}

interface ModelsPayload {
  detection: ModelCard;
  behaviour: ModelCard;
  attribution: AttributionCard;
  separation: string;
  system_limitations?: string[];
}

/** Percentage from a 0-1 metric, or "Not available" — never a zero stand-in. */
const pct = (v: unknown) =>
  typeof v === "number" ? `${(v * 100).toFixed(2)}%` : NOT_AVAILABLE;

/**
 * AI MODEL INTELLIGENCE.
 *
 * Everything shown here comes from GET /api/models, which composes it from the
 * artifacts themselves. Nothing is hardcoded in this file — if a metric is
 * absent from the checkpoint or the validation JSON it renders as "Not
 * available" rather than as a number someone typed.
 *
 * The card exists mainly to make one distinction impossible to miss: two of the
 * three things below are trained models and the third is arithmetic.
 */
export function ModelInfoModal({onClose}: ModelInfoModalProps) {
  const [data, setData] = useState<ModelsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetch(`${API}/api/models`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => live && setData(d))
      .catch(() => live && setError("Could not load model information from the backend."));
    return () => { live = false; };
  }, []);

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modeltitle">
      <div className="modalbox modelbox">
        <button className="close" onClick={onClose} aria-label="Close"><X /></button>

        <div className="reporthead">
          <div>
            <b>AI MODEL INTELLIGENCE</b>
            <small>WHAT ACTUALLY POWERS THIS SYSTEM</small>
          </div>
          <Badge tone="blue">LIVE FROM ARTIFACTS</Badge>
        </div>

        {error && <p className="reportempty">{error}</p>}
        {!data && !error && <p className="reportempty">Loading model information…</p>}

        {data && <ModelCards data={data} />}
      </div>
    </div>
  );
}

/**
 * The three cards themselves, split out so the payload is non-null throughout
 * and every field below is read from a known shape rather than an `any`.
 */
function ModelCards({data}: {data: ModelsPayload}) {
  const cnn = data.detection, ais = data.behaviour, attr = data.attribution;

  return (
          <>
            <p className="flowintro">{data.separation}</p>

            {/* ---- 1. detection ---- */}
            <h3>1 · {cnn.name} — {cnn.kind}</h3>
            <div className="reportgrid">
              <div><small>ROLE</small><b>{cnn.role}</b></div>
              <div><small>TASK</small><b>{cnn.task}</b></div>
              <div><small>PARAMETERS</small><b>{cnn.parameters?.toLocaleString() ?? NOT_AVAILABLE}</b></div>
              <div><small>RUNNING ON</small><b>{cnn.available ? (cnn.device ?? "loaded") : "Not loaded"}</b></div>
            </div>
            <p className="reportnote">
              Input: {cnn.input?.format}, resized to {cnn.input?.size}
              {cnn.input?.preprocessing && ` · ${cnn.input?.preprocessing.join(" → ")}`}.
              {" "}Output: {cnn.output?.returns}.
            </p>

            <div className="reportgrid">
              <div><small>ACCURACY</small><b>{pct(cnn.validation?.accuracy)}</b></div>
              <div><small>PRECISION</small><b>{pct(cnn.validation?.precision)}</b></div>
              <div><small>RECALL</small><b>{pct(cnn.validation?.recall)}</b></div>
              <div><small>ROC-AUC</small><b>{pct(cnn.validation?.roc_auc)}</b></div>
            </div>
            <p className="reportnote">Measured on {cnn.validation_source}.</p>

            <div className="modelstatement">{cnn.statement}</div>

            {/* ---- 2. behaviour ---- */}
            <h3>2 · {ais.name} — {ais.kind}</h3>
            <div className="reportgrid">
              <div><small>MODEL</small><b>{ais.model_type ?? NOT_AVAILABLE}</b></div>
              <div><small>TREES</small><b>{ais.hyperparameters?.n_estimators ?? NOT_AVAILABLE}</b></div>
              <div><small>CONTAMINATION</small><b>{ais.hyperparameters?.contamination ?? NOT_AVAILABLE}</b></div>
              <div><small>FEATURES</small><b>{ais.input?.features?.length ?? NOT_AVAILABLE}</b></div>
            </div>
            <p className="reportnote">
              Features, in the order the saved scaler pins:{" "}
              <code>{(ais.input?.features ?? []).join(", ")}</code>.
              {" "}{ais.output?.returns}. Normalisation is {ais.output?.normalisation} —
              {" "}{ais.corpus_reason}
            </p>
            <div className="modelstatement">{ais.statement}</div>
            {ais.known_flaw && (
              <p className="reportnote">
                <b>Known flaw, reproduced deliberately.</b> {ais.known_flaw.detail}
              </p>
            )}

            {/* ---- 3. attribution — the distinction this card exists for ---- */}
            <h3>3 · {attr.name} — {attr.kind}</h3>
            <div className="reportgrid">
              <div><small>PROXIMITY</small><b>{attr.weights.proximity.toFixed(2)}</b></div>
              <div><small>TRAJECTORY</small><b>{attr.weights.trajectory.toFixed(2)}</b></div>
              <div><small>BEHAVIOUR</small><b>{attr.weights.behaviour.toFixed(2)}</b></div>
              <div><small>TRAINED MODEL?</small><b style={{color: "var(--warn)"}}>No</b></div>
            </div>
            <p className="reportnote">
              {Object.entries(attr.components).map(([k, v]) => (
                <span key={k}><b>{k}</b> — {v}<br /></span>
              ))}
              Search radius: {attr.search_radius.derivation}. {attr.search_radius.note}
            </p>
            <p className="reportnote">
              <b>When a term is unavailable:</b> {attr.unavailable_term_rule.detail}
            </p>
            <div className="modelstatement warn">{attr.statement}</div>
            <p className="reportnote">{attr.validation_note}</p>

            {/* ---- limitations ---- */}
            <h3>Limitations</h3>
            <ul className="modellimits">
              {[...(cnn.limitations ?? []), ...(ais.limitations ?? []),
                ...(data.system_limitations ?? [])].map((l: string, i: number) => (
                <li key={i}>{l}</li>
              ))}
            </ul>

            <div className="disclaimer" style={{marginTop: 14}}>
              <Info size={14} />
              Every figure on this page is read from the model artifacts at request time.
              Anything the artifacts do not carry is shown as "Not available" rather than
              estimated.
            </div>
          </>
  );
}

/** Header button that opens the card. */
export function ModelInfoButton({onClick}: {onClick: () => void}) {
  return (
    <button className="reportbtn modelbtn" onClick={onClick} title="What AI models power this system?">
      <Brain size={14} /> MODEL INFO
    </button>
  );
}
