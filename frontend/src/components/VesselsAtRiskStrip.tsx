import {ChevronRight} from "lucide-react";
import {Badge, fmt} from "../ui";
import {MAP_COLOURS as C} from "../mapColours";
import type {RiskEntry, RiskOverview, Ship} from "../types";

export interface VesselsAtRiskStripProps {
  risk?: RiskOverview | null;
  fleet: Ship[];
  selected: Ship | null;
  selectedRisk?: RiskEntry | null;
  /** Which vessel's detour is currently drawn on the map. */
  rerouteFor: string | null;
  setRerouteFor: (id: string | null) => void;
  onSelect: (shipId: string, spillShipId?: string | null) => void;
}

/**
 * Which vessels are projected to enter the affected area, and what they could
 * do about it.
 *
 * The detour for every at-risk vessel is already solved by the backend and is
 * shown as soon as one is selected. OPTIMIZE ROUTE does not compute it — it
 * draws it on the map, which is the part that changes what the map asserts and
 * so is the part that needs an explicit action.
 */
export function VesselsAtRiskStrip({
  risk: shownRisk, fleet, selected, selectedRisk, rerouteFor, setRerouteFor, onSelect,
}: VesselsAtRiskStripProps) {
  // A detection with no forward-risk block has nothing to say here, and every
  // field below would otherwise need its own guard.
  if (!shownRisk) return null;

  return (
        <div className="oilstrip" data-demo="routing">
          <div className="eyebrow">
            VESSELS AT RISK <Badge tone="amber">FORWARD PROJECTION</Badge>
            <span style={{marginLeft: "auto", textTransform: "none", letterSpacing: 0}}>
              {shownRisk.at_risk_count} of {shownRisk.vessels_checked} projected to enter · {shownRisk.safe_count} safe
            </span>
          </div>
          {shownRisk.at_risk.length ? (
            <>
              <div className="oilhead">
                <span>#</span><span>Vessel</span><span>Entry · from spill</span>
                <span>Detour</span><span>Risk</span>
              </div>
              {shownRisk.at_risk.map((r: RiskEntry, i: number) => (
                <button key={r.ship_id}
                        className={"oilrank " + (selected?.id === r.ship_id ? "selected" : "")}
                        onClick={() => onSelect(r.ship_id, r.spill_ship_id)}>
                  <span className="pos">
                    {i + 1}
                    <i className="dot" style={{background: C.atRisk}} />
                  </span>
                  <span className="vessel">
                    <b>{r.name}</b>
                    <small>MMSI {r.mmsi}</small>
                  </span>
                  <span className="meta">
                    ~{r.estimated_entry_minutes} min · from <b>{r.spill_ship_name}</b>
                    {r.response_priority ? ` (${r.response_priority})` : ""}
                  </span>
                  <span className="sus">
                    {r.detour
                      ? <>{fmt(r.detour.original_heading_deg, 0)}° → <b>{fmt(r.detour.suggested_heading_deg, 0)}°</b>
                          {" "}({r.detour.heading_change_deg > 0 ? "+" : ""}{fmt(r.detour.heading_change_deg, 0)}°)</>
                      : "No detour computed"}
                  </span>
                  <span className="pct" style={{color: r.risk === "HIGH" ? "var(--danger)" : "var(--warn)"}}>
                    {r.risk}
                  </span>
                </button>
              ))}
            </>
          ) : (
            <div className="empty">No monitored vessel is projected to enter the affected area.</div>
          )}
          {/* The detour is computed for every at-risk vessel and shown as soon as
              one is selected. OPTIMIZE ROUTE does not compute it — it draws it
              on the map, which is the part that needs an explicit action
              because it changes what the map is asserting. */}
          {selectedRisk?.detour && selected && (
            <div className="rerouteact">
                <div className="rerouteout">
                  <div className="rerouteouthead">
                    <b>ROUTE — {selected.name}</b>
                    <Badge tone={selectedRisk.detour.clears_spill_zone ? "ok" : "red"}>
                      {selectedRisk.detour.clears_spill_zone ? "CLEARS THE ZONE" : selectedRisk.detour.already_inside_zone ? "EXIT ROUTE" : "NO CLEAR ROUTE"}
                    </Badge>
                    {rerouteFor === selected.id ? (
                      <button className="undobtn" onClick={() => setRerouteFor(null)}>
                        Hide on map
                      </button>
                    ) : (
                      <button className="optimisebtn" onClick={() => setRerouteFor(selected.id)}>
                        SHOW ROUTE <ChevronRight size={15} />
                      </button>
                    )}
                  </div>
                  <div className="metrics three" style={{marginTop: 2}}>
                    <div>
                      <small>Heading</small>
                      <b>{fmt(selectedRisk.detour.original_heading_deg, 0)}° → {fmt(selectedRisk.detour.suggested_heading_deg, 0)}°
                        {" "}({selectedRisk.detour.heading_change_deg > 0 ? "+" : ""}{fmt(selectedRisk.detour.heading_change_deg, 0)}°)</b>
                    </div>
                    <div>
                      <small>Distance</small>
                      <b>{fmt(selectedRisk.detour.direct_distance_km, 2)} → {fmt(selectedRisk.detour.detour_distance_km, 2)} km
                        {" "}(+{fmt(selectedRisk.detour.detour_distance_km - selectedRisk.detour.direct_distance_km, 2)})</b>
                    </div>
                    <div>
                      <small>Safety buffer</small>
                      <b>{fmt(selectedRisk.detour.safety_buffer_km, 1)} km</b>
                    </div>
                  </div>

                </div>
            </div>
          )}

          <div className="subtle" style={{marginTop: 6, fontSize: 12}}>Simulated route · requires navigation review</div>
        </div>
  );
}
