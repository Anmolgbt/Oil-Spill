import {FileText, Info, X} from "lucide-react";
import {NOT_AVAILABLE, show, showPct} from "../lib/oiltrace";
import {Badge, fmt} from "../ui";
import {STAGES} from "../stages";
import {ReportCandidates, ReportOutcome} from "./report/ReportEvidence";
import {ReportDrift, ReportEnvironment} from "./report/ReportEnvironment";
import {ReportRisk} from "./report/ReportRisk";
import {ReportProvenance} from "./report/ReportProvenance";
import type {Candidate, Counterfactual, Detour, RiskOverview, Scan, Ship, SpillEntry,
              Weights} from "../types";

export interface ReportModalProps {
  scan: Scan;
  detected: boolean;
  onClose: () => void;
  /** The detection this report covers, and its position among the pass's. */
  entry?: SpillEntry;
  index: number;
  total: number;
  candidates: Candidate[];
  weights: Weights;
  /** Counterfactuals actually run for this detection, keyed by MMSI. */
  counterfactuals: Record<number, Counterfactual>;
  /** The reroute, only if one was requested. */
  reroute?: {ship: Ship; detour: Detour; entryMinutes?: number} | null;
  causationProven?: boolean;
  liveInference?: boolean;
  /** Vessels projected to enter THIS detection's envelope. */
  risk?: RiskOverview | null;
}

/**
 * The take-away artefact.
 *
 * A report is read after the screen is gone, by someone who did not watch the
 * investigation happen — so it has to carry the reasoning, not just the
 * conclusion. It states each stage's finding beside that stage's limit, shows
 * the suspect arithmetic rather than only its total, and includes every
 * counterfactual that was run INCLUDING the exculpatory ones. Leaving out a
 * test that cleared a vessel would turn an honest instrument into a case for
 * the prosecution.
 *
 * Nothing here recomputes anything; every value is passed in from the scan.
 */
export function ReportModal({
  scan, detected, onClose, entry, index, total, candidates, weights,
  counterfactuals, reroute, causationProven, liveInference, risk,
}: ReportModalProps) {
  const spill = entry?.spill;
  // Every candidate's counterfactual, not only the ones a reader happened to
  // click. The backend runs all of them to grade the evidence (Phase 17), so a
  // report that listed only the clicked ones was silently incomplete — and
  // incompleteness that depends on where someone clicked is the worst kind,
  // since an omitted exculpatory result looks like an absent one.
  const tests = candidates.map((c) => ({
    c,
    graded: (entry?.evidence?.candidates ?? []).find((e) => e.mmsi === c.mmsi)
      ?.streams?.counterfactual,
    r: counterfactuals[c.mmsi] as Counterfactual | undefined,
  })).filter((t) => t.graded || t.r);

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="reporttitle">
      <div className="modalbox reportbox">
        <button className="close" onClick={onClose} aria-label="Close report"><X /></button>

        <div className="reporthead">
          <div>
            <b>OILTRACE</b>
            <small>MONITORING REPORT · PASS {String(scan.snapshot_id).toUpperCase()}</small>
          </div>
          <Badge tone={detected ? "red" : "blue"}>{detected ? "SPILL DETECTED" : "ALL CLEAR"}</Badge>
        </div>

        <h2 id="reporttitle">
          {detected ? `Oil signature near ${spill?.ship_name}` : "No oil signature detected"}
        </h2>
        {/* NOT scan.message: that describes the pass's strongest detection, so on
            a multi-detection pass it named a different vessel and confidence than
            the heading directly above it. In a document read after the fact that
            is not a cosmetic mismatch. */}
        <p>{detected && spill
          ? `Oil signature detected near ${spill.ship_name} in pass ${String(scan.snapshot_id).toUpperCase()} at ${showPct(spill.confidence)} confidence.`
          : scan.message}</p>

        {detected && total > 1 && (
          <p className="reportscope">
            This pass holds {total} separate detections. This report covers detection{" "}
            {index >= 0 ? index + 1 : 1} of {total} ({spill?.ship_name}). Select another
            vessel to report on it.
          </p>
        )}

        <div className="reportgrid">
          <div><small>CONFIDENCE</small><b>{detected ? showPct(spill?.confidence) : NOT_AVAILABLE}</b></div>
          <div><small>SPILL AREA</small><b>{NOT_AVAILABLE}</b></div>
          <div><small>EST. AGE</small><b>{detected ? show(entry?.age?.estimated_hours, " h") : NOT_AVAILABLE}</b></div>
          <div><small>CANDIDATES</small><b>{detected ? candidates.length : NOT_AVAILABLE}</b></div>
        </div>

        {detected && (
          <>
            {/* The conclusion first: a report read after the fact must not let
                a ranked list form a view before the paragraph saying nobody is
                supported. */}
            <ReportOutcome assessment={entry?.evidence?.assessment} />

            {/* ---- what was established, and what was not ---- */}
            <h3>How this conclusion was reached</h3>
            <ol className="reportstages">
              {STAGES.map((s) => (
                <li key={s.key}>
                  <b>{s.label}</b>
                  <span>{s.establishes}</span>
                  <em>{s.limits}</em>
                </li>
              ))}
            </ol>

            <h3>Findings</h3>
            <div className="reportgrid">
              <div><small>RELEASE (EST.)</small>
                <b>{entry?.age?.release_at ? `${entry.age.release_at.slice(11, 16)} UTC` : NOT_AVAILABLE}</b></div>
              <div><small>DRIFT ENVELOPE</small>
                <b>{fmt(entry?.affected_area?.radius_km)} km · {fmt(entry?.affected_area?.area_km2, 0)} km²</b></div>
              <div><small>AIS SEARCHED</small>
                <b>{entry?.ais?.records_in_window != null
                  ? `${entry.ais.records_in_window} fixes · ${fmt(entry.ais.search_radius_km, 0)} km`
                  : NOT_AVAILABLE}</b></div>
              <div><small>CANDIDATES IN RADIUS</small>
                <b>{entry?.ais?.funnel
                  ? `${entry.ais.funnel.within_radius} of ${entry.ais.funnel.monitored} monitored`
                  : NOT_AVAILABLE}</b></div>
            </div>

            <ReportEnvironment environment={scan.environment} />

            <ReportDrift source={entry?.source}
                         sourceEnvironmental={entry?.source_environmental}
                         forecast={entry?.forecast}
                         forecastEnvironmental={entry?.forecast_environmental}
                         divergence={entry?.drift_divergence} />

            <ReportCandidates candidates={candidates} weights={weights}
                              evidence={entry?.evidence?.candidates} />

            {/* ---- counterfactuals, including the ones that cleared a vessel ---- */}
            {tests.length > 0 && (
              <>
                <h3>Counterfactual tests</h3>
                <p className="reportnote">
                  Each takes the vessel's real AIS position at the estimated release time
                  and drifts it forward, then measures how far that lands from where oil
                  was actually seen — judged against how far that same drift could have
                  carried it. An independent check on the ranking, and it can disagree
                  with it. Every candidate is listed, and an exculpatory result is stated
                  as plainly as a corroborating one.
                </p>
                {tests.map(({c, graded, r}) => {
                  const miss = r?.available ? r.miss_distance_km : (graded?.miss_km as number);
                  const radius = r?.available
                    ? (r.consistency_radius_km ?? r.envelope_radius_km)
                    : (graded?.threshold_km as number);
                  const consistent = r?.available
                    ? r.within_envelope : graded?.verdict === "consistent";
                  return (
                    <div className="reportcandidate" key={`cf-${c.mmsi}`}>
                      <b>#{c.rank} {c.name}</b>
                      <strong>{miss != null ? `${fmt(miss, 2)} km` : "\u2014"}</strong>
                      <span>
                        {miss == null
                          ? (graded?.reason as string) ?? "The counterfactual could not be run."
                          : <>
                              {consistent ? "Consistent" : "Not consistent"}: the simulated
                              slick lands {fmt(miss, 2)} km from the observation, against the
                              {" "}{fmt(radius, 2)} km that drift could have carried it.
                              {r?.available && r.environmental?.available && <>
                                {" "}Through the environment field instead:{" "}
                                {fmt(r.environmental.miss_distance_km, 2)} km against{" "}
                                {fmt(r.environmental.consistency_radius_km, 2)} km,{" "}
                                {r.mode_comparison?.available && r.mode_comparison.verdicts_agree
                                  ? "the same verdict." : "a different verdict."}
                              </>}
                              {graded?.robustness != null && <>
                                {" "}The verdict is <b>{String(graded.robustness)}</b> to the
                                drift assumption.
                              </>}
                              {" "}Consistency, not proof.
                            </>}
                      </span>
                    </div>
                  );
                })}
              </>
            )}

            <ReportRisk risk={risk} entry={entry} reroute={reroute} />
          </>
        )}

        <ReportProvenance scan={scan} environment={scan.environment} />

        <div className="disclaimer" style={{marginTop: 14}}>
          <Info size={14} />
          This is an investigation record, not a determination. Ranking is analytical
          association with an estimated source and window: it does not establish that any
          vessel caused the spill
          {causationProven === false && ", and the system asserts no causation"}.
        </div>

        <button className="print" onClick={() => window.print()}>
          <FileText size={15} /> Print / Save PDF
        </button>
      </div>
    </div>
  );
}
