/**
 * Shapes of the /fleet/scan payload, as the backend actually sends them.
 *
 * Deliberately partial and permissive. These describe the fields the dashboard
 * reads, nothing more — no field is declared here that the API does not send,
 * and optionality mirrors the backend's own honesty: a value the models cannot
 * produce arrives as null and must stay renderable as "Not available".
 */

export interface TrackFix {
  /** AIS fixes use the short names. Forecast and projected_track use the long
   *  ones — mixing them up silently yields empty arrays, which has bitten
   *  this codebase before. */
  time: string;
  lat: number;
  lon: number;
  speed_kt?: number;
  course_deg?: number;
}

export interface LatLon {
  latitude: number;
  longitude: number;
}

export interface Ship {
  id: string;
  mmsi: number;
  name: string;
  vessel_type?: string;
  image_url?: string;
  length_m?: number;
  width_m?: number;
  latitude: number;
  longitude: number;
  speed_kt?: number;
  course_deg?: number;
  position_time?: string;
  track?: TrackFix[];
  projected_track?: LatLon[];
  status?: string;
  oil_detected?: boolean;
  prediction?: string;
  confidence?: number;
}

export interface Spill {
  ship_id: string;
  ship_name: string;
  mmsi?: number;
  latitude: number;
  longitude: number;
  confidence?: number;
  image_url?: string;
}

export interface Source extends LatLon {
  hours_backward?: number;
  drift_speed_kmh?: number;
  drift_direction_deg?: number;
  label?: string;
  confirmed?: boolean;
  method?: string;
  environmental_data_used?: boolean;
}

/**
 * Spread of the hindcast point across the drift-assumption band the
 * counterfactual sensitivity sweep already uses. NOT a probability surface —
 * every point is an equally-plausible re-run of the same hindcast, not a
 * weighted likelihood.
 */
export interface SourceHeatmap {
  points: LatLon[];
  grid?: string;
  speed_range_kmh?: [number, number];
  bearing_range_deg?: [number, number];
  hours?: number;
  label?: string;
  note?: string;
  evidence_class?: string;
}

/**
 * Forward-looking counterpart to SourceHeatmap — the forecast point
 * re-evaluated across the same drift-assumption band, per horizon. Also not
 * a probability surface.
 */
export interface ForecastHeatmapHorizon {
  hours_ahead: number;
  points: LatLon[];
}
export interface ForecastHeatmap {
  by_horizon: ForecastHeatmapHorizon[];
  grid?: string;
  speed_range_kmh?: [number, number];
  bearing_range_deg?: [number, number];
  label?: string;
  note?: string;
  evidence_class?: string;
}

export interface Age {
  estimated_hours: number;
  release_at: string;
}

export interface AffectedArea {
  radius_km?: number;
  area_km2?: number;
  /** Structurally null: the detector classifies and produces no mask. */
  measured_area_km2?: null;
}

export interface ForecastPoint extends LatLon {
  hours_ahead: number;
}

export interface Forecast {
  points?: ForecastPoint[];
  type?: string;
  label?: string;
  requires_environmental_drift_data?: boolean;
}

export interface Weights {
  proximity: number;
  trajectory: number;
  behaviour: number;
}

export interface Candidate {
  rank: number;
  ship_id: string;
  mmsi: number;
  name: string;
  vessel_type?: string;
  in_fleet?: boolean;
  minimum_distance_km?: number;
  closest_time?: string;
  proximity_score?: number;
  trajectory_status?: string;
  trajectory_score?: number;
  /** Null when the Isolation Forest returned no verdict. Must never render as
   *  a scored zero — see behaviour_status for why it is missing. */
  behaviour_score?: number | null;
  behaviour_available?: boolean;
  /** ok | track_too_short | model_unavailable | model_declined | inference_error */
  behaviour_status?: string;
  behaviour_reason?: string | null;
  /** The weights actually used for this candidate. When a term is unavailable
   *  the remaining ones are renormalised, so these differ from the headline
   *  weights and the displayed arithmetic must use these. */
  weights_applied?: Weights;
  scored_on_partial_evidence?: boolean;
  anomalous_points?: number | null;
  final_suspect_score: number;
  latitude?: number;
  longitude?: number;
}

/** What the irrelevant-traffic filter rejected, counted in vessels. */
export interface Funnel {
  monitored: number;
  with_fixes_in_window: number;
  within_radius: number;
  rejected_no_fixes: number;
  rejected_too_far: number;
}

export interface Ais {
  candidate_count?: number;
  records_in_window?: number;
  records_within_radius?: number;
  search_radius_km?: number;
  /** Why the radius is what it is — derived from the drift envelope, not picked. */
  search_radius_basis?: string;
  funnel?: Funnel;
  weights?: Weights;
  model?: string;
}

/** The vessel population the monitored fleet was drawn from. */
export interface Traffic {
  corpus_vessels?: number | null;
  monitored?: number;
  /** "constructed" when vessel co-presence is a scheduling artefact of the demo. */
  co_presence?: string | null;
  co_presence_reason?: string | null;
  note?: string;
}

export interface Detour {
  original_heading_deg: number;
  suggested_heading_deg: number;
  heading_change_deg: number;
  safety_buffer_km: number;
  already_inside_zone: boolean;
  detour_distance_km: number;
  direct_distance_km: number;
  clears_spill_zone: boolean;
  detour_waypoints: (LatLon & {label?: string})[];
  reason?: string;
  note?: string;
}

export interface RiskEntry {
  ship_id: string;
  mmsi: number;
  name: string;
  risk?: string;
  estimated_entry_minutes?: number;
  spill_ship_id?: string;
  spill_ship_name?: string;
  response_priority?: string;
  projected_route: LatLon[];
  forecast_horizon_hours?: number;
  detour?: Detour | null;
}

export interface RiskOverview {
  at_risk: RiskEntry[];
  at_risk_count: number;
  vessels_checked: number;
  safe_count: number;
  forecast_horizon_hours?: number;
}

export interface Damage {
  priority_score?: number;
  radius_km?: number;
  area_km2?: number;
}

export interface ResponseAdvice {
  urgency: string;
  action: string;
}

export interface ResponsePriority {
  ship_id: string;
  ship_name: string;
  mmsi: number;
  response_priority: string;
  priority_score: number;
  envelope_radius_km?: number;
  envelope_area_km2?: number;
}

/** One detection and everything derived from it. A pass may hold several. */
export interface SpillEntry {
  spill: Spill;
  source?: Source;
  source_heatmap?: SourceHeatmap;
  age?: Age;
  affected_area?: AffectedArea;
  forecast?: Forecast;
  forecast_heatmap?: ForecastHeatmap;
  /** Environment-aware estimates, computed alongside the legacy ones above. */
  source_environmental?: EnvironmentalDrift;
  forecast_environmental?: EnvironmentalDrift;
  drift_divergence?: DriftDivergence;
  evidence?: Evidence;
  ais?: Ais;
  candidates: Candidate[];
  /** Vessels projected to enter THIS detection's envelope, not the fleet-wide
   *  merge in Scan.risk_overview. */
  risk?: RiskOverview;
  damage?: Damage;
  response?: ResponseAdvice;
  response_priority?: string;
}

export interface EnvVector {
  speed_ms?: number;
  direction_deg?: number;
  /** True only when the value came from a committed historical dataset. */
  measured?: boolean;
  assumed?: boolean;
}

export interface Environment {
  wind?: EnvVector | null;
  current?: EnvVector | null;
  /** Always null: no wave feed is connected. */
  wave?: null;
  drift?: {speed_kmh?: number; direction_deg?: number} | null;
  /** "historical" only when every value came from a dataset; else "fallback". */
  environment_mode?: "historical" | "fallback";
  /** Why the mode is not historical. Null when it is. */
  environment_reason?: string | null;
  measured?: boolean;
  source?: string;
  resolution?: Record<string, unknown> | null;
  coverage?: Record<string, unknown> | null;
  sampled_at?: string | null;
  sampled_at_position?: {latitude: number; longitude: number};
}

/** One point on an integrated drift path. */
export interface DriftPoint {
  hours: number;
  latitude: number;
  longitude: number;
}

/**
 * The environment-aware estimate of the same question the legacy fixed-vector
 * hindcast/forecast answer. Computed alongside them; it drives nothing yet.
 */
export interface EnvironmentalDrift {
  latitude?: number;
  longitude?: number;
  path?: DriftPoint[];
  points?: {hours_ahead: number; latitude: number; longitude: number}[];
  steps?: number;
  step_minutes?: number;
  environment_mode?: "historical" | "fallback";
  environment_reason?: string | null;
  environment_sources?: string[];
  environmental_data_used?: boolean;
  label?: string;
  method?: string;
  note?: string;
}

/**
 * How far apart the legacy and environment-aware estimates land. They differ
 * even with no dataset loaded, because the legacy vectors were never derived
 * from the stated wind and current. A disagreement between assumptions, not a
 * measurement of error.
 */
export interface RankingChangeRow {
  mmsi: number;
  name: string;
  legacy_rank: number;
  legacy_score: number;
  environmental_rank: number | null;
  environmental_score: number | null;
  rank_delta: number | null;
  /** The environment-aware source puts this vessel outside the search radius. */
  dropped: boolean;
}

export type RankingChange =
  | {available: false; reason: string}
  | {
      available: true;
      /** Whether the two drift assumptions rank a different vessel first. */
      top_changes: boolean;
      legacy_top: string | null;
      environmental_top: string | null;
      legacy_count: number;
      environmental_count: number;
      rows: RankingChangeRow[];
      admitted_only_by_environmental: {mmsi: number; name: string;
                                       environmental_rank: number}[];
      in_use: "legacy";
      meaning: string;
    };

export interface DriftDivergence {
  source_separation_km: number;
  forecast_separation_km: Record<string, number>;
  legacy_vectors: {
    hindcast: {speed_kmh: number; direction_deg: number};
    forecast: {speed_kmh: number; direction_deg: number};
  };
  environment_vector: {speed_kmh: number; direction_deg: number};
  environment_mode: "historical" | "fallback";
  closure: {residual_km: number; hours: number; environment_mode: string;
            step_minutes: number; meaning: string};
  ranking_change?: RankingChange;
  cause: string;
  in_use: string;
}

export type Grade = "HIGH" | "MEDIUM" | "LOW" | "UNAVAILABLE";

/** One evidence stream. The grade says how much it can tell us, not how guilty
 *  the vessel is — which is why UNAVAILABLE is not the bottom of the scale. */
export interface EvidenceStream {
  grade: Grade;
  reason: string;
  /** The threshold rule that produced the grade, so it can be argued with. */
  rule: string;
  [key: string]: unknown;
}

export type NarrativeTone = "supports" | "weakens" | "missing" | "neutral";

export interface NarrativeBeat {
  text: string;
  tone: NarrativeTone;
}

/** The plain-language reading of one candidate, composed by the backend. */
export interface CandidateNarrativeData {
  beats: NarrativeBeat[];
  /** Streams with no evidence either way — stated, never silently dropped. */
  missing_streams: string[];
  counts: Record<NarrativeTone, number>;
  disclaimer: string;
}

export interface CandidateEvidence {
  mmsi: number;
  name: string;
  streams: {
    ais_coverage: EvidenceStream;
    trajectory: EvidenceStream;
    behaviour: EvidenceStream;
    environment: EvidenceStream;
    counterfactual: EvidenceStream;
  };
  unavailable: string[];
  counts: Record<Grade, number>;
  note: string;
  narrative?: CandidateNarrativeData | null;
}

export type Outcome =
  | "CANDIDATE_SUPPORTED"
  | "LEADING_CANDIDATE_UNSTABLE"
  | "NO_STRONG_CANDIDATE";

export interface DetectionAssessment {
  outcome: Outcome;
  leader: {mmsi: number; name: string; score: number;
           counterfactual_consistent: boolean} | null;
  reasons: string[];
  consistent_count: number;
  candidate_count: number;
  rules: Record<string, string>;
  /** What the outcome claims, and what it does not. */
  means: string;
}

export interface Evidence {
  candidates: CandidateEvidence[];
  assessment: DetectionAssessment;
}

export interface Scan {
  status: "SPILL_DETECTED" | "CLEAR" | string;
  message?: string;
  mode?: string;
  snapshot_id?: string | null;
  observed_at?: string | null;
  available_snapshots?: string[];
  pass_interval_hours?: number;
  region?: string;
  scanned?: number;
  fleet: Ship[];
  detections?: Ship[];
  spills?: SpillEntry[];
  spill?: Spill | null;
  source?: Source;
  source_heatmap?: SourceHeatmap;
  age?: Age;
  affected_area?: AffectedArea | null;
  forecast?: Forecast;
  forecast_heatmap?: ForecastHeatmap;
  source_environmental?: EnvironmentalDrift;
  forecast_environmental?: EnvironmentalDrift;
  drift_divergence?: DriftDivergence;
  evidence?: Evidence;
  ais?: Ais;
  candidates?: Candidate[];
  risk_overview?: RiskOverview;
  response_priorities?: ResponsePriority[];
  environment?: Environment;
  traffic?: Traffic;
  interpretation?: {
    vessel_causation_proven?: boolean;
    forecast_type?: string;
    requires_environmental_drift_data?: boolean;
    ranking_meaning?: string;
  };
  provenance?: Provenance;
  /** How far behind this pass the newest AIS fix is. Present when an uploaded
   *  pass runs past the end of the corpus. */
  ais_currency?: {stale?: boolean; newest_fix_lag_hours?: number; note?: string};
}

/** What produced the run, and what a reader needs to reproduce or dispute it. */
export interface Provenance {
  live_inference?: boolean;
  fleet_data?: string;
  oil_detection?: {source?: string; model_version?: string | null};
  anomaly_detection?: {source?: string; model_version?: string | null};
  /** Which vessels carry an oil-positive tile is assigned by this seed. */
  simulation_seed?: number;
  simulation_note?: string;
  ais_dataset?: {source?: string; vessels_in_corpus?: number | null;
                 monitored?: number; co_presence?: string | null};
  sar_input?: {source?: string; note?: string};
  software_mode?: string;
  [k: string]: unknown;
}

/**
 * POST /fleet/counterfactual
 *
 * A discriminated union, because `available` genuinely decides whether the
 * result fields exist: when the vessel had no AIS fix at the estimated release
 * time there is no simulated position to report, only a reason. Modelling that
 * as optional fields would let a caller render `undefined` as a distance.
 */
/** How far one assumption can move before the counterfactual's verdict flips. */
export interface RobustnessFlip {
  /** Smallest perturbation that changes the verdict, in the axis's own unit. */
  delta: number;
  direction: string;
  /** Half-width of the swept band, so the delta can be read as a proportion. */
  bound: number;
}

export type Robustness =
  | {available: false; reason: string}
  | {
      available: true;
      baseline_verdict: "consistent" | "not consistent";
      /** Share of the swept band agreeing with the baseline. NOT a probability. */
      agreement_fraction: number;
      classification: "robust" | "moderately sensitive" | "highly sensitive";
      flips_at: {
        drift_speed_kmh: RobustnessFlip | null;
        drift_bearing_deg: RobustnessFlip | null;
        assumed_age_hours: RobustnessFlip | null;
      };
      smallest_flip: (RobustnessFlip & {axis: string}) | null;
      sweep: {
        combinations: number;
        over: string;
        drift_speed_kmh: [number, number];
        drift_bearing_deg: [number, number];
        basis: string;
        not_swept: string;
      };
      rule: string;
      interpretation: {is_accuracy: false; is_probability: false; meaning: string};
    };

/** The same counterfactual, run through the environment field. */
export interface EnvironmentalCounterfactual {
  available: boolean;
  miss_distance_km: number;
  /** The envelope THIS drift implies — not the map's affected-area circle. */
  consistency_radius_km: number;
  within_envelope: boolean;
  margin_km: number;
  simulated_now: LatLon;
  environment_mode: "historical" | "fallback";
  environment_reason: string | null;
  agrees_with_legacy: boolean | null;
  method?: string;
  radius_basis?: string;
  note?: string;
}

export type ModeComparison =
  | {available: false; reason: string}
  | {
      available: true;
      verdicts_agree: boolean | null;
      legacy: {miss_km: number; radius_km: number; margin_km: number};
      environmental: {miss_km: number; radius_km: number; margin_km: number};
      /** How much closer to (or further from) the threshold the verdict sits. */
      margin_shift_km: number;
      environment_mode: "historical" | "fallback";
      self_consistency: string;
      meaning: string;
    };

export type Counterfactual =
  | {available: false; reason: string}
  | {
      available: true;
      ship_id: string;
      mmsi: number;
      name: string;
      assumed_release: LatLon & {ais_fix_time: string; fix_age_hours: number; note?: string};
      simulated_now: LatLon & {note?: string};
      observed_now: LatLon & {note?: string};
      miss_distance_km: number;
      envelope_radius_km: number | null;
      /** The threshold actually applied, derived from this test's own drift. */
      consistency_radius_km?: number;
      /** The map circle, for context. Sized by a different vector. */
      affected_area_radius_km?: number | null;
      radius_basis?: string;
      margin_km?: number;
      within_envelope: boolean | null;
      environmental?: EnvironmentalCounterfactual;
      mode_comparison?: ModeComparison;
      distance_from_estimated_source_km: number | null;
      drift?: Record<string, unknown>;
      method?: string;
      interpretation?: {is_proof: boolean; meaning: string};
      robustness?: Robustness;
      limits?: string;
    };
