/**
 * OILTRACE data-access layer.
 *
 * Components ask this module for an investigation and get one back. They never
 * learn whether it came from the backend, the bundled AI JSON, or the old demo
 * fixtures — except through `mode`, which they must surface honestly.
 *
 * Resolution order:
 *   1. LIVE_INFERENCE  POST /fleet/scan     both trained models, run now
 *   2. AI_RESULT       GET /ai-result       stored completed case from the handoff
 *   3. AI_RESULT       /ai-data/...json     the same output, bundled locally
 *
 * Nothing here computes or substitutes values. A field the AI did not produce
 * stays null and is rendered as "Not available" by the UI.
 */
export const API = "http://localhost:8000";

/** Backend-served paths (/simulation-images/..., /ai-images/...) need the API
 *  origin, because the page itself is served by Vite on another port. */
export const apiUrl = (path?: string | null) => (path ? `${API}${path}` : undefined);

export type InvestigationMode = "LIVE_INFERENCE" | "AI_RESULT";

/** Formats a value the AI did not supply. Never guess, never zero-fill. */
export const NOT_AVAILABLE = "Not available";
export const show = (v: any, suffix = "") =>
  v === null || v === undefined || v === "" ? NOT_AVAILABLE : `${v}${suffix}`;
export const showPct = (v: any, digits = 2) =>
  typeof v === "number" ? `${(v * 100).toFixed(digits)}%` : NOT_AVAILABLE;
export const showCoord = (v: any, digits = 5) =>
  typeof v === "number" ? v.toFixed(digits) : NOT_AVAILABLE;

async function tryFetch(url: string, init?: RequestInit, timeoutMs = 2000) {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const res = await fetch(url, {...init, signal: controller.signal});
    clearTimeout(timer);
    if (!res.ok) throw new Error(String(res.status));
    return await res.json();
  } catch {
    return null;
  }
}

/** Adapt the raw handoff JSON the same way the backend adapter does. */
function adaptRaw(ai: any) {
  if (!ai?.detection) return null;
  const i = ai.interpretation || {};
  return {
    system: ai.system, version: ai.version, mode: "AI_RESULT",
    detection: {
      prediction: ai.detection.prediction, oil_detected: ai.detection.class === 1,
      class: ai.detection.class, confidence: ai.detection.confidence,
      model: "OilSpillCNN — binary classifier", task: "classification",
      performs_segmentation: false, image_url: "/ai-data/class_1.jpg",
      estimated_area_km2: null, mask_url: null, oil_thickness: null, oil_volume: null,
      evidence_class: "MODEL OUTPUT",
    },
    spill: {...ai.spill, evidence_class: "SUPPLIED RESULT"},
    source: {
      latitude: ai.hindcast.latitude, longitude: ai.hindcast.longitude,
      hours_backward: ai.hindcast.hours_backward,
      label: "Probable Source — Model Estimate", confirmed: false, confidence: null,
      method: "Kinematic back-projection using an assumed drift vector",
      environmental_data_used: false, evidence_class: "MODEL ESTIMATE",
    },
    ais: {
      candidate_count: ai.ais.candidate_count,
      model: "Isolation Forest — behavioural anomaly detection",
      detailed_candidates: 1,
      candidates: [{
        rank: 1, mmsi: ai.ais.top_mmsi,
        minimum_distance_km: ai.ais.minimum_distance_km,
        trajectory_status: ai.ais.trajectory_status,
        trajectory_score: ai.ais.trajectory_score,
        behaviour_score: ai.ais.behaviour_score,
        final_suspect_score: ai.ais.final_suspect_score,
        latitude: null, longitude: null, track: null,
      }],
      note: `${ai.ais.candidate_count} candidates were found; the AI output details only the top-ranked vessel.`,
      evidence_class: "ANALYTICAL RANKING",
    },
    forecast: {
      type: i.forecast_type || "kinematic_projection",
      label: "Kinematic Movement Projection",
      requires_environmental_drift_data: i.requires_environmental_drift_data !== false,
      warning: "Environmental wind, currents, waves and oil properties are not currently incorporated.",
      points: ai.forecast || [], wind: null, current: null, wave: null,
      evidence_class: "PREDICTION",
    },
    cnn_validation: ai.cnn_validation, model_status: ai.model_status,
    model_artifacts: null,
    interpretation: {
      ...i,
      ranking_meaning: "This ranking indicates analytical association with the estimated source window. It does not establish legal responsibility.",
    },
    provenance: {source: "ai_result_local", detail: "Bundled AI output; backend unreachable.", live_inference: false},
  };
}

/**
 * Adapt POST /ai/investigate onto the shape the dashboard already renders.
 *
 * Field names line up with the stored-result adapter deliberately, so the UI does
 * not need to know which produced the data. CNN validation metrics are fetched
 * separately: they describe the model, not this run, so the live pipeline does
 * not (and should not) return them per request.
 */
async function adaptLive(live: any) {
  if (!live?.detection) return null;
  const clear = live.status !== "SPILL_CONFIRMED";
  const metrics = await tryFetch(`${API}/ai-result/metrics`);

  return {
    system: "OILTRACE", version: "live", mode: "LIVE_INFERENCE",
    status: live.status, message: live.message ?? null,
    detection: {
      prediction: live.detection.prediction,
      oil_detected: live.detection.class_id === 1,
      class: live.detection.class_id,
      confidence: live.detection.confidence,
      probabilities: live.detection.probabilities,
      model: live.detection.model,
      task: "classification",
      performs_segmentation: false,
      // The scene the CNN actually classified.
      image_url: apiUrl("/ai-images/class_1.jpg"),
      estimated_area_km2: null, mask_url: null,
      oil_thickness: null, oil_volume: null,
      inference_ms: live.detection.inference_ms,
      device: live.detection.device,
      evidence_class: "MODEL OUTPUT",
    },
    spill: {
      latitude: live.spill?.latitude, longitude: live.spill?.longitude,
      note: live.spill?.note, evidence_class: "SUPPLIED INPUT",
    },
    source: clear ? null : {...live.source, evidence_class: "MODEL ESTIMATE"},
    ais: clear ? null : {
      candidate_count: live.ais?.candidate_count ?? 0,
      model: live.ais?.model,
      detailed_candidates: live.ais?.candidates?.length ?? 0,
      candidates: live.ais?.candidates ?? [],
      search_radius_km: live.ais?.search_radius_km,
      records_in_window: live.ais?.records_in_window,
      records_within_radius: live.ais?.records_within_radius,
      weights: live.ais?.weights,
      note: `${live.ais?.records_in_window ?? 0} AIS records in the ±2 h window, ` +
            `${live.ais?.candidate_count ?? 0} vessels within ${live.ais?.search_radius_km ?? 50} km of the estimated source.`,
      evidence_class: "ANALYTICAL RANKING",
    },
    forecast: clear ? null : {...live.forecast, evidence_class: "PREDICTION"},
    cnn_validation: metrics ?? null,
    model_status: null,
    interpretation: live.interpretation ?? {},
    provenance: {
      source: "live_inference",
      detail: "Both trained models run now against the supplied scene.",
      live_inference: true,
      elapsed_ms: live.elapsed_ms,
    },
  };
}

/**
 * The completed AI investigation, or null if neither source is reachable.
 * Image URLs are absolutised here so the caller never has to know the origin.
 */
export async function getInvestigation() {
  const fromApi = await tryFetch(`${API}/ai-result`);
  if (fromApi?.detection) {
    return {...fromApi, detection: {...fromApi.detection, image_url: apiUrl(fromApi.detection.image_url)}};
  }
  const local = await tryFetch("/ai-data/oiltrace_ai_output_final.json");
  return adaptRaw(local);
}

/** Map viewport derived from whatever coordinates the result actually contains. */
export function viewportFrom(inv: any): {center: [number, number]; points: [number, number][]} | null {
  const pts: [number, number][] = [];
  if (typeof inv?.spill?.latitude === "number") pts.push([inv.spill.latitude, inv.spill.longitude]);
  if (typeof inv?.source?.latitude === "number") pts.push([inv.source.latitude, inv.source.longitude]);
  for (const p of inv?.forecast?.points || []) {
    if (typeof p.latitude === "number") pts.push([p.latitude, p.longitude]);
  }
  if (!pts.length) return null;
  const lat = pts.reduce((a, p) => a + p[0], 0) / pts.length;
  const lon = pts.reduce((a, p) => a + p[1], 0) / pts.length;
  return {center: [lat, lon], points: pts};
}

/**
 * Fleet monitoring scan — the primary mode.
 *
 * Runs the CNN over every monitored ship in one satellite pass. Returns the whole
 * fleet whether or not oil is found, so the dashboard can always list the vessels
 * being tracked. Null when the backend is unreachable.
 */
export async function runFleetScan(snapshotId?: string) {
  const body = JSON.stringify(snapshotId ? {snapshot_id: snapshotId} : {});
  const scan = await tryFetch(`${API}/fleet/scan`, {
    method: "POST", headers: {"Content-Type": "application/json"}, body,
  }, 60000);
  if (!scan?.fleet) return null;
  return {
    ...scan,
    mode: "LIVE_INFERENCE",
    fleet: scan.fleet.map((s: any) => ({...s, image_url: apiUrl(s.image_url)})),
    // detections repeat fleet entries, so they need the same absolute URLs
    detections: (scan.detections || []).map((d: any) => ({...d, image_url: apiUrl(d.image_url)})),
    spill: scan.spill ? {...scan.spill, image_url: apiUrl(scan.spill.image_url)} : null,
  };
}

/** Map viewport covering the fleet, the spill, the source and the forecast. */
export function fleetViewport(scan: any): {center: [number, number]; points: [number, number][]} | null {
  const pts: [number, number][] = [];
  for (const s of scan?.fleet || []) {
    if (typeof s.latitude === "number") pts.push([s.latitude, s.longitude]);
  }
  if (typeof scan?.source?.latitude === "number") pts.push([scan.source.latitude, scan.source.longitude]);
  for (const p of scan?.forecast?.points || []) {
    if (typeof p.latitude === "number") pts.push([p.latitude, p.longitude]);
  }
  if (!pts.length) return null;
  const lat = pts.reduce((a, p) => a + p[0], 0) / pts.length;
  const lon = pts.reduce((a, p) => a + p[1], 0) / pts.length;
  return {center: [lat, lon], points: pts};
}
