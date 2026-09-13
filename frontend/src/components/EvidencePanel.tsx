import {fmt} from "../ui";
import type {Candidate, SpillEntry, Weights} from "../types";
export function EvidenceMetrics({candidate: c, entry}: {candidate: Candidate; entry?: SpillEntry}) {
  const cf = entry?.evidence?.candidates.find((e) => e.mmsi === c.mmsi)?.streams.counterfactual;
  const checks = [
    ["Closest approach time", c.closest_time ? `${c.closest_time.slice(11, 16)} UTC` : "Unavailable"],
    ["Source distance", c.minimum_distance_km != null ? `${fmt(c.minimum_distance_km, 2)} km` : "Unavailable"],
    ["Trajectory", c.trajectory_status ?? "Unavailable"],
    ["Behaviour", c.behaviour_available === false || c.behaviour_score == null ? "Unavailable" : `${fmt(c.behaviour_score, 1)} / 100`],
    ...(cf?.verdict ? [["Source consistency", String(cf.verdict).replace(/_/g, " ")]] : []),
  ];
  return <div className="evidence-metrics">{checks.map(([label, value]) => <div key={label}><small>{label}</small><b>{value}</b></div>)}</div>;
}
export function EvidencePanel({candidate: c, entry, weights}: {candidate: Candidate; entry?: SpillEntry; weights: Weights}) {
  const w = c.weights_applied ?? weights;
  return <>
    <div className="evidence-heading"><div><h3>{c.name}</h3><span>{c.vessel_type} · MMSI {c.mmsi}</span></div><strong>{fmt(c.final_suspect_score, 1)}<small> / 100</small></strong></div>
    <EvidenceMetrics candidate={c} entry={entry} />
    <div className="evidence-bars">{([
      ["Proximity", c.proximity_score, w.proximity], ["Trajectory", c.trajectory_score, w.trajectory], ["Behaviour", c.behaviour_score, w.behaviour],
    ] as const).map(([label, score, weight]) => <div key={label}><div><b>{label}</b><span>{score == null ? "Unavailable" : `${fmt(score, 1)} · ${Math.round(weight * 100)}% weight`}</span></div><div className="mini-score"><i style={{width: `${Math.max(0, Math.min(100, score ?? 0))}%`}} /></div></div>)}</div>
    {c.scored_on_partial_evidence && <small className="subtle">Partial evidence · weights adjusted</small>}
  </>;
}
