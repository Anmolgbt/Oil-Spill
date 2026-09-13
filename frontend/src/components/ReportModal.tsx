import {FileText} from "lucide-react";
import {fmt} from "../ui";
import {showPct, showCoord, imageSource} from "../lib/oiltrace";
import {ModalFrame} from "./ModalFrame";
import {EvidenceMetrics} from "./EvidencePanel";
import {GovernmentActions} from "./GovernmentActions";
import type {Candidate, Counterfactual, Detour, RiskOverview, Scan, Ship, SpillEntry, Weights} from "../types";

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

export function ReportModal({scan, detected, onClose, entry, index, candidates, reroute}: ReportModalProps) {
  const spill = entry?.spill ?? scan.spill;
  const source = entry?.source ?? scan.source;
  const top = candidates[0];
  const env = scan.environment;
  const demo = scan.traffic?.co_presence === "constructed" || scan.provenance?.simulation_seed != null;
  const incident = `OT-${scan.observed_at?.slice(0, 10).replace(/-/g, "") ?? "STORED"}-${Math.max(0, index) + 1}`;
  return <ModalFrame title="Monitoring report" onClose={onClose} className="reportbox">
    <div className="report-brand"><b>OILTRACE AI</b><span>Incident #{incident}</span></div>
    <p className="report-provenance">{demo ? "DEMO / SCENARIO DATA · recycled SAR tiles · aligned recorded AIS" : "See source provenance below"}</p>
    <h3>Satellite observation</h3>
    {imageSource(spill?.image_url) && <img className="report-sar" src={imageSource(spill?.image_url)} alt="Classified SAR input tile"/>}
    <div className="reportgrid">
      <div><small>DETECTION</small><b>{detected ? showPct(spill?.confidence, 1) : "No spill detected"}</b></div>
      <div><small>DRIFT ENVELOPE</small><b>{entry?.affected_area?.area_km2 != null ? `${fmt(entry.affected_area.area_km2, 1)} km²` : "Unavailable"}</b></div>
      <div><small>{demo ? "SCENARIO OBSERVATION TIME" : "OBSERVATION TIME"}</small><b>{scan.observed_at ? scan.observed_at.replace("T", " ").replace("Z", " UTC") : "Unavailable"}</b></div>
    </div>
    <p className="report-provenance">{scan.provenance?.sar_input?.source ?? "Source not supplied"}. Tile acquisition time and a measured slick boundary are not supplied. Map position uses an AIS anchor.</p>
    {detected && <>
      <h3>Source</h3>
      <div className="reportgrid">
        <div><small>PROBABLE SOURCE</small><b>{source ? `${showCoord(source.latitude, 4)}°, ${showCoord(source.longitude, 4)}°` : "Unavailable"}</b></div>
        <div><small>RELEASE WINDOW (EST.)</small><b>{entry?.age?.release_at && scan.observed_at ? `${entry.age.release_at.slice(11, 16)}–${scan.observed_at.slice(11, 16)} UTC` : "Unavailable"}</b></div>
        <div><small>WIND</small><b>{env?.wind ? `${fmt(env.wind.speed_ms, 1)} m/s · ${fmt(env.wind.direction_deg, 0)}°` : "Unavailable"}</b></div>
        <div><small>CURRENT</small><b>{env?.current ? `${fmt(env.current.speed_ms, 2)} m/s · ${fmt(env.current.direction_deg, 0)}°` : "Unavailable"}</b></div>
      </div>
      <small className="subtle">{env?.environment_mode === "historical" ? "Historical conditions" : "Assumed conditions"}</small>
      <div className="reportgrid"><div><small>RESULTANT DRIFT</small><b>{fmt(env?.drift?.speed_kmh, 2)} km/h · {fmt(env?.drift?.direction_deg, 0)}°</b></div><div><small>SOURCE CONFIDENCE</small><b>{source?.confidence == null ? "Not quantified" : showPct(source.confidence, 1)}</b></div></div>
      <h3>Top candidate</h3>
      {top ? <><div className="reportcandidate"><b>{top.name}</b><strong>{fmt(top.final_suspect_score, 1)} / 100</strong><span>{top.vessel_type} · MMSI {top.mmsi}</span></div>
        {entry?.evidence?.assessment && <p className="compact-result">{entry.evidence.assessment.outcome === "NO_STRONG_CANDIDATE" ? "No strong candidate" : entry.evidence.assessment.outcome === "LEADING_CANDIDATE_UNSTABLE" ? "Ranking unstable" : "Leading candidate supported"}</p>}
        <h3>Evidence</h3><EvidenceMetrics candidate={top} entry={entry}/></> : <p>No candidate available.</p>}
      <h3>Candidate evidence record</h3>
      <div className="exposure-table report-candidate-table"><table><thead><tr><th>Rank / vessel</th><th>Score</th><th>Source consistency</th></tr></thead><tbody>{candidates.map((candidate) => {const cf = entry?.evidence?.candidates.find((e) => e.mmsi === candidate.mmsi)?.streams.counterfactual; return <tr key={candidate.mmsi}><td>#{candidate.rank} {candidate.name}</td><td>{fmt(candidate.final_suspect_score, 1)}</td><td>{cf?.verdict ? String(cf.verdict) : "Not assessed"}{cf?.robustness ? ` · ${cf.robustness}` : ""}</td></tr>;})}</tbody></table></div>
      {top && <div className="report-evidence-notes">{(entry?.evidence?.candidates.find((e) => e.mmsi === top.mmsi)?.narrative?.beats ?? []).filter((beat) => beat.tone === "weakens").map((beat, i) => <p key={i}>{beat.text}</p>)}</div>}
      <h3>Forecast</h3><div className="reportgrid">{(entry?.forecast?.points ?? scan.forecast?.points ?? []).map((point) => <div key={point.hours_ahead}><small>+{point.hours_ahead} H · PROJECTED</small><b>{showCoord(point.latitude, 3)}°, {showCoord(point.longitude, 3)}°</b></div>)}</div>
      {reroute && <div className="reportcandidate"><b>Route · {reroute.ship.name}</b><strong>{fmt(reroute.detour.suggested_heading_deg, 0)}°</strong><span>{reroute.detour.already_inside_zone ? "Exit route" : reroute.detour.clears_spill_zone ? "Clears modelled zone" : "No clear route"} · {fmt(reroute.detour.detour_distance_km, 1)} km · simulated</span></div>}
      <h3>Potential exposure</h3>
      <div className="reportgrid"><div><small>WATERS TO MONITOR</small><b>{fmt(entry?.affected_area?.area_km2, 1)} km² · modelled envelope</b></div><div><small>OPERATIONAL EXPOSURE</small><b>{entry?.risk ? `${entry.risk.at_risk_count} vessels within ${entry.risk.forecast_horizon_hours} h` : "Not assessed"}</b></div><div><small>RESPONSE ORDER</small><b>{entry?.response_priority ?? "Not ranked"}</b></div><div><small>SENSITIVE AREAS / ECOLOGICAL DAMAGE</small><b>Not assessed</b></div></div>
      <p className="report-provenance">No habitat, protected-area or shoreline-exposure dataset is supplied. The envelope and forecast are potential exposure, not measured ecological damage.</p>
      <GovernmentActions/>
    </>}
    <p className="report-disclaimer">Attribution score is an investigation aid, not a legal determination of responsibility.</p>
    <button className="print" onClick={() => window.print()}><FileText size={15}/> Print / Save PDF</button>
  </ModalFrame>;
}
