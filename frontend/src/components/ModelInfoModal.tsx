import {ModalFrame} from "./ModalFrame";
import {useEffect, useState} from "react";
import {Brain} from "lucide-react";
import {API, NOT_AVAILABLE} from "../lib/oiltrace";

export interface ModelInfoModalProps { onClose: () => void; }

/** The shape of GET /api/models, as far as this card reads it. Everything is
 *  optional on purpose — the endpoint omits what an artifact does not carry
 *  rather than substituting a zero, so absence renders as "Not available". */
interface ModelCard {
  name: string; kind: string; role?: string; task?: string; statement?: string;
  limitations?: string[]; available?: boolean; device?: string | null; parameters?: number | null;
  input?: {format?: string; size?: string; preprocessing?: string[] | null; features?: string[] | null};
  output?: {returns?: string; normalisation?: string};
  validation?: Record<string, number | string | string[]> | null; validation_source?: string;
  model_type?: string | null; hyperparameters?: {n_estimators?: number | null; contamination?: number | null};
  corpus_reason?: string; known_flaw?: {detail: string} | null;
}
interface AttributionCard {
  name: string; kind: string; weights: {proximity: number; trajectory: number; behaviour: number};
  search_radius: {derivation: string; note: string}; statement: string; validation_note: string;
}
interface ModelsPayload {
  detection: ModelCard; behaviour: ModelCard; attribution: AttributionCard;
  separation: string; system_limitations?: string[];
}

/** Percentage from a 0-1 metric, or "Not available" — never a zero stand-in. */
const pct = (v: unknown) => typeof v === "number" ? `${(v * 100).toFixed(1)}%` : NOT_AVAILABLE;
const params = (v: unknown) => typeof v !== "number" ? NOT_AVAILABLE
  : v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : String(v);

/**
 * What actually powers this system, read live from GET /api/models — nothing
 * here is hardcoded. The card exists to make one distinction impossible to
 * miss: two of the three things below are trained, validated models; the
 * third (attribution) is a deterministic weighted sum, not a model at all.
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

  return <ModalFrame title="Model info" onClose={onClose} className="reportbox">
    {error && <p className="reportempty">{error}</p>}
    {!data && !error && <p className="reportempty">Loading model information…</p>}
    {data && <ModelCards data={data} />}
  </ModalFrame>;
}

function ModelCards({data}: {data: ModelsPayload}) {
  const cnn = data.detection, ais = data.behaviour, attr = data.attribution;
  return <>
    <p className="flowintro">{data.separation}</p>

    <h3>1 · {cnn.name} — {cnn.kind}</h3>
    <div className="reportgrid">
      <div><small>PARAMETERS</small><b>{params(cnn.parameters)}</b></div>
      <div><small>RUNNING ON</small><b>{cnn.available ? (cnn.device ?? "loaded") : "Not loaded"}</b></div>
      <div><small>INPUT</small><b>{cnn.input?.size ?? NOT_AVAILABLE}</b></div>
      <div><small>OUTPUT</small><b>{cnn.output?.returns ?? "class + confidence"}</b></div>
    </div>
    <div className="reportgrid">
      <div><small>ACCURACY</small><b>{pct(cnn.validation?.accuracy)}</b></div>
      <div><small>PRECISION</small><b>{pct(cnn.validation?.precision)}</b></div>
      <div><small>RECALL</small><b>{pct(cnn.validation?.recall)}</b></div>
      <div><small>ROC-AUC</small><b>{pct(cnn.validation?.roc_auc)}</b></div>
    </div>
    <p className="reportnote">Measured on {cnn.validation_source ?? "a held-out validation set"}.</p>
    {cnn.statement && <div className="modelstatement">{cnn.statement}</div>}

    <h3>2 · {ais.name} — {ais.kind}</h3>
    <div className="reportgrid">
      <div><small>MODEL</small><b>{ais.model_type ?? NOT_AVAILABLE}</b></div>
      <div><small>TREES</small><b>{ais.hyperparameters?.n_estimators ?? NOT_AVAILABLE}</b></div>
      <div><small>CONTAMINATION</small><b>{typeof ais.hyperparameters?.contamination === "number" ? `${(ais.hyperparameters.contamination * 100).toFixed(0)}%` : NOT_AVAILABLE}</b></div>
      <div><small>FEATURES</small><b>{ais.input?.features?.length ?? NOT_AVAILABLE}</b></div>
    </div>
    {ais.statement && <div className="modelstatement">{ais.statement}</div>}
    {ais.known_flaw && <p className="reportnote"><b>Known flaw, reproduced deliberately.</b> {ais.known_flaw.detail}</p>}

    <h3>3 · {attr.name} — {attr.kind}</h3>
    <div className="reportgrid">
      <div><small>PROXIMITY</small><b>{attr.weights.proximity.toFixed(2)}</b></div>
      <div><small>TRAJECTORY</small><b>{attr.weights.trajectory.toFixed(2)}</b></div>
      <div><small>BEHAVIOUR</small><b>{attr.weights.behaviour.toFixed(2)}</b></div>
      <div><small>TRAINED MODEL?</small><b style={{color: "var(--warn)"}}>No</b></div>
    </div>
    <p className="reportnote">Search radius: {attr.search_radius.derivation}</p>
    <div className="modelstatement warn">{attr.statement}</div>
  </>;
}

/** Header button that opens the card. */
export function ModelInfoButton({onClick}: {onClick: () => void}) {
  return <button className="reportbtn modelbtn" onClick={onClick} title="What AI models power this system?">
    <Brain size={14} /> Model info
  </button>;
}
