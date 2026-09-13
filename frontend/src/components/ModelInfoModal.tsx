import {ModalFrame} from "./ModalFrame";
import {useEffect, useState} from "react";
import {Brain, X} from "lucide-react";
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
    <ModalFrame title="Model Info" onClose={onClose}>
        {error && <p className="reportempty">{error}</p>}
        {!data && !error && <p className="reportempty">Loading model information…</p>}

        {data && <ModelCards data={data} />}
    </ModalFrame>
  );
}

/**
 * The three cards themselves, split out so the payload is non-null throughout
 * and every field below is read from a known shape rather than an `any`.
 */
function ModelCards({data}: {data: ModelsPayload}) {
  const cnn = data.detection, ais = data.behaviour, attr = data.attribution;

  return <div className="model-summary">
    <section><h3>Spill detection</h3><b>{cnn.name}</b><p>{cnn.input?.size ?? "SAR image"} → oil / no oil · confidence</p></section>
    <section><h3>Vessel behaviour</h3><b>{ais.model_type ?? ais.name}</b><p>AIS track → anomaly score</p></section>
    <section><h3>Attribution</h3><b>Weighted association</b><p>Proximity {Math.round(attr.weights.proximity * 100)}% · trajectory {Math.round(attr.weights.trajectory * 100)}% · behaviour {Math.round(attr.weights.behaviour * 100)}%</p></section>
  </div>;
}

/** Header button that opens the card. */
export function ModelInfoButton({onClick}: {onClick: () => void}) {
  return (
    <button className="reportbtn modelbtn" onClick={onClick} title="What AI models power this system?">
      <Brain size={14} /> MODEL INFO
    </button>
  );
}
