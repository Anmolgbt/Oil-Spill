import {useEffect, useMemo, useState} from "react";
import {CircleMarker, MapContainer, Polygon, Polyline, TileLayer, Tooltip, useMap} from "react-leaflet";
import L from "leaflet";
import {AlertTriangle, Anchor, Check, FileText, Info, X} from "lucide-react";
import {NOT_AVAILABLE, fleetViewport, getInvestigation, runFleetScan, show, showCoord, showPct} from "./lib/oiltrace";

/**
 * OILTRACE dashboard.
 *
 * One question per panel: which ships are we watching, did the satellite see oil,
 * where did it come from, who was nearby, where is it going.
 *
 * Nothing here computes an investigation value. Every number comes from the
 * backend scan; anything the models cannot produce renders as "Not available".
 */

const FALLBACK_CENTER: [number, number] = [28.55, -94.85];

const fmt = (v: any, digits = 1) => (typeof v === "number" ? v.toFixed(digits) : NOT_AVAILABLE);

/** Ring of lat/lng around a point, for the drift envelope. */
const ring = (lat: number, lon: number, km: number): [number, number][] => {
  const dLat = km / 110.574;
  const dLon = km / (111.32 * Math.cos((lat * Math.PI) / 180));
  return Array.from({length: 49}, (_, i) => {
    const a = (i * 7.5 * Math.PI) / 180;
    return [lat + dLat * Math.cos(a), lon + dLon * Math.sin(a)] as [number, number];
  });
};

function Card({children, className = ""}: {children: any; className?: string}) {
  return <section className={"card " + className}>{children}</section>;
}
function Badge({children, tone = "blue"}: {children: any; tone?: string}) {
  return <span className={"badge " + tone}>{children}</span>;
}
/** Fit the map to everything the scan produced. */
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

function App() {
  const [scan, setScan] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [selected, setSelected] = useState<any>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [error, setError] = useState("");
  const [fallback, setFallback] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);

  const load = async (snapshotId?: string) => {
    setRunning(true);
    setError("");
    setSelected(null);

    // 1. live fleet scan  2. stored completed case  3. bundled JSON
    const fleetScan = await runFleetScan(snapshotId);
    if (fleetScan) {
      setScan(fleetScan);
      setFallback(false);
      // Open on the vessel the signature was found near, so the panel is never
      // empty on a pass that detected something.
      const top = fleetScan.detections?.[0];
      if (top) setSelected(fleetScan.fleet.find((f: any) => f.id === top.id) ?? top);
      setRunning(false);
      return;
    }
    // The stored completed case nests its fields differently to a fleet scan, so
    // normalise it here rather than teaching every panel two shapes.
    const stored = await getInvestigation();
    if (stored) {
      const det = stored.detection || {};
      const cands = stored.ais?.candidates || [];
      setScan({
        ...stored,
        status: det.oil_detected ? "SPILL_DETECTED" : "CLEAR",
        message: `Stored completed case — ${det.prediction ?? "result"} at ` +
                 `${det.confidence != null ? (det.confidence * 100).toFixed(2) + "%" : "unknown"} confidence. ` +
                 "Live scan unavailable.",
        fleet: [],
        scanned: 0,
        snapshot_id: null,
        observed_at: null,
        available_snapshots: [],
        spill: stored.spill ? {
          ...stored.spill,
          ship_name: cands[0]?.name ?? `MMSI ${cands[0]?.mmsi ?? "—"}`,
          confidence: det.confidence,
        } : null,
        age: stored.source?.hours_backward != null
          ? {estimated_hours: stored.source.hours_backward, release_at: null}
          : null,
        affected_area: null,   // no envelope in the stored payload; do not invent one
        candidates: cands.map((c: any) => ({...c, name: c.name ?? `MMSI ${c.mmsi}`, in_fleet: true})),
        ais: stored.ais,
      });
      setFallback(true);
      setRunning(false);
      return;
    }
    setError("Backend unreachable and no bundled result available.");
    setRunning(false);
  };

  useEffect(() => { load(); }, []);

  const fleet = scan?.fleet || [];
  const spill = scan?.spill;
  const source = scan?.source;
  const candidates = scan?.candidates || [];
  const forecast = scan?.forecast;
  const age = scan?.age;
  const area = scan?.affected_area;
  const detected = scan?.status === "SPILL_DETECTED";

  const rankByMmsi = useMemo(
    () => Object.fromEntries(candidates.map((c: any) => [c.mmsi, c])),
    [candidates]
  );

  // Each flagged vessel carries its own spill findings.
  const spillFor = (ship: any) =>
    ship ? (scan?.spills || []).find((sp: any) => sp.spill?.ship_id === ship.id) : undefined;
  const sel = spillFor(selected);
  // Map overlays follow the selected spill, falling back to the strongest detection.
  const shown = sel || (scan?.spills || [])[0];
  const shownSpill = shown?.spill ?? spill;
  const shownSource = shown?.source ?? source;
  const shownArea = shown?.affected_area ?? area;
  const shownForecast = shown?.forecast ?? forecast;

  const view = useMemo(() => (scan ? fleetViewport(scan) : null), [scan]);
  const envelope = detected && shownSpill && shownArea?.radius_km
    ? ring(shownSpill.latitude, shownSpill.longitude, shownArea.radius_km) : null;

  // FORWARD RISK — which vessels are projected to enter the spill area next.
  // Kept separate from `candidates` (attribution: who may have caused it,
  // from historic AIS). This looks forward from each vessel's current AIS fix.
  const shownRisk = shown?.risk;
  const riskByShipId = useMemo(
    () => Object.fromEntries((shownRisk?.at_risk || []).map((r: any) => [r.ship_id, r])),
    [shownRisk]
  );
  const selectedRisk = selected ? riskByShipId[selected.id] : undefined;

  if (!scan && !error) return <div className="loading">Loading OILTRACE…</div>;
  if (error) return <div className="loading">{error}</div>;

  const mode = fallback ? "STORED RESULT" : "LIVE INFERENCE";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brandmark"><Anchor size={18} /></div>
          <div><b>OILTRACE</b><small>SATELLITE + AIS OIL-SPILL MONITORING</small></div>
        </div>
        <div className="incident">
          <span className="live-dot" />
          <Badge tone={fallback ? "amber" : "blue"}>{mode}</Badge>
          {scan.snapshot_id && <strong>PASS {String(scan.snapshot_id).toUpperCase()}</strong>}
          <button className="reportbtn" onClick={() => setReportOpen(true)}
                  style={{border: "1px solid var(--line)", background: "var(--panel)",
                          borderRadius: 7, padding: "7px 12px", fontSize: 13, fontWeight: 600,
                          display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
                          marginLeft: 6}}>
            <FileText size={14} /> Report
          </button>
        </div>
      </header>

      {/* One-line verdict. Red only when the model actually found oil. */}
      <div className={"alertbar" + (detected ? "" : " ok")}>
        {detected ? <AlertTriangle size={16} /> : <Check size={16} />}
        <b>{detected ? "OIL SPILL DETECTED" : "NO OIL DETECTED"}</b>
        <span>{scan.message}</span>
      </div>

      <main className="layout">
        {/* ---------------- left: fleet + forecast ---------------- */}
        <aside className="left">
          <Card>
            <div className="eyebrow">
              MONITORED FLEET
              <span style={{marginLeft: "auto", textTransform: "none", letterSpacing: 0}}>
                {running ? "scanning…" : `${fleet.length} vessels`}
              </span>
            </div>
            {(scan.available_snapshots || []).length > 1 && (
              <div className="timebar" style={{marginBottom: 12}}>
                <b>PASS</b>
                {scan.available_snapshots.map((sid: string) => (
                  <button key={sid} className={scan.snapshot_id === sid ? "sel" : ""}
                          disabled={running} onClick={() => load(sid)}>
                    {sid.toUpperCase()}
                  </button>
                ))}
              </div>
            )}
            <div className="candidates">
              {fleet.length ? fleet.map((s: any) => (
                <button key={s.id}
                        className={"candidate " + (selected?.id === s.id ? "selected" : "")}
                        onClick={() => setSelected(s)}>
                  <div className="rank">
                    <i className="dot" style={{background: s.oil_detected ? "#e2554a" : "#5b9bd8"}} />
                  </div>
                  <div className="cv">
                    <b>{s.name}</b>
                    <small>{s.vessel_type} · {fmt(s.speed_kt)} kt · {s.status}</small>
                  </div>
                  <strong style={{color: s.oil_detected ? "var(--danger)" : "var(--ink-mute)"}}>
                    {s.confidence ? showPct(s.confidence, 0) : "—"}
                  </strong>
                </button>
              )) : <div className="empty">Fleet data unavailable in this mode.</div>}
            </div>
          </Card>

          {/* Forecast belongs to a specific spill, so it shows only for a flagged vessel. */}
          {sel && (
            <Card>
              <div className="eyebrow">
                WHERE THIS OIL GOES NEXT <Badge tone="amber">KINEMATIC</Badge>
              </div>
              <div className="subtle" style={{marginBottom: 6, fontSize: 12}}>
                From {selected.name}
              </div>
              <div className="metrics" style={{marginTop: 4}}>
                {(sel.forecast?.points || []).map((p: any) => (
                  <div key={p.hours_ahead}>
                    <small>+{p.hours_ahead} h</small>
                    <b style={{fontSize: 14}}>{showCoord(p.latitude, 3)}, {showCoord(p.longitude, 3)}</b>
                  </div>
                ))}
              </div>
              <div className="subtle" style={{marginTop: 10}}>
                No wind, current or wave data — drift uses a fixed assumed vector.
              </div>
            </Card>
          )}
        </aside>

        {/* ---------------- map ---------------- */}
        <section className="mapwrap">
          <div className="maphead">
            <div>
              <span className="eyebrow">MONITORING MAP</span>
              <h1>{scan.region || "Monitoring area"}</h1>
              <div className="subtle">
                {scan.observed_at
                  ? `Pass ${String(scan.snapshot_id).toUpperCase()} · ${scan.observed_at.slice(0, 16).replace("T", " ")} UTC · revisit every ${scan.pass_interval_hours ?? "—"} h`
                  : "Stored result"}
              </div>
            </div>
            <div className="maptools">
              {detected
                ? <><Badge tone="red">SPILL</Badge><Badge tone="amber">SOURCE ESTIMATE</Badge></>
                : <Badge tone="blue">ALL CLEAR</Badge>}
            </div>
          </div>

          <MapContainer center={view?.center ?? FALLBACK_CENTER} zoom={7} className="map" scrollWheelZoom>
            <MapFit points={view?.points ?? null} />
            <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

            {/* possible affected area — drift envelope, never a measured slick */}
            {envelope && (
              <Polygon positions={envelope} pathOptions={{color: "#c0261b", fillColor: "#c0261b", fillOpacity: .05, weight: 1.5, dashArray: "5 6"}}>
                <Tooltip>{shownSpill?.ship_name} · possible affected area, {fmt(shownArea?.radius_km)} km radius<br />Drift envelope, not a measured slick</Tooltip>
              </Polygon>
            )}

            {/* hindcast: spill back to probable source */}
            {detected && shownSource && shownSpill && (
              <>
                <Polyline positions={[[shownSource.latitude, shownSource.longitude], [shownSpill.latitude, shownSpill.longitude]]}
                          pathOptions={{color: "#b45309", weight: 3, opacity: .85}}>
                  <Tooltip>{shownSpill.ship_name} · drift traced back {show(shownSource.hours_backward)} h</Tooltip>
                </Polyline>
                <CircleMarker center={[shownSource.latitude, shownSource.longitude]} radius={8}
                              pathOptions={{color: "#b45309", fillColor: "#f59e0b", fillOpacity: .9, weight: 3}}>
                  <Tooltip>Probable source — model estimate<br />{showCoord(shownSource.latitude)}, {showCoord(shownSource.longitude)}</Tooltip>
                </CircleMarker>
              </>
            )}

            {/* forward kinematic projection */}
            {detected && shownForecast?.points?.length > 0 && shownSpill && (
              <>
                <Polyline positions={[[shownSpill.latitude, shownSpill.longitude], ...shownForecast.points.map((p: any) => [p.latitude, p.longitude] as [number, number])]}
                          pathOptions={{color: "#0b5cab", weight: 2.5, dashArray: "2 7", opacity: .9}} />
                {shownForecast.points.map((p: any) => (
                  <CircleMarker key={p.hours_ahead} center={[p.latitude, p.longitude]} radius={4}
                                pathOptions={{color: "#0b5cab", fillColor: "#fff", fillOpacity: 1, weight: 2.5}}>
                    <Tooltip>+{p.hours_ahead} h · {showCoord(p.latitude, 4)}, {showCoord(p.longitude, 4)}<br />Kinematic projection</Tooltip>
                  </CircleMarker>
                ))}
              </>
            )}

            {/* FORWARD RISK: selected vessel's projected track and, if it
                intersects the spill, the simulated detour. Separate concept
                from attribution — this is forward-looking, not historic. */}
            {selectedRisk && (
              <>
                <Polyline
                  positions={selectedRisk.projected_route.map((p: any) => [p.latitude, p.longitude] as [number, number])}
                  pathOptions={{color: "#c0261b", weight: 2.5, dashArray: "1 6", opacity: .9}}>
                  <Tooltip>{selected.name} · projected track (kinematic, {selectedRisk.forecast_horizon_hours} h)<br />Not a navigational prediction</Tooltip>
                </Polyline>
                {selectedRisk.detour && (
                  <Polyline
                    positions={selectedRisk.detour.detour_waypoints.map((p: any) => [p.latitude, p.longitude] as [number, number])}
                    pathOptions={{color: "#1a8a4a", weight: 3, dashArray: "6 4", opacity: .95}}>
                    <Tooltip>{selected.name} · SIMULATED ROUTE AVOIDANCE<br />
                      {fmt(selectedRisk.detour.original_heading_deg, 0)}° → {fmt(selectedRisk.detour.suggested_heading_deg, 0)}°
                      ({selectedRisk.detour.heading_change_deg > 0 ? "+" : ""}{fmt(selectedRisk.detour.heading_change_deg, 0)}°)<br />
                      Demo only — not navigation guidance</Tooltip>
                  </Polyline>
                )}
              </>
            )}

            {/* track of the selected vessel only, to keep the map readable */}
            {selected?.track?.length > 1 && (
              <Polyline positions={selected.track.map((p: any) => [p.lat, p.lon] as [number, number])}
                        pathOptions={{color: "#8a95a3", weight: 2.5, opacity: .8}}>
                <Tooltip>{selected.name} · AIS track</Tooltip>
              </Polyline>
            )}

            {/* monitored vessels — an amber ring marks a vessel FORWARD RISK
                flagged as projected to enter the spill area (separate from
                the oil-detected red fill, which is the CNN's own call). */}
            {fleet.map((s: any) => {
              const atRisk = riskByShipId[s.id];
              return (
                <CircleMarker
                  key={s.id}
                  center={[s.latitude, s.longitude]}
                  radius={s.oil_detected ? 10 : atRisk ? 8 : 6}
                  pathOptions={{
                    color: s.oil_detected ? "#c0261b" : atRisk ? "#b8860b" : "#0b5cab",
                    fillColor: s.oil_detected ? "#e2554a" : "#5b9bd8",
                    fillOpacity: selected?.id === s.id ? 1 : .8,
                    weight: selected?.id === s.id ? 4 : (atRisk ? 3 : 2),
                    dashArray: atRisk && !s.oil_detected ? "3 2" : undefined,
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
              <span><i className="dot" style={{background: "#5b9bd8"}} />Vessel</span>
              <span><i className="dot" style={{background: "#e2554a"}} />Oil detected</span>
              <span><i style={{width: 18, height: 0, borderTop: "2px solid #8a95a3"}} />Selected vessel's past track</span>
              {detected && <span><i style={{width: 18, height: 0, borderTop: "3px solid #b45309"}} />Where the oil drifted from ({show(source?.hours_backward)} h)</span>}
              {detected && <span><i style={{width: 18, height: 0, borderTop: "2px dotted #0b5cab"}} />Where it will drift next (48 h)</span>}
              {detected && <span><i style={{width: 18, height: 0, borderTop: "1px dashed #c0261b"}} />Possible affected area</span>}
              {detected && <span><i style={{width: 10, height: 10, borderRadius: "50%", border: "2px dashed #b8860b", display: "inline-block"}} />Vessel at risk (forward projection)</span>}
              {detected && <span><i style={{width: 18, height: 0, borderTop: "3px dashed #1a8a4a"}} />Simulated detour (demo only)</span>}
            </div>}
            <button className={"legendbtn" + (legendOpen ? " open" : "")}
                    onClick={() => setLegendOpen((v) => !v)}
                    title={legendOpen ? "Hide legend" : "What do the colours and lines mean?"}
                    aria-label="Toggle map legend" aria-expanded={legendOpen}>
              <Info size={17} />
            </button>
          </MapContainer>

          <div className="mapbottom">
            <div className="env">
              <Info size={14} />
              <span>WIND <b>{NOT_AVAILABLE}</b></span>
              <span>CURRENT <b>{NOT_AVAILABLE}</b></span>
              <span>WAVE <b>{NOT_AVAILABLE}</b></span>
              <span style={{marginLeft: "auto"}}>Drift uses a fixed assumed vector — no environmental data.</span>
            </div>
          </div>
        </section>

        {/* ---------------- right: vessel detail ---------------- */}
        <aside className="right">
          <Card>
            <div className="eyebrow">
              VESSEL DETAIL
              {selected?.oil_detected && <Badge tone="red">OIL DETECTED</Badge>}
              {selectedRisk && <Badge tone="amber">AT RISK</Badge>}
            </div>
            {selected ? (
              <>
                <div className="vname">{selected.name}</div>
                <div className="subtle">MMSI {selected.mmsi} · {selected.vessel_type}</div>

                <div className="detailtop">
                  <div>
                    {selected.image_url
                      ? <div className="scene"><img src={selected.image_url} alt="SAR tile" /></div>
                      : <div className="scene" />}
                    <div className="scene-meta">
                      <span>Sentinel-1 SAR · pass {String(scan.snapshot_id).toUpperCase()}</span>
                    </div>
                  </div>
                  <div>
                    <div className="metrics" style={{marginTop: 0}}>
                      <div style={{gridColumn: "1 / 3"}}>
                        <small>CNN result</small>
                        <b style={{fontSize: 17, color: selected.oil_detected ? "var(--danger)" : "var(--ok)"}}>
                          {selected.prediction ?? NOT_AVAILABLE}
                        </b>
                      </div>
                      <div style={{gridColumn: "1 / 3"}}>
                        <small>Confidence</small>
                        <b style={{fontSize: 17}}>{selected.confidence ? showPct(selected.confidence) : NOT_AVAILABLE}</b>
                      </div>
                      <div style={{gridColumn: "1 / 3"}}>
                        <small>Suspect score</small>
                        <b>{rankByMmsi[selected.mmsi]
                            ? `${fmt(rankByMmsi[selected.mmsi].final_suspect_score)} / 100`
                            : "Not ranked"}</b>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="metrics">
                  <div><small>Position</small><b>{showCoord(selected.latitude, 3)}, {showCoord(selected.longitude, 3)}</b></div>
                  <div><small>Speed / course</small><b>{fmt(selected.speed_kt)} kt · {fmt(selected.course_deg, 0)}°</b></div>
                </div>
                <div className="metrics">
                  <div><small>Last AIS fix</small><b>{selected.position_time ? selected.position_time.slice(5, 16).replace("T", " ") : NOT_AVAILABLE}</b></div>
                  <div><small>AIS fixes held</small><b>{selected.track?.length ?? 0}</b></div>
                </div>

                {/* Findings belong to the vessel they were found on, so each
                    flagged ship shows its own spill characterisation. */}
                {sel && (
                  <>
                    <div className="eyebrow" style={{marginTop: 16}}>SPILL FOUND HERE</div>
                    <div className="metrics" style={{marginTop: 0}}>
                      <div><small>Max age</small><b>{show(sel.age?.estimated_hours, " h")}</b></div>
                      <div><small>Released (est.)</small><b>{sel.age?.release_at ? `${sel.age.release_at.slice(11, 16)} UTC` : NOT_AVAILABLE}</b></div>
                    </div>
                    <div className="metrics">
                      <div><small>Probable source</small><b>{showCoord(sel.source?.latitude, 3)}, {showCoord(sel.source?.longitude, 3)}</b></div>
                      <div><small>Search zone</small><b>{fmt(sel.affected_area?.radius_km)} km · {fmt(sel.affected_area?.area_km2, 0)} km²</b></div>
                    </div>
                    <div className="metrics">
                      <div style={{gridColumn: "1 / 3"}}>
                        <small>Vessels near this source</small>
                        <b>{sel.candidates.length
                            ? sel.candidates.map((c: any) => `${c.name} (${fmt(c.final_suspect_score)})`).join(", ")
                            : `None within ${fmt(sel.ais?.search_radius_km, 0)} km`}</b>
                      </div>
                    </div>
                  </>
                )}

              </>
            ) : (
              <div className="empty">Select a vessel on the map or in the fleet list.</div>
            )}
          </Card>
        </aside>
      </main>

      {/* ---------------- leaking-vessel leaderboard ---------------- */}
      {detected && (
        <div className="oilstrip">
          <div className="eyebrow">
            VESSELS SHOWING AN OIL SIGNATURE
            <span style={{marginLeft: "auto", textTransform: "none", letterSpacing: 0}}>
              {(scan.detections || []).length} of {scan.scanned} scanned
            </span>
          </div>
          <div className="oilhead">
            <span>#</span><span>Vessel</span><span>Position</span>
            <span>Attribution</span><span>CNN confidence</span>
          </div>
          {(scan.detections || []).map((d: any, i: number) => {
            const rank = rankByMmsi[d.mmsi];
            return (
              <button key={d.id}
                      className={"oilrank " + (selected?.id === d.id ? "selected" : "")}
                      onClick={() => setSelected(d)}>
                <span className="pos">
                  {i + 1}
                  <i className="dot" style={{background: "#e2554a"}} />
                </span>
                <span className="vessel">
                  <b>{d.name}</b>
                  <small>MMSI {d.mmsi} · {d.vessel_type}</small>
                </span>
                <span className="meta">
                  {showCoord(d.latitude, 3)}, {showCoord(d.longitude, 3)}
                </span>
                <span className="sus">
                  {rank
                    ? <>Suspect #{rank.rank} · score <b>{fmt(rank.final_suspect_score)}</b> · {fmt(rank.minimum_distance_km, 1)} km from source</>
                    : <>Not ranked — not near the estimated source in the release window</>}
                </span>
                <span className="pct">{showPct(d.confidence, 1)}</span>
              </button>
            );
          })}
          <div className="subtle" style={{marginTop: 6, fontSize: 12}}>
            Analytical association with an estimated source window — not proof of responsibility.
          </div>
        </div>
      )}

      {/* ---------------- forward risk: vessels projected to enter the spill ---------------- */}
      {detected && shownRisk && (
        <div className="oilstrip">
          <div className="eyebrow">
            VESSELS AT RISK <Badge tone="amber">FORWARD PROJECTION</Badge>
            <span style={{marginLeft: "auto", textTransform: "none", letterSpacing: 0}}>
              {shownRisk.at_risk_count} of {shownRisk.vessels_checked} projected to enter · {shownRisk.safe_count} safe
            </span>
          </div>
          {shownRisk.at_risk.length ? (
            <>
              <div className="oilhead">
                <span>#</span><span>Vessel</span><span>Entry / horizon</span>
                <span>Detour</span><span>Risk</span>
              </div>
              {shownRisk.at_risk.map((r: any, i: number) => (
                <button key={r.ship_id}
                        className={"oilrank " + (selected?.id === r.ship_id ? "selected" : "")}
                        onClick={() => setSelected(fleet.find((f: any) => f.id === r.ship_id))}>
                  <span className="pos">
                    {i + 1}
                    <i className="dot" style={{background: "#b8860b"}} />
                  </span>
                  <span className="vessel">
                    <b>{r.name}</b>
                    <small>MMSI {r.mmsi}</small>
                  </span>
                  <span className="meta">
                    ~{r.estimated_entry_minutes} min · of {r.forecast_horizon_hours} h horizon
                  </span>
                  <span className="sus">
                    {r.detour
                      ? <>{fmt(r.detour.original_heading_deg, 0)}° → <b>{fmt(r.detour.suggested_heading_deg, 0)}°</b>
                        {" "}({r.detour.heading_change_deg > 0 ? "+" : ""}{fmt(r.detour.heading_change_deg, 0)}°)</>
                      : "No detour computed"}
                  </span>
                  <span className="pct" style={{color: r.risk === "HIGH" ? "var(--danger)" : "var(--warn)"}}>
                    {r.risk}
                  </span>
                </button>
              ))}
            </>
          ) : (
            <div className="empty">No monitored vessel is projected to enter the affected area.</div>
          )}
          <div className="subtle" style={{marginTop: 6, fontSize: 12}}>
            Kinematic projection from each vessel's current speed/heading — a prototype trajectory, not a
            navigational prediction. Detour headings are a SIMULATED ROUTE AVOIDANCE demo, not maritime guidance.
          </div>
        </div>
      )}

      {reportOpen && (
        <div className="modal">
          <div className="modalbox reportbox">
            <button className="close" onClick={() => setReportOpen(false)}><X /></button>
            <div className="reporthead">
              <div><b>OILTRACE</b><small>MONITORING REPORT · PASS {String(scan.snapshot_id).toUpperCase()}</small></div>
              <Badge tone={detected ? "red" : "blue"}>{detected ? "SPILL DETECTED" : "ALL CLEAR"}</Badge>
            </div>
            <h2>{detected ? `Oil signature near ${spill?.ship_name}` : "No oil signature detected"}</h2>
            <p>{scan.message}</p>
            <div className="reportgrid">
              <div><small>CONFIDENCE</small><b>{detected ? showPct(spill?.confidence) : NOT_AVAILABLE}</b></div>
              <div><small>SPILL AREA</small><b>{NOT_AVAILABLE}</b></div>
              <div><small>EST. AGE</small><b>{detected ? show(age?.estimated_hours, " h") : NOT_AVAILABLE}</b></div>
              <div><small>SUSPECTS</small><b>{detected ? candidates.length : NOT_AVAILABLE}</b></div>
            </div>
            {detected && (
              <>
                <h3>Suspect ranking</h3>
                {candidates.map((c: any, i: number) => (
                  <div className="reportcandidate" key={c.mmsi}>
                    <b>#{i + 1} {c.name}</b>
                    <strong>{fmt(c.final_suspect_score)}</strong>
                    <span>MMSI {c.mmsi} · {fmt(c.minimum_distance_km, 2)} km · {c.trajectory_status}</span>
                  </div>
                ))}
              </>
            )}
            <div className="disclaimer" style={{marginTop: 14}}>
              <Info size={14} />
              Classification only — no segmentation, so no spill area, thickness or boundary.
              Source and age are model estimates; the forecast is a kinematic projection with no
              environmental data. Vessel ranking does not establish responsibility.
            </div>
            <button className="print" onClick={() => window.print()}><FileText size={15} /> Print / Save PDF</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
