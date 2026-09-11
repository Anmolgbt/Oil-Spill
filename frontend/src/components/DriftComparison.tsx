import {AlertTriangle, Info} from "lucide-react";
import {Badge, fmt} from "../ui";
import {showCoord} from "../lib/oiltrace";
import {MAP_COLOURS as C} from "../mapColours";
import type {DriftDivergence, EnvironmentalDrift, Source} from "../types";

export interface DriftComparisonProps {
  divergence?: DriftDivergence | null;
  legacySource?: Source | null;
  environmentalSource?: EnvironmentalDrift | null;
  spillName?: string;
}

/** The three vectors, drawn from one origin. 60 px half-width. */
function VectorRosette({divergence: d}: {divergence: DriftDivergence}) {
  const R = 46;
  const arms = [
    {label: "Hindcast", ...d.legacy_vectors.hindcast, colour: C.hindcast},
    {label: "Forecast", ...d.legacy_vectors.forecast, colour: C.forecast},
    {label: "Environment", ...d.environment_vector, colour: C.environment},
  ];
  const fastest = Math.max(...arms.map((a) => a.speed_kmh)) || 1;

  return (
    <svg viewBox="-60 -60 120 120" className="rosette" role="img"
         aria-label="The three drift vectors this system carries, drawn from one origin">
      <circle cx="0" cy="0" r={R} fill="none" stroke="var(--line)" strokeWidth="1" />
      <text x="0" y="-49" textAnchor="middle" fontSize="8" fill="var(--ink-mute)">N</text>
      {arms.map((a) => {
        // Compass bearing to SVG: 0 is up, clockwise, y inverted.
        const rad = (a.speed_kmh && a.direction_deg * Math.PI) / 180;
        const len = (a.speed_kmh / fastest) * R;
        const x = len * Math.sin(rad), y = -len * Math.cos(rad);
        return (
          <g key={a.label}>
            <line x1="0" y1="0" x2={x} y2={y} stroke={a.colour} strokeWidth="2.5"
                  strokeLinecap="round" />
            <circle cx={x} cy={y} r="3" fill={a.colour} />
          </g>
        );
      })}
    </svg>
  );
}

/**
 * LEGACY vs ENVIRONMENT-AWARE — what a drift assumption changes.
 *
 * The uncomfortable result this panel exists to show: with NO environmental
 * dataset loaded, the two estimates put the source 4.56 km apart and, on the
 * first t3 detection, rank a different vessel first. Nothing about that is
 * caused by environmental data. It is the three drift constants this system
 * carries disagreeing with each other — the legacy hindcast's 1.5 km/h toward
 * 135 deg against the 1.394 km/h toward 181.2 deg the stated wind and current
 * imply.
 *
 * A reader who takes the gap for the effect of real data has been misled by
 * the panel, so the cause is stated at the top and again at the bottom in the
 * backend's own words.
 *
 * Neither estimate is labelled correct. Neither is validated. The shipped
 * ranking is the legacy one and the panel says so.
 */
export function DriftComparison({divergence: d, legacySource, environmentalSource,
                                 spillName}: DriftComparisonProps) {
  if (!d) return null;
  const rank = d.ranking_change;
  const historical = d.environment_mode === "historical";

  return (
    <div className="oilstrip">
      <div className="eyebrow">
        DRIFT ASSUMPTION — WHAT IT CHANGES <Badge tone="blue">SENSITIVITY</Badge>
        <span style={{marginLeft: "auto", textTransform: "none", letterSpacing: 0}}>
          {spillName} · {historical ? "historical field" : "no environmental dataset loaded"}
        </span>
      </div>

      {/* The headline, when the assumption changes who is ranked first. */}
      {rank?.available && rank.top_changes && (
        <div className="rankflip">
          <AlertTriangle size={16} />
          <span>
            <b>The top candidate changes with the drift assumption.</b>{" "}
            The shipped ranking puts <b>{rank.legacy_top}</b> first; re-ranked against the
            environment-aware source — same fleet, same search radius, same behaviour
            scores — <b>{rank.environmental_top}</b> is first instead. This is a
            sensitivity of the attribution to an assumption nobody measured, the same
            class of thing the per-candidate robustness line reports. It is not a sign
            that either ranking is wrong, and neither is validated.
          </span>
        </div>
      )}
      {rank?.available && !rank.top_changes && (
        <div className="ranksteady">
          <Info size={15} />
          <span>
            <b>{rank.legacy_top}</b> ranks first under both drift assumptions. The order
            below it still moves.
          </span>
        </div>
      )}

      <div className="driftgrid">
        <div className="driftcol">
          <small>ESTIMATED SOURCE</small>
          <div className="driftrow">
            <i className="dot" style={{background: C.hindcast}} />
            <span>Legacy</span>
            <b>{legacySource
              ? `${showCoord(legacySource.latitude, 4)}, ${showCoord(legacySource.longitude, 4)}`
              : "—"}</b>
          </div>
          <div className="driftrow">
            <i className="dot" style={{background: C.environment}} />
            <span>Environment-aware</span>
            <b>{environmentalSource?.latitude != null
              ? `${showCoord(environmentalSource.latitude, 4)}, ${showCoord(environmentalSource.longitude, 4)}`
              : "—"}</b>
          </div>
          <div className="driftsep">
            <b>{fmt(d.source_separation_km, 2)} km</b> apart
          </div>
        </div>

        <div className="driftcol">
          <small>FORECAST HORIZONS, APART</small>
          <div className="metrics">
            {Object.entries(d.forecast_separation_km).map(([h, km]) => (
              <div key={h}>
                <small>+{h} h</small>
                <b>{fmt(km, 2)} km</b>
              </div>
            ))}
          </div>
          <div className="subtle" style={{fontSize: 12, marginTop: 6}}>
            Closure check: forward-then-back misses by {fmt(d.closure.residual_km, 4)} km.
          </div>
        </div>

        <div className="driftcol rosettecol">
          <small>THE THREE VECTORS</small>
          <VectorRosette divergence={d} />
          <ul className="vectorkey">
            <li><i style={{background: C.hindcast}} />Hindcast {d.legacy_vectors.hindcast.speed_kmh} km/h · {d.legacy_vectors.hindcast.direction_deg}°</li>
            <li><i style={{background: C.forecast}} />Forecast {d.legacy_vectors.forecast.speed_kmh} km/h · {d.legacy_vectors.forecast.direction_deg}°</li>
            <li><i style={{background: C.environment}} />Environment {d.environment_vector.speed_kmh} km/h · {d.environment_vector.direction_deg}°</li>
          </ul>
        </div>
      </div>

      {rank?.available && rank.rows.length > 0 && (
        <>
          <div className="oilhead rankcmp">
            <span>Vessel</span><span>Legacy (shipped)</span>
            <span>Environment-aware</span><span>Change</span>
          </div>
          {rank.rows.map((r) => (
            <div key={r.mmsi} className="rankrow">
              <span className="vessel"><b>{r.name}</b></span>
              <span>#{r.legacy_rank} · {fmt(r.legacy_score, 2)}</span>
              <span>{r.dropped
                ? <em>outside the search radius</em>
                : <>#{r.environmental_rank} · {fmt(r.environmental_score, 2)}</>}</span>
              <span className={"delta" + (r.rank_delta ? (r.rank_delta > 0 ? " up" : " down") : "")}>
                {r.dropped ? "—"
                  : r.rank_delta === 0 ? "no change"
                    : `${r.rank_delta! > 0 ? "+" : ""}${r.rank_delta} place${Math.abs(r.rank_delta!) === 1 ? "" : "s"}`}
              </span>
            </div>
          ))}
        </>
      )}

      {/* The backend's own words, because this is the sentence that stops the
          panel being read backwards. */}
      <div className="driftcause">
        <Info size={14} />
        <span>{d.cause} The shipped ranking, counterfactual, search radius and report all
          use the legacy estimate.</span>
      </div>
    </div>
  );
}
