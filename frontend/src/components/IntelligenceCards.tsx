import {Crosshair, Satellite, Ship as ShipIcon} from "lucide-react";
import {showPct, showCoord} from "../lib/oiltrace";
import {fmt} from "../ui";
import type {Candidate, Environment, Source, Spill, SpillEntry} from "../types";
export function IntelligenceCards({spill, source, entry, environment, observedAt, top, onEvidence}: {
  spill?: Spill | null; source?: Source | null; entry?: SpillEntry; environment?: Environment | null;
  observedAt?: string | null; top?: Candidate; onEvidence: () => void;
}) {
  const outcome = entry?.evidence?.assessment?.outcome;
  return <aside className="intelligence">
    <article className="intel-card"><div className="eyebrow"><Satellite size={15} /> SPILL DETECTION</div>
      <div className="intel-number">{spill ? showPct(spill.confidence, 1) : "—"}</div><small>Detection confidence</small>
      <div className="intel-pair"><span>Drift envelope</span><b>{entry?.affected_area?.area_km2 != null ? `${fmt(entry.affected_area.area_km2, 1)} km²` : "Unavailable"}</b></div>
      <div className="intel-caption">SAR classification{observedAt ? ` · ${observedAt.slice(11, 16)} UTC` : ""}</div>
    </article>
    <article className="intel-card"><div className="eyebrow"><Crosshair size={15} /> SOURCE RECONSTRUCTION</div>
      <h3>Probable source</h3><div className="source-position">{source ? `${showCoord(source.latitude, 3)}°, ${showCoord(source.longitude, 3)}°` : "Unavailable"}</div>
      <div className="intel-pair"><span>Release window</span><b>{entry?.age?.release_at && observedAt ? `${entry.age.release_at.slice(11, 16)}–${observedAt.slice(11, 16)} UTC` : "Unavailable"}</b></div>
      <div className="intel-pair"><span>Wind</span><b>{environment?.wind ? `${fmt(environment.wind.speed_ms, 1)} m/s · ${fmt(environment.wind.direction_deg, 0)}°` : "Unavailable"}</b></div>
      <div className="intel-pair"><span>Current</span><b>{environment?.current ? `${fmt(environment.current.speed_ms, 2)} m/s · ${fmt(environment.current.direction_deg, 0)}°` : "Unavailable"}</b></div>
      <small className="intel-caption">{!environment ? "Conditions unavailable" : environment.environment_mode === "historical" ? "Historical conditions" : "Assumed conditions"} · estimated source</small>
    </article>
    <article className="intel-card top-intel"><div className="eyebrow"><ShipIcon size={15} /> TOP CANDIDATE</div>
      <h3>{top?.name ?? "No candidate"}</h3><div className="intel-number">{top ? fmt(top.final_suspect_score, 1) : "—"}<small> / 100</small></div>
      <div className="candidate-status">{outcome === "NO_STRONG_CANDIDATE" ? "No strong candidate" : outcome === "LEADING_CANDIDATE_UNSTABLE" ? "Ranking unstable" : "Investigation candidate"}</div>
      <button className="primary-button" onClick={onEvidence} disabled={!top}>View Evidence</button>
    </article>
  </aside>;
}
