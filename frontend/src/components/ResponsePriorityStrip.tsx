import {Badge, fmt} from "../ui";
import {MAP_COLOURS as C} from "../mapColours";
import type {ResponsePriority, Ship, SpillEntry} from "../types";

export interface ResponsePriorityStripProps {
  priorities: ResponsePriority[];
  spills: SpillEntry[];
  fleet: Ship[];
  selected: Ship | null;
  onSelect: (shipId: string) => void;
}

/**
 * Which spill gets attention first.
 *
 * A triage order, not a measure of harm — the disclaimer under the table is
 * load-bearing and says what the score excludes.
 */
export function ResponsePriorityStrip({
  priorities: _priorities, spills, fleet, selected, onSelect,
}: ResponsePriorityStripProps) {
  const scan = {response_priorities: _priorities, spills};
  return (
        <div className="oilstrip">
          <div className="eyebrow">
            RESPONSE PRIORITY <Badge tone="red">ACTION REQUIRED</Badge>
            <span style={{marginLeft: "auto", textTransform: "none", letterSpacing: 0}}>
              {scan.response_priorities.length} live spill{scan.response_priorities.length === 1 ? "" : "s"}
            </span>
          </div>
          <div className="oilhead">
            <span>#</span><span>Spill</span><span>Impact envelope</span>
            <span>Recommended action</span><span>Priority</span>
          </div>
          {scan.response_priorities.map((p: ResponsePriority) => {
            const entry = (scan.spills || []).find((sp: SpillEntry) => sp.spill?.ship_id === p.ship_id);
            const act = entry?.response;
            return (
              <button key={p.ship_id}
                      className={"oilrank " + (selected?.id === p.ship_id ? "selected" : "")}
                      onClick={() => onSelect(p.ship_id)}>
                <span className="pos">
                  {p.response_priority}
                  <i className="dot" style={{background: C.spill}} />
                </span>
                <span className="vessel">
                  <b>{p.ship_name}</b>
                  <small>MMSI {p.mmsi}</small>
                </span>
                <span className="meta">
                  {fmt(p.envelope_radius_km)} km radius · {fmt(p.envelope_area_km2, 0)} km²
                </span>
                <span className="sus">
                  {act
                    ? <><b>{act.urgency}</b> · {act.action}</>
                    : "No action determined"}
                </span>
                <span className="pct">{fmt(p.priority_score)}</span>
              </button>
            );
          })}
          <div className="subtle" style={{marginTop: 6, fontSize: 12}}>
            Priority score ranks spills against each other for response order — it is not a measure of harm
            caused, oil volume or cost, and excludes shoreline proximity and habitat sensitivity. Escalation
            advice only: this prototype does not model response assets, crews or arrival times.
          </div>
        </div>
  );
}
