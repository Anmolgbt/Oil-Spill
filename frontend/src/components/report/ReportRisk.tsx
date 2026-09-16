import {GovernmentActions} from "../GovernmentActions";
import {fmt} from "../../ui";
import {NOT_AVAILABLE} from "../../lib/oiltrace";
import type {Detour, RiskOverview, Ship, SpillEntry} from "../../types";

/**
 * Who is projected to run into this slick, and what responders should do.
 *
 * Forward-looking, and a different question from attribution: these vessels are
 * not candidates and must never read as such. Vessels showing oil themselves are
 * excluded upstream — they are the casualty, not traffic to divert.
 */
export function ReportRisk({risk, entry, reroute}: {
  risk?: RiskOverview | null;
  entry?: SpillEntry;
  reroute?: {ship: Ship; detour: Detour; entryMinutes?: number} | null;
}) {
  const atRisk = risk?.at_risk ?? [];

  return (
    <>
      <h3>Assets at risk</h3>
      {atRisk.length === 0 ? (
        <p className="reportempty">
          No projected vessel exposure within {fmt(risk?.forecast_horizon_hours, 0)} h.
        </p>
      ) : (
        <>
          {atRisk.map((r) => (
            <div className="reportcandidate" key={r.ship_id}>
              <b>{r.name}</b>
              <strong>{r.risk}</strong>
              <span>
                MMSI {r.mmsi} · projected to enter in about{" "}
                {fmt(r.estimated_entry_minutes, 0)} minutes
                {r.spill_ship_name ? ` · from the ${r.spill_ship_name} detection` : ""}
              </span>
            </div>
          ))}
        </>
      )}

      <h3>Recommended response</h3>
      {entry?.response ? (
        <div className="reportgrid">
          <div><small>PRIORITY</small>
            <b>{entry.response_priority ?? NOT_AVAILABLE}
              {entry.damage ? ` · ${fmt(entry.damage.priority_score)}/100` : ""}</b></div>
          <div><small>ACTION</small>
            <b>{entry.response.urgency} — {entry.response.action}</b></div>
        </div>
      ) : (
        <p className="reportempty">No response advice was generated for this detection.</p>
      )}

      <GovernmentActions />

      {reroute && (
        <div className="reportcandidate">
          <b>Reroute — {reroute.ship.name}</b>
          <strong>{reroute.detour.clears_spill_zone ? "clears" : reroute.detour.already_inside_zone ? "exit route" : "does not clear"}</strong>
          <span>
            Heading {fmt(reroute.detour.original_heading_deg, 0)}° →{" "}
            {fmt(reroute.detour.suggested_heading_deg, 0)}°
            {" "}({reroute.detour.heading_change_deg > 0 ? "+" : ""}
            {fmt(reroute.detour.heading_change_deg, 0)}°) ·{" "}
            {fmt(reroute.detour.direct_distance_km, 2)} → {fmt(reroute.detour.detour_distance_km, 2)} km
            {" "}(+{fmt(reroute.detour.detour_distance_km - reroute.detour.direct_distance_km, 2)}) ·
            {" "}{fmt(reroute.detour.safety_buffer_km, 1)} km buffer.
            {" "}Simulated route avoidance, not maritime navigation guidance.
          </span>
        </div>
      )}
    </>
  );
}
