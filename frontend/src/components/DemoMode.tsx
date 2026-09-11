import {useEffect, useState} from "react";
import {ChevronLeft, ChevronRight, X} from "lucide-react";
import {STAGES} from "../stages";
import type {Scan, SpillEntry} from "../types";

export interface DemoActions {
  /** Which detection is in view. Index into the pass's detections. */
  focusDetection: (index: number) => void;
  /** Select a vessel by ship id, which also expands its candidate row. */
  selectShip: (shipId?: string) => void;
  setShowEnvironment: (on: boolean) => void;
  /** Run the counterfactual for the currently expanded candidate. */
  askWhatIfTop: () => void;
  openReport: (open: boolean) => void;
}

export interface DemoModeProps {
  scan: Scan;
  spills: SpillEntry[];
  actions: DemoActions;
  onExit: () => void;
}

interface Step {
  id: string;
  title: string;
  /** Drawn from what the product already says — never written fresh here. */
  text: (ctx: {scan: Scan; spills: SpillEntry[]}) => string;
  target: string;
  /** Applied before the scroll, so the target exists by the time we look. */
  act?: (a: DemoActions, ctx: {spills: SpillEntry[]}) => void;
}

const stage = (key: string) => STAGES.find((s) => s.key === key);
const limit = (key: string) => stage(key)?.limits ?? "";

/**
 * THE TWELVE STEPS, PLUS ONE.
 *
 * The roadmap's twelve, in order, and one more between routing and report: the
 * second detection. The two detections are a demonstration pair — the first has
 * a leading candidate whose identity depends on an unmeasured constant, the
 * second is where the system declines to name anyone at all. A walkthrough that
 * showed only the confident case would misrepresent the system to exactly the
 * audience this mode exists for, so the honest half does not get dropped for a
 * round number.
 *
 * Every `text` is assembled from what the panel already says: the STAGES table's
 * own `establishes`/`limits`, the assessment's reasons, the measured figures in
 * the payload. No claim is written here that the product does not already make.
 */
const STEPS: Step[] = [
  {
    id: "pass",
    title: "A satellite pass arrives",
    target: '[data-demo="detection"]',
    act: (a, {spills}) => { a.openReport(false); a.focusDetection(0);
                            a.selectShip(spills[0]?.spill?.ship_id); },
    text: ({scan}) => `Pass ${String(scan.snapshot_id).toUpperCase()} covers `
      + `${scan.region ?? "the monitored area"}, revisited every `
      + `${scan.pass_interval_hours ?? "—"} h. Every monitored vessel carries one SAR `
      + `tile for this pass, and the models run as soon as it lands.`,
  },
  {
    id: "detection",
    title: "Detection",
    target: '[data-demo="detection"]',
    text: ({scan}) => `${stage("detection")?.establishes} `
      + `${scan.detections?.length ?? 0} of ${scan.scanned ?? 0} tiles came back positive. `
      + limit("detection"),
  },
  {
    id: "age",
    title: "How old the oil is",
    target: ".investbar",
    text: ({spills}) => `${stage("characterization")?.establishes} `
      + `That puts it at most ${spills[0]?.age?.estimated_hours ?? "—"} h old. `
      + limit("characterization"),
  },
  {
    id: "environment",
    title: "Environmental reconstruction",
    target: ".env",
    act: (a) => a.setShowEnvironment(true),
    text: ({scan}) => scan.environment?.environment_mode === "historical"
      ? `Wind and current come from the loaded historical dataset. A reanalysis is `
        + `itself a model output, so this is physically informed rather than measured.`
      : `No environmental dataset is loaded, so wind and current are stated constants — `
        + `the arrows on the map are identical everywhere because the field is one `
        + `assumed number. Every drift figure after this inherits that assumption.`,
  },
  {
    id: "source",
    title: "Where the oil came from",
    target: ".mapwrap",
    act: (a) => a.setShowEnvironment(false),
    text: ({spills}) => `${stage("hindcast")?.establishes} ${limit("hindcast")} `
      + `Two drift assumptions disagree by `
      + `${spills[0]?.drift_divergence?.source_separation_km ?? "—"} km on where that `
      + `source is, with no environmental data involved at all.`,
  },
  {
    id: "ais",
    title: "Searching the AIS",
    target: ".funnel",
    text: ({scan, spills}) => {
      const f = spills[0]?.ais?.funnel;
      return `${stage("ais")?.establishes} `
        + `${scan.traffic?.corpus_vessels ?? "—"} vessels in the corpus, `
        + `${f?.monitored ?? "—"} monitored this pass, ${f?.within_radius ?? "—"} inside `
        + `the search radius. ${limit("ais")}`;
    },
  },
  {
    id: "ranking",
    title: "Ranking the candidates",
    target: ".candwrap",
    text: ({spills}) => `${stage("candidates")?.establishes} ${limit("candidates")}`,
  },
  {
    id: "why",
    title: "Why this vessel",
    target: ".narrative",
    act: (a, {spills}) => a.selectShip(spills[0]?.candidates?.[0]?.ship_id),
    text: ({spills}) =>
      spills[0]?.evidence?.candidates?.[0]?.narrative?.beats?.[0]?.text
      ?? "The evidence behind the leading candidate, in plain terms.",
  },
  {
    id: "counterfactual",
    title: "Testing the leading candidate",
    target: ".whatifbox",
    act: (a) => a.askWhatIfTop(),
    text: () => `An independent check on the ranking: take the vessel's real AIS position `
      + `at the estimated release time, drift it forward, and see whether the oil would `
      + `have ended up where oil was actually seen. It can disagree with the ranking, `
      + `and both drift assumptions are run.`,
  },
  {
    id: "forecast",
    title: "Where it goes next",
    target: '[data-demo="forecast"]',
    // Re-select the DETECTED vessel: the forecast belongs to the spill, not to
    // whichever candidate the previous step expanded, and the card unmounts
    // while a candidate is selected. Caught by the driver as a dead end.
    act: (a, {spills}) => a.selectShip(spills[0]?.spill?.ship_id),
    text: () => `Forward projection at +6, +12, +24 and +48 h. Kinematic only — no oil `
      + `weathering, spreading or evaporation is modelled, and no environmental data `
      + `stands behind the drift.`,
  },
  {
    id: "routing",
    title: "Vessels in the way",
    target: '[data-demo="routing"]',
    text: ({spills}) => {
      const n = spills[0]?.risk?.at_risk_count ?? 0;
      return n === 0
        ? `No monitored vessel's projected track enters this spill's envelope within the `
          + `forecast horizon. Vessels that stay clear are not listed.`
        : `${n} vessel${n === 1 ? "" : "s"} projected to enter the envelope. Each track is `
          + `a straight-line projection at current speed and course — a prototype `
          + `trajectory, not navigational guidance.`;
    },
  },
  {
    id: "second",
    title: "The second detection — where the system declines",
    target: ".outcome",
    act: (a, {spills}) => { a.focusDetection(1); a.selectShip(spills[1]?.spill?.ship_id); },
    text: ({spills}) => {
      const a = spills[1]?.evidence?.assessment;
      if (!a) return "This pass holds a second detection.";
      return `${a.reasons[0]} ${a.means}`;
    },
  },
  {
    id: "report",
    title: "The report",
    target: ".reportbox",
    act: (a) => a.openReport(true),
    text: () => `Everything above as one document: the outcome first, then how it was `
      + `reached, the evidence behind each candidate, every counterfactual including the `
      + `exculpatory ones, what the models are and cannot do, and the provenance needed `
      + `to reproduce or dispute the run.`,
  },
];

/**
 * A guided run through the product — not a second copy of it.
 *
 * Each step scrolls the REAL panel into view and outlines it. Nothing here
 * renders a duplicate of a panel, because a duplicate is free to drift from the
 * thing it depicts, and a demo that shows a stale copy of your own system is
 * worse than no demo.
 *
 * The mode does not lock the interface. A live demo means someone interrupts to
 * ask "can you click that?", and a walkthrough that traps the presenter is worse
 * than one they can step out of and back into — `Next` re-establishes the step's
 * state rather than the mode forbidding anything.
 */
export function DemoMode({scan, spills, actions, onExit}: DemoModeProps) {
  const [i, setI] = useState(0);
  const step = STEPS[i];

  useEffect(() => {
    step.act?.(actions, {spills});
    // The action may mount the target (opening the report, expanding a
    // candidate), so look for it after the render it triggers.
    const t = window.setTimeout(() => {
      document.querySelectorAll(".demofocus").forEach((n) => n.classList.remove("demofocus"));
      const el = document.querySelector(step.target);
      if (el) {
        el.classList.add("demofocus");
        el.scrollIntoView({block: "center", behavior: "smooth"});
      }
    }, 350);
    return () => window.clearTimeout(t);
  }, [i]);

  useEffect(() => () => {
    document.querySelectorAll(".demofocus").forEach((n) => n.classList.remove("demofocus"));
  }, []);

  return (
    <div className="demobar" role="region" aria-label="Guided walkthrough">
      <div className="demostep">
        <span className="democount">{i + 1} / {STEPS.length}</span>
        <b>{step.title}</b>
      </div>
      <p className="demotext">{step.text({scan, spills})}</p>
      <div className="democtl">
        <button onClick={() => setI((n) => Math.max(0, n - 1))} disabled={i === 0}
                aria-label="Previous step"><ChevronLeft size={15} /> Back</button>
        <button className="primary" onClick={() => setI((n) => Math.min(STEPS.length - 1, n + 1))}
                disabled={i === STEPS.length - 1} aria-label="Next step">
          Next <ChevronRight size={15} />
        </button>
        <button className="ghost" onClick={onExit} aria-label="Exit walkthrough">
          <X size={15} /> Exit
        </button>
      </div>
    </div>
  );
}

export const DEMO_STEP_COUNT = STEPS.length;
