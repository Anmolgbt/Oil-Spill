import {Info} from "lucide-react";
import {fmt} from "../ui";
import {NOT_AVAILABLE} from "../lib/oiltrace";
import type {Environment} from "../types";

export interface EnvironmentStripProps {
  environment?: Environment | null;
}

/**
 * The conditions driving the impact envelope, with their provenance.
 *
 * The closing sentence used to be hardcoded ("assumed values, not
 * measurements"). It was true, but only by coincidence — it would have gone on
 * saying so after a real dataset was added. It now comes from the backend's
 * `environment_mode`, which is the single place that knows whether these
 * numbers are a dataset's or `core/config.py`'s.
 */
export function EnvironmentStrip({environment: env}: EnvironmentStripProps) {
  const historical = env?.environment_mode === "historical";

  return (
    <div className="env">
      <Info size={14} />
      <span>WIND <b>{env?.wind
        ? `${fmt(env.wind.speed_ms)} m/s · ${fmt(env.wind.direction_deg, 0)}°`
        : NOT_AVAILABLE}</b></span>
      <span>CURRENT <b>{env?.current
        ? `${fmt(env.current.speed_ms, 2)} m/s · ${fmt(env.current.direction_deg, 0)}°`
        : NOT_AVAILABLE}</b></span>
      {/* Genuinely absent: nothing in the pipeline consumes wave data. */}
      <span>DRIFT <b>{env?.drift
        ? `${fmt(env.drift.speed_kmh, 2)} km/h · ${fmt(env.drift.direction_deg, 0)}°`
        : NOT_AVAILABLE}</b></span>
      <span style={{marginLeft: "auto"}} title={env?.environment_reason ?? undefined}>
        {historical ? "Historical data" : "Assumed conditions"}
      </span>
    </div>
  );
}
