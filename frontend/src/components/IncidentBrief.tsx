import {ArrowDown, Ship as ShipIcon} from "lucide-react";
import {fmt} from "../ui";
import {showPct} from "../lib/oiltrace";
import type {Candidate, Scan, SpillEntry} from "../types";
export function IncidentBrief({scan, entry, top, onEvidence}: {scan: Scan; entry?: SpillEntry; top?: Candidate; onEvidence: () => void}) {
  const sp = entry?.spill ?? scan.spill;
  const detected = scan.status === "SPILL_DETECTED";
  const assessment = entry?.evidence?.assessment;
  return <aside className="incident-brief"><div className="eyebrow">CURRENT INTELLIGENCE</div>
    <h2>{detected ? "Oil-like signature" : "No oil classified"}</h2><p>{detected && sp ? `Near ${sp.ship_name}` : "Continue monitoring this observation"}</p>
    <dl className="brief-facts"><div><dt>Detection confidence</dt><dd>{showPct(sp?.confidence, 1)}</dd></div><div><dt>Potential water exposure</dt><dd>{entry?.affected_area?.area_km2 != null ? `${fmt(entry.affected_area.area_km2, 1)} km²` : "Not assessed"}</dd></div><div><dt>Probable source</dt><dd>{entry?.source ? "Model estimate" : "Not available"}</dd></div><div><dt>Release window</dt><dd>{entry?.age?.release_at && scan.observed_at ? `${entry.age.release_at.slice(11, 16)}–${scan.observed_at.slice(11, 16)} UTC` : "Not available"}</dd></div><div><dt>Vessels in search</dt><dd>{entry?.candidates.length ?? scan.candidates?.length ?? 0}</dd></div><div><dt>Forecast available</dt><dd>{entry?.forecast?.points?.length ? `Up to +${Math.max(...entry.forecast.points.map((p) => p.hours_ahead))} h` : "Not available"}</dd></div></dl>
    <div className="brief-candidate"><div className="eyebrow"><ShipIcon size={14}/> LEADING INVESTIGATION CANDIDATE</div><div><h3>{top?.name ?? "No candidate"}</h3><strong>{top ? fmt(top.final_suspect_score, 1) : "—"}<small> /100</small></strong></div><p>{assessment?.outcome === "NO_STRONG_CANDIDATE" ? "No strong candidate supported" : assessment?.outcome === "LEADING_CANDIDATE_UNSTABLE" ? "Ranking changes with drift assumptions" : top ? `Rank #${top.rank} · ${top.vessel_type ?? "Vessel"}` : "No attribution result"}</p><button className="text-button" onClick={onEvidence} disabled={!top}>Review attribution & evidence <ArrowDown size={13}/></button></div>
  </aside>;
}
