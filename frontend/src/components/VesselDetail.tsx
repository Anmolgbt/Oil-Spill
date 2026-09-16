import {Badge, Card, fmt} from "../ui";
import {NOT_AVAILABLE, show, showCoord, showPct} from "../lib/oiltrace";
import type {Candidate, RiskEntry, Scan, Ship, SpillEntry} from "../types";

export interface VesselDetailProps {
  selected: Ship | null;
  /** The detection this vessel raised, if it raised one. */
  sel?: SpillEntry;
  selectedRisk?: RiskEntry | null;
  scan: Scan;
  /** Candidates for the detection in view, keyed by MMSI — this panel shows a
   *  vessel's rank when it is also a candidate. */
  rankByMmsi: Record<number, Candidate>;
}

/**
 * The right-hand column: what is known about the selected vessel.
 *
 * Extracted from App.tsx unchanged. Every value is passed in from the scan;
 * nothing is recomputed here.
 */
export function VesselDetail({selected, sel, selectedRisk, scan, rankByMmsi}: VesselDetailProps) {
  return (
    <aside className="right">
        <Card>
          <div className="eyebrow">
            VESSEL DETAIL
            {selected?.oil_detected && <Badge tone="red">OIL DETECTED</Badge>}
            {selectedRisk && <Badge tone="amber">AT RISK</Badge>}
          </div>
          {selected ? (
            <>
              <div className="vname">{selected.name}</div>
              <div className="subtle">MMSI {selected.mmsi} · {selected.vessel_type}</div>

              <div className="detailtop">
                <div>
                  {selected.image_url
                    ? <div className="scene"><img src={selected.image_url} alt="SAR tile" /></div>
                    : <div className="scene" />}
                  <div className="scene-meta">
                    <span>Sentinel-1 SAR · pass {String(scan.snapshot_id).toUpperCase()}</span>
                  </div>
                </div>
                <div>
                  <div className="metrics flush">
                    <div className="span2">
                      <small>CNN result</small>
                      <b style={{fontSize: 17, color: selected.oil_detected ? "var(--danger)" : "var(--ok)"}}>
                        {selected.prediction ?? NOT_AVAILABLE}
                      </b>
                    </div>
                    <div className="span2">
                      <small>Confidence</small>
                      <b className="lg">{selected.confidence ? showPct(selected.confidence) : NOT_AVAILABLE}</b>
                    </div>
                    <div className="span2">
                      <small>Suspect score</small>
                      <b>{rankByMmsi[selected.mmsi]
                          ? `${fmt(rankByMmsi[selected.mmsi].final_suspect_score)} / 100`
                          : "Not ranked"}</b>
                    </div>
                  </div>
                </div>
              </div>
              <div className="metrics">
                <div><small>Position</small><b>{showCoord(selected.latitude, 3)}, {showCoord(selected.longitude, 3)}</b></div>
                <div><small>Speed / course</small><b>{fmt(selected.speed_kt)} kt · {fmt(selected.course_deg, 0)}°</b></div>
              </div>
              <div className="metrics">
                <div><small>Last AIS fix</small><b>{selected.position_time ? selected.position_time.slice(5, 16).replace("T", " ") : NOT_AVAILABLE}</b></div>
                <div><small>AIS fixes held</small><b>{selected.track?.length ?? 0}</b></div>
              </div>

              {/* Findings belong to the vessel they were found on, so each
                  flagged ship shows its own spill characterisation. */}
              {sel && (
                <>
                  <div className="eyebrow spaced">SPILL FOUND HERE</div>
                                      {(
                    <div className="metrics flush">
                      <div><small>Max age</small><b>{show(sel.age?.estimated_hours, " h")}</b></div>
                      <div><small>Released (est.)</small><b>{sel.age?.release_at ? `${sel.age.release_at.slice(11, 16)} UTC` : NOT_AVAILABLE}</b></div>
                    </div>
                  )}
                  <div className="metrics">
                    <div><small>Impact envelope</small><b>{fmt(sel.affected_area?.radius_km)} km · {fmt(sel.affected_area?.area_km2, 0)} km²</b></div>
                    <div><small>Probable source</small>
                      <b>{showCoord(sel.source?.latitude, 3)}, {showCoord(sel.source?.longitude, 3)}</b></div>
                  </div>
                  <div className="metrics">
                    <div><small>Response priority</small>
                      <b style={{color: "var(--danger)"}}>
                        {sel.response_priority ?? NOT_AVAILABLE}
                        {sel.damage ? ` · ${fmt(sel.damage.priority_score)}/100` : ""}
                      </b></div>
                    <div><small>Recommended action</small>
                      <b>{sel.response
                          ? `${sel.response.urgency} — ${sel.response.action}`
                          : NOT_AVAILABLE}</b></div>
                  </div>
                  <div className="metrics">
                    <div className="span2">
                      <small>AIS searched</small>
                      <b>{sel.ais?.records_in_window != null
                          ? `${sel.ais.records_in_window} fixes in the window · ${fmt(sel.ais?.search_radius_km, 0)} km radius`
                          : NOT_AVAILABLE}</b>
                    </div>
                  </div>
                  <div className="metrics">
                    <div className="span2">
                      <small>Vessels near this source</small>
                      <b>{sel.candidates.length
                          ? `${sel.candidates.length} ranked — top ${sel.candidates[0].name} (${fmt(sel.candidates[0].final_suspect_score)}). Full breakdown below.`
                          : `None within ${fmt(sel.ais?.search_radius_km, 0)} km`}</b>
                    </div>
                  </div>
                </>
              )}

            </>
          ) : (
            <div className="empty">Select a vessel on the map or in the fleet list.</div>
          )}
      </Card>
    </aside>
  );
}
