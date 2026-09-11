/**
 * Map overlay colours, in one place.
 *
 * Leaflet paints SVG strokes through `pathOptions`, not CSS classes, so these
 * cannot live in styles.css with the rest of the palette — but they were
 * scattered as bare hex literals across ~30 call sites, where the same red
 * meant "oil detected" in one line and "possible affected area" three lines
 * later with nothing tying them together. Naming them by ROLE rather than by
 * colour is the point: it is what makes an accidental reuse visible.
 *
 * These mirror the CSS custom properties in styles.css. If one changes, change
 * both — the map and the panels must not drift apart.
 */
export const MAP_COLOURS = {
  /** --danger: the CNN's own call, and the drift envelope drawn from it. */
  spill: "#c0261b",
  spillFill: "#e2554a",

  /** --warn: anything back-derived. The hindcast track and its source marker. */
  hindcast: "#b45309",
  hindcastFill: "#f59e0b",

  /** --accent: anything projected forward. Forecast, and a vessel's own track. */
  forecast: "#0b5cab",
  vessel: "#0b5cab",
  vesselFill: "#5b9bd8",

  /** A vessel the forward-risk check flagged. */
  atRisk: "#b8860b",

  /** --ok: the simulated detour. Green because avoiding the zone is the good
   *  outcome, not because the route is verified — it is a demo. */
  detour: "#1a8a4a",

  /** The counterfactual, held apart from every other overlay on purpose: it is
   *  a hypothesis being tested, not a finding. */
  counterfactual: "#6d28d9",
  counterfactualFill: "#ede9fe",

  /** The environmental field. Teal because it is a CONDITION rather than a
   *  finding — it belongs to none of the roles above, and reusing any of them
   *  would make an assumed constant look like a result. */
  environment: "#0f766e",
  environmentFaint: "#5eead4",

  /** --ink-mute: observed history that is context rather than claim. */
  track: "#8a95a3",
  candidateTrack: "#6b7684",
} as const;
