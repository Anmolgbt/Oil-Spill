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
/** Backend origin. Override with VITE_API_URL at build or dev time (see
 *  frontend/.env.example); the localhost default keeps `npm run dev` working
 *  with no configuration. */
export const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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

/**
 * COUNTERFACTUAL — "what if this vessel caused the spill?"
 *
 * Sends the detection's own figures back to the API, which runs the hindcast's
 * drift vector forward from the vessel's real AIS position at the estimated
 * release time. Returns a distance between simulated and observed, not a
 * verdict. Null if the backend is unreachable.
 */
export async function runCounterfactual(args: {
  mmsi: number;
  release_at: string;
  spill_latitude: number;
  spill_longitude: number;
  age_hours: number;
  /** Context only — the backend derives the threshold from its own drift. */
  affected_area_radius_km?: number | null;
  /** Override for that derived threshold. Tests use it; the app does not. */
  envelope_radius_km?: number | null;
  source_latitude?: number | null;
  source_longitude?: number | null;
}) {
  return tryFetch(`${API}/fleet/counterfactual`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(args),
  }, 15000);
}

/** Which id the next uploaded pass would take. */
export async function peekNextPass() {
  return tryFetch(`${API}/fleet/passes/next`);
}

/**
 * Create the next satellite pass from dropped images.
 *
 * Returns the backend's summary — including which image was paired with which
 * vessel, and that no ground truth exists for an uploaded pass — or an object
 * carrying `error` so the caller can say what went wrong rather than failing
 * silently.
 */
export async function uploadPass(files: File[]) {
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  try {
    const res = await fetch(`${API}/fleet/passes`, {method: "POST", body: form});
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      return {error: body?.detail ?? `Upload failed (${res.status}).`};
    }
    return body;
  } catch {
    return {error: "Could not reach the backend."};
  }
}

/** Remove an uploaded pass. t1-t3 ship with the repo and are protected. */
export async function deletePass(snapshotId: string) {
  try {
    const res = await fetch(`${API}/fleet/passes/${snapshotId}`, {method: "DELETE"});
    return res.ok ? await res.json() : {error: `Could not delete ${snapshotId}.`};
  } catch {
    return {error: "Could not reach the backend."};
  }
}

/** Configured pass times, without running inference again. */
export async function getFleetMetadata(): Promise<{snapshot_times?: Record<string, string>} | null> {
  return tryFetch(`${API}/fleet`);
}
export const imageSource = (path?: string | null) => !path ? undefined : /^https?:\/\//.test(path) || path.startsWith("/ai-data/") ? path : `${API}${path}`;
