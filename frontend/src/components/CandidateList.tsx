import {Ship as ShipIcon} from "lucide-react";
import {fmt} from "../ui";
import type {Candidate} from "../types";
export function CandidateList({candidates, selectedId, onSelect}: {
  candidates: Candidate[]; selectedId?: string; onSelect: (candidate: Candidate) => void;
}) {
  return <div className="vessel-list">
    {!candidates.length && <p className="empty">No candidates available</p>}
    {candidates.map((c) => <button key={c.mmsi} className={`vessel-card ${c.rank === 1 ? "leader" : ""} ${selectedId === c.ship_id ? "active" : ""}`} onClick={() => onSelect(c)}>
      <span className="vessel-rank">{c.rank}</span><span className="vessel-icon"><ShipIcon size={24} /></span>
      <span className="vessel-copy"><b>{c.name}</b><small>{c.vessel_type ?? "Vessel"}</small>
        <span className="mini-score"><i style={{width: `${Math.max(0, Math.min(100, c.final_suspect_score))}%`}} /></span>
      </span><strong>{fmt(c.final_suspect_score, 1)}</strong>
    </button>)}
  </div>;
}
