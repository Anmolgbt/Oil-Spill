import {Fragment} from "react";
import {Polyline, Tooltip} from "react-leaflet";
import {MAP_COLOURS as C} from "../mapColours";
import type {Environment} from "../types";

export interface EnvironmentLayerProps {
  environment?: Environment | null;
  /** The area to tile with arrows: the same points the map fits to. */
  points?: [number, number][] | null;
}

/** How many arrows across the AOI. 5 x 5 is enough to read a field and few
 *  enough to still see the vessels underneath. */
const GRID = 5;

/** Arrow length, in degrees of latitude. Fixed rather than scaled by speed:
 *  one drift speed over the whole field carries no length information, and a
 *  varying field is better read by direction than by 25 slightly different
 *  line lengths. */
const ARROW_DEG = 0.022;
const HEAD_DEG = 0.008;
const HEAD_SPREAD = 150;

function arrow(lat: number, lon: number, bearingDeg: number) {
  // Compass bearing: 0 is north, clockwise. cos(lat) keeps the arrow pointing
  // where it says it does rather than shearing with longitude.
  const rad = (bearingDeg * Math.PI) / 180;
  const k = Math.cos((lat * Math.PI) / 180) || 1;
  const tip: [number, number] = [lat + ARROW_DEG * Math.cos(rad),
                                 lon + (ARROW_DEG * Math.sin(rad)) / k];
  const barb = (offset: number): [number, number] => {
    const b = rad + (offset * Math.PI) / 180;
    return [tip[0] + HEAD_DEG * Math.cos(b), tip[1] + (HEAD_DEG * Math.sin(b)) / k];
  };
  return {shaft: [[lat, lon], tip] as [number, number][],
          head: [barb(-HEAD_SPREAD), tip, barb(HEAD_SPREAD)] as [number, number][]};
}

/**
 * ENVIRONMENTAL INTELLIGENCE — the drift field the envelope is sized from.
 *
 * One arrow per node, showing EFFECTIVE DRIFT (current plus windage) rather
 * than three overlaid fields. Current, wind and their sum are given as numbers
 * and as a rosette in the comparison strip instead; drawing three arrows at
 * every node would bury the vessels the map exists to show.
 *
 * With no dataset loaded every arrow is identical, because the field is one
 * stated constant. That uniformity is the honest picture and the layer says so
 * rather than letting a regular grid of arrows imply measurement.
 *
 * Off by default. It is context, not a finding.
 */
export function EnvironmentLayer({environment: env, points}: EnvironmentLayerProps) {
  const drift = env?.drift;
  if (drift?.direction_deg == null || drift?.speed_kmh == null) return null;

  const lats = (points ?? []).map((p) => p[0]);
  const lons = (points ?? []).map((p) => p[1]);
  if (lats.length < 2) return null;

  const [lat0, lat1] = [Math.min(...lats), Math.max(...lats)];
  const [lon0, lon1] = [Math.min(...lons), Math.max(...lons)];
  const historical = env?.environment_mode === "historical";

  const nodes: {lat: number; lon: number}[] = [];
  for (let i = 0; i < GRID; i++) {
    for (let j = 0; j < GRID; j++) {
      nodes.push({
        lat: lat0 + ((lat1 - lat0) * (i + 0.5)) / GRID,
        lon: lon0 + ((lon1 - lon0) * (j + 0.5)) / GRID,
      });
    }
  }

  const label = historical
    ? `Effective drift ${drift.speed_kmh} km/h toward ${drift.direction_deg}° · from historical data`
    : `Effective drift ${drift.speed_kmh} km/h toward ${drift.direction_deg}° · ASSUMED FIELD — UNIFORM`;

  return (
    <>
      {nodes.map((n, i) => {
        const vector = i % 3 === 0 ? env?.wind : i % 3 === 1 ? env?.current : null;
        const kind = i % 3 === 0 ? "Wind" : i % 3 === 1 ? "Current" : "Drift";
        const bearing = vector?.direction_deg ?? drift.direction_deg as number;
        const a = arrow(n.lat, n.lon, bearing);
        const colour = kind === "Wind" ? "#b1d6e8" : kind === "Current" ? "#5bcfc6" : "#e2be6d";
        const arrowLabel = vector ? `${kind} ${vector.speed_ms} m/s · ${bearing}° · ${historical ? "historical sample" : "assumed"}` : label;
        return (
          <Fragment key={i}>
            <Polyline positions={a.shaft} pathOptions={{
              color: colour, weight: 2, opacity: historical ? 0.75 : 0.5,
              dashArray: historical ? undefined : "4 3"}}>
              <Tooltip>{arrowLabel}</Tooltip>
            </Polyline>
            <Polyline positions={a.head} pathOptions={{
              color: colour, weight: 2, opacity: historical ? 0.75 : 0.5}} />
          </Fragment>
        );
      })}
    </>
  );
}
