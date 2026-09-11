import {NOT_AVAILABLE, showCoord} from "../../lib/oiltrace";
import {fmt} from "../../ui";
import type {DriftDivergence, Environment, EnvironmentalDrift, Forecast, Source} from "../../types";

/**
 * What the environment actually was — which, with no dataset committed, is a
 * stated constant, and the section says so rather than presenting four numbers
 * as observations.
 */
export function ReportEnvironment({environment: env}: {environment?: Environment | null}) {
  const historical = env?.environment_mode === "historical";
  return (
    <>
      <h3>Environmental conditions</h3>
      <div className="reportgrid">
        <div><small>WIND</small><b>{env?.wind
          ? `${fmt(env.wind.speed_ms)} m/s · ${fmt(env.wind.direction_deg, 0)}°` : NOT_AVAILABLE}</b></div>
        <div><small>CURRENT</small><b>{env?.current
          ? `${fmt(env.current.speed_ms, 2)} m/s · ${fmt(env.current.direction_deg, 0)}°` : NOT_AVAILABLE}</b></div>
        <div><small>WAVE</small><b>{NOT_AVAILABLE}</b></div>
        <div><small>RESULTING DRIFT</small><b>{env?.drift
          ? `${fmt(env.drift.speed_kmh, 2)} km/h · ${fmt(env.drift.direction_deg, 0)}°` : NOT_AVAILABLE}</b></div>
      </div>
      <p className="reportnote">
        {historical
          ? `From ${env?.source}. A reanalysis is itself a model output, so this is
             physically informed rather than measured.`
          : `These are ASSUMED VALUES, not measurements — no environmental dataset is
             loaded. ${env?.environment_reason ?? ""} Every drift figure in this report,
             including the estimated source and every candidate's distance from it,
             inherits that assumption.`}
      </p>
    </>
  );
}

/**
 * Where the oil came from and where it goes — under both drift assumptions.
 *
 * The two differ by kilometres with no environmental data involved at all,
 * because the legacy hindcast and forecast use notebook constants that were
 * never derived from the stated wind and current. A report that showed one
 * number would be hiding a disagreement the system knows about.
 */
export function ReportDrift({source, sourceEnvironmental, forecast, forecastEnvironmental,
                             divergence}: {
  source?: Source | null;
  sourceEnvironmental?: EnvironmentalDrift | null;
  forecast?: Forecast | null;
  forecastEnvironmental?: EnvironmentalDrift | null;
  divergence?: DriftDivergence | null;
}) {
  const rank = divergence?.ranking_change;
  return (
    <>
      <h3>Estimated source region and forecast</h3>
      <p className="reportnote">
        The source is a back-projection of the observed slick, not an observation. Two
        estimates are shown because this system carries more than one drift assumption
        and they disagree.
      </p>
      <div className="reportgrid">
        <div><small>SOURCE — SHIPPED ESTIMATE</small>
          <b>{showCoord(source?.latitude, 4)}, {showCoord(source?.longitude, 4)}</b></div>
        <div><small>SOURCE — ENVIRONMENT-AWARE</small>
          <b>{sourceEnvironmental?.latitude != null
            ? `${showCoord(sourceEnvironmental.latitude, 4)}, ${showCoord(sourceEnvironmental.longitude, 4)}`
            : NOT_AVAILABLE}</b></div>
        <div><small>THEY DIFFER BY</small>
          <b>{divergence ? `${fmt(divergence.source_separation_km, 2)} km` : NOT_AVAILABLE}</b></div>
        <div><small>DRIFT VECTORS IN USE</small>
          <b>{divergence
            ? `${divergence.legacy_vectors.hindcast.speed_kmh} @ ${divergence.legacy_vectors.hindcast.direction_deg}° vs ${divergence.environment_vector.speed_kmh} @ ${divergence.environment_vector.direction_deg}°`
            : NOT_AVAILABLE}</b></div>
      </div>

      {(forecast?.points?.length ?? 0) > 0 && (
        <>
          <p className="reportnote">
            Forward projection. Kinematic, with no oil weathering, spreading or
            evaporation modelled.
          </p>
          <div className="reportforecast">
            <span><small>HORIZON</small></span>
            <span><small>SHIPPED ESTIMATE</small></span>
            <span><small>ENVIRONMENT-AWARE</small></span>
            <span><small>APART</small></span>
            {(forecast?.points ?? []).map((p, i) => {
              const alt = forecastEnvironmental?.points?.[i];
              const apart = divergence?.forecast_separation_km?.[String(p.hours_ahead)];
              return (
                <Row key={p.hours_ahead}
                     h={`+${p.hours_ahead} h`}
                     a={`${showCoord(p.latitude, 3)}, ${showCoord(p.longitude, 3)}`}
                     b={alt ? `${showCoord(alt.latitude, 3)}, ${showCoord(alt.longitude, 3)}` : NOT_AVAILABLE}
                     c={apart != null ? `${fmt(apart, 2)} km` : NOT_AVAILABLE} />
              );
            })}
          </div>
        </>
      )}

      <h3>Sensitivity to the drift assumption</h3>
      <p className="reportnote">
        {divergence?.cause ?? "No divergence measurement is available for this detection."}
      </p>
      {rank?.available && (
        <p className={"reportsensitivity " + (rank.top_changes ? "changed" : "steady")}>
          {rank.top_changes
            ? <><b>The top-ranked vessel changes with the drift assumption.</b> The shipped
                ranking puts {rank.legacy_top} first; re-ranked against the
                environment-aware source — same fleet, same search radius, same behaviour
                scores — {rank.environmental_top} is first instead. Neither ranking is
                validated.</>
            : <><b>{rank.legacy_top}</b> ranks first under both drift assumptions, though
                the order below it moves.</>}
        </p>
      )}
      {divergence?.closure && (
        <p className="reportnote">
          Closure check: integrating back to a source and forward again misses the
          observed slick by {fmt(divergence.closure.residual_km, 4)} km, so the two
          directions remain inverses of each other.
        </p>
      )}
    </>
  );
}

function Row({h, a, b, c}: {h: string; a: string; b: string; c: string}) {
  return <><span>{h}</span><span>{a}</span><span>{b}</span><span>{c}</span></>;
}
