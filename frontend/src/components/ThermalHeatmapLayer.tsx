import {useEffect} from "react";
import {useMap} from "react-leaflet";
import L from "leaflet";

// leaflet.heat (github.com/Leaflet/Leaflet.heat) predates ES modules — it
// expects a global `L` to already exist when its script body runs, instead
// of importing one itself. Vite/Rollup evaluate a module's own top-level
// statements in source order, so setting window.L here, before the
// side-effect import below, is the standard fix for using it inside a
// bundled app rather than a plain <script> tag.
if (typeof window !== "undefined") {
  (window as unknown as {L?: typeof L}).L = (window as unknown as {L?: typeof L}).L || L;
}
import "leaflet.heat";

import type {ForecastHeatmap, SourceHeatmap} from "../types";

export interface ThermalHeatmapLayerProps {
  sourceHeatmap?: SourceHeatmap | null;
  forecastHeatmap?: ForecastHeatmap | null;
  /** Replay's current band, when replay is running. Gates which half of the
   *  spread shows, so the heat layer moves with the scrubber instead of
   *  showing the whole story at once — spread around the source while
   *  replay is in the hindcast portion, spread around the forecast once
   *  replay moves past the detection. null (replay not running) shows both
   *  at once, so the toggle alone is useful without needing replay. */
  band?: "before" | "estimated" | "observed" | "projected" | null;
}

// Green (sparse) through red (where the real 49-point sweep clusters most
// tightly) — see the docstrings on source_heatmap()/forecast_heatmap() in
// services/fleet_pipeline.py. Colour comes from point DENSITY, computed by
// the canvas layer below from the genuine spread of re-run hindcast/forecast
// points; nothing here is a hand-assigned per-point weight.
const GRADIENT: Record<number, string> = {
  0.20: "#22c55e",
  0.40: "#a3e635",
  0.60: "#facc15",
  0.80: "#fb923c",
  1.00: "#ef4444",
};

type HeatPoint = [number, number, number]; // lat, lng, weight

export function ThermalHeatmapLayer({sourceHeatmap, forecastHeatmap, band = null}: ThermalHeatmapLayerProps) {
  const map = useMap();

  useEffect(() => {
    const showSource = band === null || band === "estimated";
    const showForecast = band === null || band === "projected";

    let points: HeatPoint[] = [];
    if (showSource && sourceHeatmap?.points?.length) {
      points = points.concat(sourceHeatmap.points.map((p): HeatPoint => [p.latitude, p.longitude, 1]));
    }
    if (showForecast && forecastHeatmap?.by_horizon?.length) {
      forecastHeatmap.by_horizon.forEach((h) => {
        points = points.concat(h.points.map((p): HeatPoint => [p.latitude, p.longitude, 1]));
      });
    }

    if (!points.length) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const heat = (L as any).heatLayer(points, {
      radius: 34,
      blur: 26,
      maxZoom: 15,
      minOpacity: 0.30,
      gradient: GRADIENT,
    }).addTo(map);

    return () => {
      map.removeLayer(heat);
    };
  }, [map, sourceHeatmap, forecastHeatmap, band]);

  return null;
}
