import {useEffect} from "react";
import {CircleMarker, MapContainer, Polygon, Polyline, TileLayer, Tooltip, useMap} from "react-leaflet";
import L from "leaflet";
import {Flame, Info, Wind} from "lucide-react";
import {show, showCoord, showPct} from "../lib/oiltrace";
import {fmt} from "../ui";
import {MAP_COLOURS as C} from "../mapColours";
import {EnvironmentLayer} from "./EnvironmentLayer";
import {ThermalHeatmapLayer} from "./ThermalHeatmapLayer";
import type {Candidate, Counterfactual, Environment, ForecastHeatmap, LatLon, RiskEntry, Ship,
              Source, SourceHeatmap, Spill, AffectedArea, Forecast} from "../types";

const FALLBACK_CENTER: [number, number] = [28.55, -94.85];

export interface ReplayVessel { sh: Ship; at: {lat: number; lon: number; observed: boolean; held: boolean} | null; }
export interface ReplayFrame {
  t: number;
  slick: {lat: number; lon: number; basis: "estimated" | "observed" | "projected"} | null;
  vessels: ReplayVessel[];
  band: "before" | "estimated" | "observed" | "projected";
}

export interface MapViewProps {
  view: {center: [number, number]; points: [number, number][]} | null;
  envelope: [number, number][] | null;
  detected: boolean;
  shownSpill?: Spill | null;
  shownArea?: AffectedArea | null;
  shownSource?: Source | null;
  source?: Source | null;
  shownForecast?: Forecast | null;
  selectedRisk?: RiskEntry | null;
  selected: Ship | null;
  setSelected: (s: Ship) => void;
  fleet: Ship[];
  riskByShipId: Record<string, RiskEntry>;
  legendOpen: boolean;
  setLegendOpen: (fn: (v: boolean) => boolean) => void;
  /** The drift field overlay. Context, not a finding — off unless asked for. */
  environment?: Environment | null;
  showEnvironment?: boolean;
  setShowEnvironment?: (fn: (v: boolean) => boolean) => void;
  /** Spread of the hindcast point across the drift-assumption band. Sensitivity
   *  context around the source marker, not a finding — off unless asked for. */
  sourceHeatmap?: SourceHeatmap | null;
  forecastHeatmap?: ForecastHeatmap | null;
  showSourceHeatmap?: boolean;
  setShowSourceHeatmap?: (fn: (v: boolean) => boolean) => void;
  mapStyle?: React.CSSProperties;
  /** Stage gates — see the note on the component. */
  showEnvelope?: boolean;
  showHindcast?: boolean;
  showForecast?: boolean;
  showRisk?: boolean;
  showDetour?: boolean;
  candidateTracks?: (Candidate & {points: [number, number][]})[];
  whatIfShown?: Counterfactual | null;
  replayFrame?: ReplayFrame | null;
}

function MapFit({points}: {points: [number, number][] | null}) {
  const map = useMap();
  useEffect(() => {
    // Size must be settled before fitting, or Leaflet fits to a stale container
    // and zooms far past the data.
    if (!points || points.length < 2) return;
    const bounds = L.latLngBounds(points.map((p) => L.latLng(p[0], p[1])));
    const fit = () => {
      map.invalidateSize({animate: false});
      map.fitBounds(bounds, {padding: [40, 40], maxZoom: 11, animate: false});
    };
    // Fit twice: once as soon as the container exists, once after layout settles.
    fit();
    const t = window.setTimeout(fit, 350);
    window.addEventListener("resize", fit);
    return () => { window.clearTimeout(t); window.removeEventListener("resize", fit); };
  }, [points && points.length, points && points[0][0]]);
  return null;
}

/**
 * The Leaflet map itself, factored out so the same map can render inside the
 * normal dashboard layout AND full-size in its own browser tab (opened via
 * "Open map in new tab", for a screen where the docked map panel is too
 * small to comfortably pan/zoom).
 */
export function MapView({view, envelope, detected, shownSpill, shownArea, shownSource, source,
                   shownForecast, selectedRisk, selected, setSelected, fleet, riskByShipId,
                   legendOpen, setLegendOpen, mapStyle,
                   environment = null, showEnvironment = false, setShowEnvironment,
                   sourceHeatmap = null, showSourceHeatmap = false, setShowSourceHeatmap,
                   forecastHeatmap = null,
                   // Stage gates. The overlays appear as the investigation reaches
                   // them, so the map never shows an estimated source before the
                   // hindcast that produced it has been run.
                   showEnvelope = true, showHindcast = true, showForecast = true,
                   showRisk = true, candidateTracks = [], showDetour = true,
                   whatIfShown = null, replayFrame = null}: MapViewProps) {
  return (
    <MapContainer center={view?.center ?? FALLBACK_CENTER} zoom={7}
                  className={"map" + (showSourceHeatmap ? " thermal-dark" : "")} style={mapStyle} scrollWheelZoom>
      <MapFit points={view?.points ?? null} />
      <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

      {/* The conditions the envelope is sized from. Drawn FIRST so every
          finding renders above it — the field is background, not a result. */}
      {showEnvironment && (
        <EnvironmentLayer environment={environment} points={view?.points ?? null} />
      )}

      {/* possible affected area — drift envelope, never a measured slick */}
      {showEnvelope && envelope && (
        <Polygon positions={envelope} pathOptions={{color: C.spill, fillColor: C.spill, fillOpacity: .05, weight: 1.5, dashArray: "5 6"}}>
          <Tooltip>{shownSpill?.ship_name} · possible affected area, {fmt(shownArea?.radius_km)} km radius<br />Drift envelope, not a measured slick</Tooltip>
        </Polygon>
      )}

      {/* Thermal spread — where the source estimate and the forecast land
          across the drift-assumption band. Drawn first so the point marker
          and hindcast line render on top of it. Which half shows follows the
          replay scrubber when replay is running (band), otherwise shows both
          at once so the toggle alone is useful. */}
      {showHindcast && showSourceHeatmap && detected && (sourceHeatmap || forecastHeatmap) && (
        <ThermalHeatmapLayer sourceHeatmap={sourceHeatmap} forecastHeatmap={forecastHeatmap}
                             band={replayFrame?.band ?? null} />
      )}

      {/* hindcast: spill back to probable source */}
      {showHindcast && detected && shownSource && shownSpill && (
        <>
          <Polyline positions={[[shownSource.latitude, shownSource.longitude], [shownSpill.latitude, shownSpill.longitude]]}
                    pathOptions={{color: C.hindcast, weight: 3, opacity: .85}}>
            <Tooltip>{shownSpill.ship_name} · drift traced back {show(shownSource.hours_backward)} h</Tooltip>
          </Polyline>
          <CircleMarker center={[shownSource.latitude, shownSource.longitude]} radius={8}
                        pathOptions={{color: C.hindcast, fillColor: C.hindcastFill, fillOpacity: .9, weight: 3}}>
            <Tooltip>Probable source — model estimate<br />{showCoord(shownSource.latitude)}, {showCoord(shownSource.longitude)}</Tooltip>
          </CircleMarker>
        </>
      )}

      {/* forward kinematic projection */}
      {showForecast && detected && shownForecast?.points && shownForecast.points.length > 0 && shownSpill && (
        <>
          <Polyline positions={[[shownSpill.latitude, shownSpill.longitude], ...shownForecast.points.map((p: any) => [p.latitude, p.longitude] as [number, number])]}
                    pathOptions={{color: C.forecast, weight: 2.5, dashArray: "2 7", opacity: .9}} />
          {shownForecast.points.map((p: any) => (
            <CircleMarker key={p.hours_ahead} center={[p.latitude, p.longitude]} radius={4}
                          pathOptions={{color: C.forecast, fillColor: "#fff", fillOpacity: 1, weight: 2.5}}>
              <Tooltip>+{p.hours_ahead} h · {showCoord(p.latitude, 4)}, {showCoord(p.longitude, 4)}<br />Kinematic projection</Tooltip>
            </CircleMarker>
          ))}
        </>
      )}

      {/* FORWARD RISK: selected vessel's projected track and, if it
          intersects the spill, the simulated detour. Separate concept
          from attribution — this is forward-looking, not historic. */}
      {showRisk && selectedRisk && selected && (
        <>
          <Polyline
            positions={selectedRisk.projected_route.map((p: any) => [p.latitude, p.longitude] as [number, number])}
            pathOptions={{color: C.spill, weight: 2.5, dashArray: "1 6", opacity: .9}}>
            <Tooltip>{selected.name} · projected track (kinematic, {selectedRisk.forecast_horizon_hours} h)<br />Not a navigational prediction</Tooltip>
          </Polyline>
          {showDetour && selectedRisk.detour && (
            <Polyline
              positions={selectedRisk.detour.detour_waypoints.map((p: any) => [p.latitude, p.longitude] as [number, number])}
              pathOptions={{color: C.detour, weight: 3, dashArray: "6 4", opacity: .95}}>
              <Tooltip>{selected.name} · SIMULATED ROUTE AVOIDANCE<br />
                {fmt(selectedRisk.detour.original_heading_deg, 0)}° → {fmt(selectedRisk.detour.suggested_heading_deg, 0)}°
                ({selectedRisk.detour.heading_change_deg > 0 ? "+" : ""}{fmt(selectedRisk.detour.heading_change_deg, 0)}°)<br />
                Demo only — not navigation guidance</Tooltip>
            </Polyline>
          )}
        </>
      )}

      {/* track of the selected vessel only, to keep the map readable */}
      {selected?.track && selected.track.length > 1 && (
        <Polyline positions={selected.track.map((p: any) => [p.lat, p.lon] as [number, number])}
                  pathOptions={{color: C.track, weight: 2.5, opacity: .8}}>
          <Tooltip>{selected.name} · AIS track (where it has been)</Tooltip>
        </Polyline>
      )}

      {/* Every candidate's AIS track, so the ranking can be checked against
          where the vessels actually were. Drawn thin and faint, beneath the
          selected vessel's own track: six tracks at full weight is spaghetti,
          and the point is the shape of the traffic, not six equal claims. */}
      {candidateTracks.map((c: any) => (
        <Polyline key={c.ship_id}
                  positions={c.points}
                  pathOptions={{color: C.candidateTrack, weight: 1.5, opacity: .3, dashArray: "3 4"}}>
          <Tooltip>#{c.rank} {c.name} · AIS track<br />
            closest {fmt(c.minimum_distance_km, 2)} km · score {fmt(c.final_suspect_score)}</Tooltip>
        </Polyline>
      ))}

      {/* Where the selected vessel is HEADED — shown for every vessel, so a
          click always pairs the grey past track with a blue future one.
          An at-risk vessel's own projection is drawn in red further up. */}
      {showRisk && selected?.projected_track && selected.projected_track.length > 1 && !selectedRisk && (
        <Polyline
          positions={selected.projected_track.map((p: any) => [p.latitude, p.longitude] as [number, number])}
          pathOptions={{color: C.forecast, weight: 2.5, dashArray: "7 5", opacity: .9}}>
          <Tooltip>{selected.name} · projected track (where it is going)<br />
            Kinematic projection at {fmt(selected.speed_kt)} kt · {fmt(selected.course_deg, 0)}°</Tooltip>
        </Polyline>
      )}

      {/* REPLAY: the slick at the moment on the timeline. Its basis is drawn,
          not just written — dashed and hollow while the position is inferred
          (hindcast, or forecast), solid only at the pass the CNN actually
          classified. Nothing about the animation is allowed to make an
          estimate look like an observation. */}
      {replayFrame?.slick && (
        <CircleMarker
          center={[replayFrame.slick.lat, replayFrame.slick.lon]}
          radius={replayFrame.slick.basis === "observed" ? 13 : 11}
          pathOptions={{
            color: replayFrame.slick.basis === "observed" ? C.spill : C.hindcast,
            fillColor: replayFrame.slick.basis === "observed" ? C.spillFill : C.hindcastFill,
            fillOpacity: replayFrame.slick.basis === "observed" ? .75 : .22,
            weight: 3,
            dashArray: replayFrame.slick.basis === "observed" ? undefined : "4 4",
          }}>
          <Tooltip permanent direction="top" offset={[0, -12]}>
            {replayFrame.slick.basis === "observed"
              ? "OBSERVED — the pass the CNN classified"
              : replayFrame.slick.basis === "estimated"
                ? "ESTIMATED — hindcast, nobody observed the oil here"
                : "PROJECTED — kinematic forecast, no environmental data"}
          </Tooltip>
        </CircleMarker>
      )}

      {/* COUNTERFACTUAL: where this vessel's oil would now be if it had been
          the source, against where oil was actually seen. The gap between the
          two IS the result, so it is drawn as a measured line, not a claim. */}
      {whatIfShown?.available === true && (
        <>
          <Polyline
            positions={[
              [whatIfShown.assumed_release.latitude, whatIfShown.assumed_release.longitude],
              [whatIfShown.simulated_now.latitude, whatIfShown.simulated_now.longitude],
            ]}
            pathOptions={{color: C.counterfactual, weight: 2.5, dashArray: "6 4", opacity: .9}}>
            <Tooltip>{whatIfShown.name} · simulated drift if it were the source<br />
              from its real AIS fix at {String(whatIfShown.assumed_release.ais_fix_time).slice(11, 16)} UTC</Tooltip>
          </Polyline>
          <CircleMarker
            center={[whatIfShown.assumed_release.latitude, whatIfShown.assumed_release.longitude]}
            radius={6}
            pathOptions={{color: C.counterfactual, fillColor: C.counterfactualFill, fillOpacity: 1, weight: 2.5}}>
            <Tooltip>{whatIfShown.name} · actual AIS position at the estimated release time</Tooltip>
          </CircleMarker>
          <CircleMarker
            center={[whatIfShown.simulated_now.latitude, whatIfShown.simulated_now.longitude]}
            radius={7}
            pathOptions={{color: C.counterfactual, fillColor: C.counterfactual, fillOpacity: .55, weight: 2.5, dashArray: "3 3"}}>
            <Tooltip>Simulated slick position now<br />
              {fmt(whatIfShown.miss_distance_km, 2)} km from where oil was actually seen</Tooltip>
          </CircleMarker>
          {/* the miss itself */}
          <Polyline
            positions={[
              [whatIfShown.simulated_now.latitude, whatIfShown.simulated_now.longitude],
              [whatIfShown.observed_now.latitude, whatIfShown.observed_now.longitude],
            ]}
            pathOptions={{color: C.counterfactual, weight: 2, dashArray: "1 5", opacity: .8}}>
            <Tooltip>Miss: {fmt(whatIfShown.miss_distance_km, 2)} km between simulated and observed</Tooltip>
          </Polyline>
        </>
      )}

      {/* monitored vessels — an amber ring marks a vessel FORWARD RISK
          flagged as projected to enter the spill area (separate from
          the oil-detected red fill, which is the CNN's own call). */}
      {fleet.map((s: any) => {
        const atRisk = riskByShipId[s.id];
        // Under replay the vessel sits where the timeline puts it, and a
        // hollow marker says that position is projected, not reported.
        const rp = replayFrame?.vessels?.find((v: any) => v.sh.id === s.id)?.at;
        const centre: [number, number] = rp ? [rp.lat, rp.lon] : [s.latitude, s.longitude];
        const projected = rp ? !rp.observed : false;
        // Oil is a fact about the pass, so during replay it is only true once
        // the timeline has actually reached the detection.
        const oil = s.oil_detected && (!replayFrame || replayFrame.band === "observed"
                                       || replayFrame.band === "projected");
        return (
          <CircleMarker
            key={s.id}
            center={centre}
            radius={oil ? 10 : atRisk ? 8 : 6}
            pathOptions={{
              color: oil ? C.spill : atRisk ? C.atRisk : C.forecast,
              fillColor: oil ? C.spillFill : C.vesselFill,
              fillOpacity: projected ? .15 : (selected?.id === s.id ? 1 : .8),
              weight: selected?.id === s.id ? 4 : (atRisk ? 3 : 2),
              dashArray: projected ? "3 3" : (atRisk && !oil ? "3 2" : undefined),
            }}
            eventHandlers={{click: () => setSelected(s)}}
          >
            <Tooltip>
              <b>{s.name}</b><br />MMSI {s.mmsi}<br />
              {s.status}{s.confidence ? ` · ${showPct(s.confidence)}` : ""}
              {atRisk && <><br /><b>AT RISK</b> · entry ~{atRisk.estimated_entry_minutes} min</>}
            </Tooltip>
          </CircleMarker>
        );
      })}

      {legendOpen && <div className="legend">
        <b>LEGEND</b>
        <span><i className="dot" style={{background: C.vesselFill}} />Vessel</span>
        <span><i className="dot" style={{background: C.spillFill}} />Oil detected</span>
        <span><i style={{width: 18, height: 0, borderTop: `2px solid ${C.track}`}} />Selected vessel's past track</span>
        {detected && <span><i style={{width: 18, height: 0, borderTop: `3px solid ${C.hindcast}`}} />Where the oil drifted from ({show(source?.hours_backward)} h)</span>}
        {detected && <span><i style={{width: 18, height: 0, borderTop: `2px dotted ${C.forecast}`}} />Where it will drift next (48 h)</span>}
        {detected && <span><i style={{width: 18, height: 0, borderTop: `1px dashed ${C.spill}`}} />Possible affected area</span>}
        {detected && <span><i style={{width: 10, height: 10, borderRadius: "50%", border: `2px dashed ${C.atRisk}`, display: "inline-block"}} />Vessel at risk (forward projection)</span>}
        {detected && <span><i style={{width: 18, height: 0, borderTop: `3px dashed ${C.detour}`}} />Simulated detour (demo only)</span>}
        <span><i style={{width: 18, height: 0, borderTop: `2px dashed ${C.forecast}`}} />Selected vessel's projected track</span>
        {candidateTracks.length > 0 && (
          <span><i style={{width: 18, height: 0, borderTop: `2px dashed ${C.candidateTrack}`, opacity: .5}} />Other candidates' AIS tracks</span>
        )}
        {showEnvironment && (
          <span><i style={{width: 18, height: 0, borderTop: `2px ${environment?.environment_mode === "historical" ? "solid" : "dashed"} ${C.environment}`}} />
            Effective drift{environment?.environment_mode === "historical" ? "" : " (assumed, uniform)"}</span>
        )}
        {showSourceHeatmap && (
          <span>
            <i style={{width: 18, height: 8, borderRadius: 2, background:
              "linear-gradient(90deg,#22c55e,#a3e635,#facc15,#fb923c,#ef4444)"}} />
            Where it came from / is heading — not a probability
          </span>
        )}
      </div>}
      {setShowEnvironment && (
        <button className={"legendbtn envbtn" + (showEnvironment ? " open" : "")}
                onClick={() => setShowEnvironment((v: boolean) => !v)}
                title={showEnvironment
                  ? "Hide the drift field"
                  : "Show the drift field the impact envelope is sized from"}
                aria-label="Toggle environmental drift layer" aria-pressed={showEnvironment}>
          <Wind size={17} />
        </button>
      )}
      {setShowSourceHeatmap && detected && (
        <button className={"legendbtn heatbtn" + (showSourceHeatmap ? " open" : "")}
                onClick={() => setShowSourceHeatmap((v: boolean) => !v)}
                title={showSourceHeatmap
                  ? "Exit thermal view"
                  : "Thermal view: dark map, where the oil likely came from and is heading"}
                aria-label="Toggle thermal heat map" aria-pressed={showSourceHeatmap}>
          <Flame size={17} />
        </button>
      )}
      <button className={"legendbtn" + (legendOpen ? " open" : "")}
              onClick={() => setLegendOpen((v: boolean) => !v)}
              title={legendOpen ? "Hide legend" : "What do the colours and lines mean?"}
              aria-label="Toggle map legend" aria-expanded={legendOpen}>
        <Info size={17} />
      </button>
    </MapContainer>
  );
}
