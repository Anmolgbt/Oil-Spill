import type {Ship, SpillEntry} from "../types";

/**
 * REPLAY — interpolating the incident over one timeline.
 *
 * Everything the replay needs is already in a single /fleet/scan response: each
 * vessel carries its full AIS history plus a two-point kinematic projection,
 * and the spill carries a hindcast source, the observed detection and the
 * forecast points. So nothing is refetched while scrubbing — there is no
 * network call between frames to stutter on.
 *
 * The one thing these helpers must never do is blur observed into projected.
 * Each returns which it is, and the caller is expected to draw them
 * differently.
 */
export const lerp = (a: number, b: number, f: number) => a + (b - a) * f;
export const HOUR_MS = 3600_000;

/** Where a vessel was (or is projected to be) at `tMs`. */
export function vesselAt(ship: Ship, tMs: number, horizonHours: number) {
  const track = ship?.track || [];
  if (!track.length) return null;
  const times = track.map((p: any) => Date.parse(p.time));
  const first = times[0];
  const last = times[times.length - 1];

  // Before its first fix, the vessel's position is simply unknown; holding it
  // at the earliest fix is the only claim that adds nothing.
  if (tMs <= first) return {lat: track[0].lat, lon: track[0].lon, observed: true, held: true};

  if (tMs <= last) {
    let i = 1;
    while (i < times.length - 1 && times[i] < tMs) i++;
    const span = Math.max(times[i] - times[i - 1], 1);
    const f = Math.max(0, Math.min(1, (tMs - times[i - 1]) / span));
    return {
      lat: lerp(track[i - 1].lat, track[i].lat, f),
      lon: lerp(track[i - 1].lon, track[i].lon, f),
      observed: true, held: false,
    };
  }

  // Past the last AIS fix this is a kinematic projection, not a report.
  const pt = ship.projected_track || [];
  const tail = track[track.length - 1];
  if (pt.length < 2) return {lat: tail.lat, lon: tail.lon, observed: false, held: true};
  const f = Math.max(0, Math.min(1, (tMs - last) / (horizonHours * HOUR_MS)));
  return {
    lat: lerp(pt[0].latitude, pt[1].latitude, f),
    lon: lerp(pt[0].longitude, pt[1].longitude, f),
    observed: false, held: f >= 1,
  };
}

/**
 * Where the slick is at `tMs`, and on what basis.
 *
 * Three bases, never merged: `estimated` between the hindcast release and the
 * pass (backward-derived, nobody saw it), `observed` at the detection itself,
 * and `projected` after it.
 */
export type SlickBasis = "estimated" | "observed" | "projected";
export interface SlickAt { lat: number; lon: number; basis: SlickBasis; }

export function slickAt(entry: SpillEntry, tMs: number, observedAtMs: number,
                        dwellMs = 0): SlickAt | null {
  const sp = entry?.spill, src = entry?.source;
  if (!sp || !entry?.age?.release_at) return null;
  const releaseMs = Date.parse(entry.age.release_at);
  if (tMs < releaseMs) return null;

  // The detection is one instant, so at any real playback rate the timeline
  // steps straight over it — and the single moment the oil was actually
  // measured would never appear. A short dwell around the pass fixes that
  // without overstating anything: a satellite pass is not instantaneous.
  if (Math.abs(tMs - observedAtMs) <= dwellMs) {
    return {lat: sp.latitude, lon: sp.longitude, basis: "observed"};
  }

  if (tMs < observedAtMs && src) {
    const f = Math.max(0, Math.min(1, (tMs - releaseMs) / Math.max(observedAtMs - releaseMs, 1)));
    return {lat: lerp(src.latitude, sp.latitude, f), lon: lerp(src.longitude, sp.longitude, f),
            basis: "estimated"};
  }

  const hours = (tMs - observedAtMs) / HOUR_MS;
  const pts = entry.forecast?.points || [];
  if (hours <= 0 || !pts.length) return {lat: sp.latitude, lon: sp.longitude, basis: "observed"};

  let prev: {hours_ahead: number; latitude: number; longitude: number} = {hours_ahead: 0, latitude: sp.latitude, longitude: sp.longitude};
  for (const p of pts) {
    if (hours <= p.hours_ahead) {
      const f = (hours - prev.hours_ahead) / Math.max(p.hours_ahead - prev.hours_ahead, 1e-9);
      return {lat: lerp(prev.latitude, p.latitude, f), lon: lerp(prev.longitude, p.longitude, f),
              basis: "projected"};
    }
    prev = p;
  }
  return {lat: prev.latitude, lon: prev.longitude, basis: "projected"};
}

/** How far past the detection the replay runs. See the note in `timeline`. */
export const REPLAY_MAX_AHEAD_H = 12;

export const clock = (ms: number) =>
  new Date(ms).toISOString().replace("T", " ").slice(5, 16) + " UTC";
