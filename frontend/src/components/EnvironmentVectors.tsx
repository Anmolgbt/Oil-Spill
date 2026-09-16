import {fmt} from "../ui";
import type {Environment} from "../types";
export function EnvironmentVectors({environment: env}: {environment?: Environment}) {
  const vectors = [
    {name: "Wind", speed: env?.wind?.speed_ms, direction: env?.wind?.direction_deg, unit: "m/s", color: "#628dac"},
    {name: "Current", speed: env?.current?.speed_ms, direction: env?.current?.direction_deg, unit: "m/s", color: "#278c92"},
    {name: "Resultant drift", speed: env?.drift?.speed_kmh, direction: env?.drift?.direction_deg, unit: "km/h", color: "#ad7d25"},
  ];
  return <div className="environment-vectors">{vectors.map((vector) => <div className="environment-vector" key={vector.name}>
    <svg viewBox="0 0 90 90" role="img" aria-label={`${vector.name} ${vector.direction == null ? "unavailable" : `${vector.direction} degrees toward`}`}>
      <circle cx="45" cy="45" r="30" fill="none" stroke="#d9e4ea"/><path d="M45 15V75 M15 45H75" stroke="#e8eef2"/><text x="45" y="10" textAnchor="middle" fill="#8095a2" fontSize="8">N</text>
      {vector.direction != null && <g transform={`rotate(${vector.direction} 45 45)`}><path d="M45 66V24 M38 32L45 23L52 32" fill="none" stroke={vector.color} strokeWidth="2.5" strokeLinecap="round"/><circle cx="45" cy="45" r="3" fill={vector.color}/></g>}
    </svg><div><b>{vector.name}</b><strong>{vector.speed == null ? "Unavailable" : `${fmt(vector.speed, vector.name === "Current" ? 2 : 1)} ${vector.unit}`}</strong><small>{vector.direction == null ? "" : `${fmt(vector.direction, 0)}° toward`}</small></div>
  </div>)}</div>;
}
