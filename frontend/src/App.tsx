import {useEffect, useMemo, useState, useRef} from "react";
import {AlertTriangle, Anchor, Check, ExternalLink, FileText, Fish, Leaf, Users, Waves} from "lucide-react";
import {fleetViewport, getInvestigation, getFleetMetadata, runCounterfactual, runFleetScan, showPct, NOT_AVAILABLE} from "./lib/oiltrace";
import {Badge, Card, fmt, ring} from "./ui";
import {MapView} from "./components/MapView";
import {ReportModal} from "./components/ReportModal";
import {CandidateList} from "./components/CandidateList";
import {VesselDetail} from "./components/VesselDetail";
import {GovernmentActions} from "./components/GovernmentActions";
import {ResponsePriorityStrip} from "./components/ResponsePriorityStrip";
import {PassControls} from "./components/PassControls";
import {EvidencePanel} from "./components/EvidencePanel";
import {ModalFrame} from "./components/ModalFrame";
import {ReplayBar} from "./components/ReplayBar";
import type {ReplayFrame} from "./components/MapView";
import {HOUR_MS, slickAt, vesselAt} from "./lib/replay";
import {usePanel} from "./hooks/usePanel";
import {FlowModal} from "./components/FlowModal";
import {ModelInfoButton, ModelInfoModal} from "./components/ModelInfoModal";
import {PassUploader} from "./components/PassUploader";
import {VesselsAtRiskStrip} from "./components/VesselsAtRiskStrip";
import {MAP_COLOURS as C} from "./mapColours";
import type {Candidate, ForecastPoint, RiskEntry, Scan, Ship, SpillEntry,
              TrackFix} from "./types";

/**
 * OILTRACE dashboard.
 *
 * One question per panel: which ships are we watching, did the satellite see oil,
 * where did it come from, who was nearby, where is it going.
 *
 * Nothing here computes an investigation value. Every number comes from the
 * backend scan; anything the models cannot produce renders as "Not available".
 *
 * The map, the stage definitions and the shared atoms live in
 * their own modules; what remains here is the dashboard's state and layout.
 */



function App() {
  const [scan, setScan] = useState<Scan | null>(null);
  const [running, setRunning] = useState(false);
  const [selected, setSelected] = useState<Ship | null>(null);
  const {panel, openPanel, closePanel} = usePanel();
  const [evidenceMmsi, setEvidenceMmsi] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [fallback, setFallback] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);
  // The drift field is context, not a finding, so it starts hidden.
  const [showEnvelope, setShowEnvelope] = useState(true);
  const [showEnvironment, setShowEnvironment] = useState(true);
  const [showSourceHeatmap, setShowSourceHeatmap] = useState(true);
  // Which spill the map overlays follow. Separate from `selected` (the vessel
  // in the detail panel): selecting an at-risk vessel used to make the shown
  // spill fall back to spills[0], which silently swapped the at-risk list and
  // wiped the detour the user had just clicked in to see.
  const [focusedSpillId, setFocusedSpillId] = useState<string | null>(null);
  // Which vessel's detour has been explicitly asked for. The backend computes a
  // detour for every at-risk vessel on every scan, but a route change is an
  // action someone takes, not a fact about the sea — so it stays off the map
  // until requested.
  const [rerouteFor, setRerouteFor] = useState<string | null>(null);
  // Counterfactual results, keyed `${spillShipId}:${mmsi}` so testing a vessel
  // against one spill does not overwrite its result against the other.
  const [whatIf, setWhatIf] = useState<Record<string, any>>({});
  const [whatIfBusy, setWhatIfBusy] = useState<string | null>(null);
  const [replayT, setReplayT] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const loadSequence = useRef(0);
  const load = async (snapshotId?: string) => {
    const sequence = ++loadSequence.current;
    setRunning(true);
    setPlaying(false);
    setReplayT(null);
    setError("");
    setSelected(null);
    setFocusedSpillId(null);
    setRerouteFor(null);
    setWhatIf({});

    // 1. live fleet scan  2. stored completed case  3. bundled JSON
    const fleetScan = await runFleetScan(snapshotId);
    if (sequence !== loadSequence.current) return;
    if (fleetScan) {
      setScan(fleetScan);
      setFallback(false);
      // Open on the vessel the signature was found near, so the panel is never
      // empty on a pass that detected something.
      const params = new URLSearchParams(location.search);
      const detection = fleetScan.spills?.find((sp: SpillEntry) => sp.spill.ship_id === params.get("detection")) ?? fleetScan.spills?.[0];
      setFocusedSpillId(detection?.spill.ship_id ?? null);
      const selectedId = params.get("vessel") ?? detection?.candidates?.[0]?.ship_id ?? fleetScan.detections?.[0]?.id;
      setSelected(fleetScan.fleet.find((f: Ship) => f.id === selectedId) ?? null);
      setRunning(false);
      return;
    }
    // The stored completed case nests its fields differently to a fleet scan, so
    // normalise it here rather than teaching every panel two shapes.
    const stored = await getInvestigation();
    if (sequence !== loadSequence.current) return;
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
          image_url: det.image_url,
        } : null,
        age: stored.source?.hours_backward != null
          ? {estimated_hours: stored.source.hours_backward, release_at: null}
          : null,
        affected_area: null,   // no envelope in the stored payload; do not invent one
        candidates: cands.map((c: Candidate) => ({...c, name: c.name ?? `MMSI ${c.mmsi}`, in_fleet: true})),
        ais: stored.ais,
      });
      setFallback(true);
      setRunning(false);
      return;
    }
    setError("Backend unreachable and no bundled result available.");
    setRunning(false);
  };

  // Full-size map opened in its own tab reads the pass to show from the URL
  // (?view=map&snapshot=t3), rather than sharing state with the tab it came from.
  const [snapshotTimes, setSnapshotTimes] = useState<Record<string, string>>({});
  useEffect(() => {let live = true; getFleetMetadata().then((data) => {if (live) setSnapshotTimes(data?.snapshot_times ?? {});}); return () => {live = false;};}, []);
  const [routeSearch, setRouteSearch] = useState(() => location.search);
  const isFullMap = new URLSearchParams(routeSearch).get("view") === "map";
  const routeSnapshot = new URLSearchParams(routeSearch).get("snapshot") || undefined;
  useEffect(() => {
    const sync = () => setRouteSearch(location.search);
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  useEffect(() => { load(routeSnapshot); }, [routeSnapshot]);
  const changeSnapshot = (snapshot: string) => {
    if (snapshot === scan?.snapshot_id) return;
    const url = new URL(location.href); url.searchParams.set("snapshot", snapshot);
    history.pushState({...history.state, oiltracePanel: false}, "", url);
    setRouteSearch(url.search);
  };

  const fleet = scan?.fleet || [];
  const spill = scan?.spill;
  const source = scan?.source;
  const candidates = scan?.candidates || [];
  const forecast = scan?.forecast;
  const area = scan?.affected_area;
  const detected = scan?.status === "SPILL_DETECTED";

  // Each flagged vessel carries its own spill findings.
  const spillFor = (ship: Ship | null) =>
    ship ? (scan?.spills || []).find((sp: SpillEntry) => sp.spill?.ship_id === ship.id) : undefined;
  const sel = spillFor(selected);
  // Map overlays follow the explicitly focused spill; otherwise the selected
  // vessel's own spill, otherwise the strongest detection.
  const shown = (scan?.spills || []).find((sp: SpillEntry) => sp.spill?.ship_id === focusedSpillId)
    || sel || (scan?.spills || [])[0];
  const shownSpill = shown?.spill ?? spill;
  const shownSource = shown?.source ?? source;
  const shownSourceHeatmap = shown?.source_heatmap ?? scan?.source_heatmap;
  const shownForecastHeatmap = shown?.forecast_heatmap ?? scan?.forecast_heatmap;
  const shownArea = shown?.affected_area ?? area;
  const shownForecast = shown?.forecast ?? forecast;
  const shownCandidates = shown?.candidates ?? candidates;
  const shownAis = shown?.ais ?? scan?.ais;
  // The backend owns the weighting; the panel only displays it. Falling back to
  // the documented 0.40/0.30/0.30 keeps the breakdown renderable against the
  // stored case, which carries no weights block.
  const weights = shownAis?.weights ?? {proximity: 0.4, trajectory: 0.3, behaviour: 0.3};
  const rankByMmsi = useMemo(
    () => Object.fromEntries(shownCandidates.map((c: Candidate) => [c.mmsi, c])),
    [shownCandidates]
  );
  // Surfaced rather than reworded: the scan already asserts this.
  // The report describes the spill currently in view. Without this it always
  // described spills[0], which is wrong the moment a pass has two detections.
  const allSpills = scan?.spills || [];
  const shownSpillIndex = allSpills.findIndex(
    (sp: SpillEntry) => sp.spill?.ship_id === shownSpill?.ship_id
  );

  const view = useMemo(() => (scan ? fleetViewport(scan) : null), [scan]);
  const envelope = detected && shownSpill && shownArea?.radius_km
    ? ring(shownSpill.latitude, shownSpill.longitude, shownArea.radius_km) : null;

  // FORWARD RISK — which vessels are projected to enter the spill area next.
  // Kept separate from `candidates` (attribution: who may have caused it,
  // from historic AIS). This looks forward from each vessel's current AIS fix.
  // One fleet-wide list, so a vessel's detour is reachable no matter which
  // spill is focused.
  const shownRisk = scan?.risk_overview;
  const riskByShipId = useMemo(
    () => Object.fromEntries((shownRisk?.at_risk || []).map((r: RiskEntry) => [r.ship_id, r])),
    [shownRisk]
  );
  const selectedRisk = selected ? riskByShipId[selected.id] : undefined;
  // Selecting an at-risk vessel shows its detour immediately — no extra click.
  // Its original (projected) path is drawn unconditionally by MapView already;
  // this is the piece that used to require a separate "Show route" press.
  const rerouteOnSelect = (shipId: string) => riskByShipId[shipId]?.detour ? shipId : null;


  const whatIfKey = (spillShipId: string, mmsi: number) => `${spillShipId}:${mmsi}`;
  const shownWhatIf = (shownSpill?.ship_id && selected?.mmsi)
    ? whatIf[whatIfKey(shownSpill.ship_id, selected.mmsi)] : null;

  // Counterfactuals actually run for the detection the report covers, keyed by
  // MMSI. Only tests that were run are included, and every one of them is —
  // omitting a result that cleared a vessel would make the report a case for
  // the prosecution rather than a record of what was checked.
  const reportCounterfactuals = useMemo(() => {
    const out: Record<number, any> = {};
    if (!shownSpill?.ship_id) return out;
    for (const c of shownCandidates) {
      const r = whatIf[whatIfKey(shownSpill.ship_id, c.mmsi)];
      if (r) out[c.mmsi] = r;
    }
    return out;
  }, [whatIf, shownCandidates, shownSpill?.ship_id]);

  // The reroute goes in the report only if someone actually asked for one.
  const reportReroute = useMemo(() => {
    if (!rerouteFor) return null;
    const ship = fleet.find((f: Ship) => f.id === rerouteFor);
    const risk = shown?.risk?.at_risk.find((risk) => risk.ship_id === rerouteFor);
    return ship && risk?.detour
      ? {ship, detour: risk.detour, entryMinutes: risk.estimated_entry_minutes}
      : null;
  }, [rerouteFor, fleet, shown?.risk]);

  /** Run the counterfactual for one candidate against the spill in view. */
  const askWhatIf = async (c: Candidate) => {
    const sp = shown;
    if (!sp?.spill || !sp?.age?.release_at) return;
    const key = whatIfKey(sp.spill.ship_id, c.mmsi);
    setWhatIfBusy(key);
    const res = await runCounterfactual({
      mmsi: c.mmsi,
      release_at: sp.age.release_at,
      spill_latitude: sp.spill.latitude,
      spill_longitude: sp.spill.longitude,
      age_hours: sp.age.estimated_hours,
      // Context only. The backend derives its own threshold from the drift each
      // mode uses — it used to be handed this circle, which is sized by a
      // different vector than the one the test drifts with.
      affected_area_radius_km: sp.affected_area?.radius_km ?? null,
      source_latitude: sp.source?.latitude ?? null,
      source_longitude: sp.source?.longitude ?? null,
    });
    setWhatIf((prev) => ({...prev, [key]: res ?? {available: false,
      reason: "The counterfactual could not be run — the backend is unreachable."}}));
    setWhatIfBusy(null);
  };

  // Candidate AIS tracks, joined from the fleet roster: a candidate carries its
  // ship_id but not its track, and every candidate is in_fleet. The selected
  // vessel is excluded — its own track is already drawn, darker, on top.
  const candidateTracks = useMemo(() => {
    return shownCandidates.flatMap((c: Candidate) => {
      if (c.ship_id === selected?.id) return [];
      const ship = fleet.find((f: Ship) => f.id === c.ship_id);
      // AIS track points are {lat, lon} — unlike projected_track and forecast
      // points, which use latitude/longitude. Mixing them up yields an empty
      // array and no polyline, silently.
      const pts = (ship?.track || [])
        .filter((p: TrackFix) => typeof p.lat === "number")
        .map((p: TrackFix) => [p.lat, p.lon] as [number, number]);
      return pts.length > 1 ? [{...c, points: pts}] : [];
    });
  }, [shownCandidates, fleet, selected?.id]);


  const timeline = useMemo(() => {
    if (!shown?.age?.release_at || !scan?.observed_at) return null;
    const observedAt = Date.parse(scan.observed_at);
    const releaseAt = Date.parse(shown.age.release_at);
    const maxAhead = Math.max(0, ...(shown.forecast?.points ?? []).map((p) => p.hours_ahead));
    if (!Number.isFinite(observedAt) || !Number.isFinite(releaseAt)) return null;
    const passes = (scan.available_snapshots ?? []).flatMap((id) => {
      const time = snapshotTimes[id]; const at = time ? Date.parse(time) : NaN;
      return Number.isFinite(at) && at <= observedAt ? [{id, at}] : [];
    });
    return {start: Math.min(releaseAt, observedAt, ...passes.map((p) => p.at)), end: observedAt + maxAhead * HOUR_MS,
      observedAt, releaseAt, maxAhead, passes};
  }, [shown, scan?.observed_at, snapshotTimes]);
  useEffect(() => { setPlaying(false); setReplayT(null); }, [shownSpill?.ship_id]);
  useEffect(() => {
    if (!playing || !timeline) return;
    const timer = window.setInterval(() => setReplayT((previous) => {
      const next = (previous ?? timeline.start) + (timeline.end - timeline.start) / 300;
      return Math.min(timeline.end, next);
    }), 100);
    return () => clearInterval(timer);
  }, [playing, timeline]);
  useEffect(() => { if (timeline && replayT != null && replayT >= timeline.end) setPlaying(false); }, [replayT, timeline]);
  const replayFrame = useMemo((): ReplayFrame | null => {
    if (!timeline || replayT == null || !shown) return null;
    const dwell = Math.max(60_000, (timeline.end - timeline.start) / 600);
    return {t: replayT, slick: slickAt(shown, replayT, timeline.observedAt, dwell),
      vessels: fleet.map((sh) => ({sh, at: vesselAt(sh, replayT, shown.risk?.forecast_horizon_hours ?? 6)})),
      band: Math.abs(replayT - timeline.observedAt) <= dwell ? "observed" : replayT < timeline.releaseAt ? "before" : replayT < timeline.observedAt ? "estimated" : "projected"};
  }, [replayT, timeline, shown, fleet]);
  const selectCandidate = (c: Candidate) => {
    setFocusedSpillId(shownSpill?.ship_id ?? null);
    setEvidenceMmsi(c.mmsi);
    setSelected(fleet.find((f) => f.id === c.ship_id) ?? null);
    setRerouteFor(rerouteOnSelect(c.ship_id));
  };
  const top = shownCandidates[0];
  const evidenceCandidate = selected
    ? shownCandidates.find((c) => c.ship_id === selected.id || c.mmsi === selected.mmsi)
    : shownCandidates.find((c) => c.mmsi === evidenceMmsi) ?? top;
  if (error && !scan) return <div className="loading">{error}<button onClick={() => load(routeSnapshot)}>Retry</button></div>;
  if (!scan) return <div className="loading">Loading OILTRACE AI…</div>;
  const incidentId = `OT-${scan.observed_at?.slice(0, 10).replace(/-/g, "") ?? "STORED"}-${Math.max(0, shownSpillIndex) + 1}`;
  const mapProps = {
    view, envelope, detected, shownSpill, spills: allSpills.map((entry) => entry.spill),
    onSelectSpill: (shipId: string) => {
      setFocusedSpillId(shipId);
      const ship = fleet.find((item: Ship) => item.id === shipId);
      if (ship) setSelected(ship);
      setRerouteFor(null);
    },
    shownArea, shownSource, source,
    showEnvelope, onToggleEnvelope: () => setShowEnvelope((value) => !value),
    shownForecast, selectedRisk, selected, setSelected: (ship: Ship) => {
      setSelected(ship); setEvidenceMmsi(ship.mmsi);
      setFocusedSpillId(riskByShipId[ship.id]?.spill_ship_id ?? spillFor(ship)?.spill.ship_id ?? shownSpill?.ship_id ?? null);
      setRerouteFor(rerouteOnSelect(ship.id));
    }, fleet, riskByShipId, legendOpen, setLegendOpen,
    environment: scan.environment, showEnvironment, setShowEnvironment,
    sourceHeatmap: shownSourceHeatmap, showSourceHeatmap, setShowSourceHeatmap,
    environmentalSource: shown?.source_environmental,
    forecastHeatmap: shownForecastHeatmap, candidateTracks,
    showDetour: rerouteFor != null && rerouteFor === selected?.id,
    whatIfShown: shownWhatIf, replayFrame,
  };
  const fullMapUrl = new URL(location.href);
  fullMapUrl.hash = ""; fullMapUrl.searchParams.set("view", "map");
  if (scan.snapshot_id) fullMapUrl.searchParams.set("snapshot", scan.snapshot_id);
  if (shownSpill?.ship_id) fullMapUrl.searchParams.set("detection", shownSpill.ship_id);
  if (selected?.id) fullMapUrl.searchParams.set("vessel", selected.id);
  if (isFullMap) return <div className="app fullmap">
    <header className="topbar"><div className="brand"><Anchor size={22}/><div><b>OILTRACE AI</b><small>Maritime Forensics</small></div></div>
      <button className="reportbtn" onClick={() => {const url = new URL(location.href); url.searchParams.delete("view"); history.pushState({}, "", url); setRouteSearch(url.search);}}>Dashboard</button></header>
    <div className="mapfill"><MapView {...mapProps} mapStyle={{height: "100%", width: "100%"}} /></div>
  </div>;

  const routeShown = !!(selectedRisk?.detour && rerouteFor === selected?.id);
  const topN = 5;

  return <div className="app workstation">
    <header className="topbar">
      <div className="brand"><div className="brandmark"><Anchor size={21}/></div><div><b>OILTRACE AI</b><small>Maritime Forensics</small></div></div>
      <div className="incident-id">Incident #{incidentId}</div>
      <nav className="incident" aria-label="Investigation">
        <button className="reportbtn" onClick={() => openPanel("method")}>How this was derived</button>
        <ModelInfoButton onClick={() => openPanel("models")} />
        <button className="reportbtn openreport" onClick={() => openPanel("report")}><FileText size={14}/> Report</button>
      </nav>
    </header>

    {/* One-line verdict, large and unmistakable — red only when the model actually found oil. */}
    <div className={`alertbar${detected ? "" : " ok"}`}>
      {detected ? <AlertTriangle size={22}/> : <Check size={22}/>}
      <b>{detected ? "OIL SPILL DETECTED" : "NO OIL DETECTED"}</b>
      <span>{scan.message}</span>
    </div>

    <main className="layout">
      {/* ---------------- left: fleet + forecast ---------------- */}
      <aside className="left">
        <Card>
          <div className="eyebrow">MONITORED FLEET<span className="eyebrowright">{running ? "scanning…" : `${fleet.length} vessels`}</span></div>
          <PassControls ids={scan.available_snapshots ?? []} current={scan.snapshot_id} times={snapshotTimes} busy={running} onChange={changeSnapshot}/>
          <PassUploader existing={scan.available_snapshots ?? []} busy={running}
            onCreated={(id) => changeSnapshot(id)}
            onDeleted={(id) => {const next = scan.available_snapshots?.filter((sid) => sid !== id).slice(-1)[0]; if (id === scan.snapshot_id && next && next !== routeSnapshot) changeSnapshot(next); else load(routeSnapshot);}}/>
          <div className="candidates">
            {fleet.length ? fleet.map((s) => <button key={s.id} className={`candidate${selected?.id === s.id ? " selected" : ""}`}
                onClick={() => {setSelected(s); setEvidenceMmsi(s.mmsi); setRerouteFor(rerouteOnSelect(s.id)); setFocusedSpillId(shownSpill?.ship_id ?? null);}}>
              <div className="rank"><i className="dot" style={{background: s.oil_detected ? C.spillFill : C.vesselFill}}/></div>
              <div className="cv"><b>{s.name}</b><small>{s.vessel_type} · {fmt(s.speed_kt)} kt</small></div>
              <strong style={{color: s.oil_detected ? "var(--danger)" : "var(--ink-mute)"}}>{s.confidence ? showPct(s.confidence, 0) : "—"}</strong>
            </button>) : <div className="empty">Fleet data unavailable in this mode.</div>}
          </div>
        </Card>

        {sel && (sel.forecast?.points?.length ?? 0) > 0 && <Card>
          <div className="eyebrow">WHERE THIS OIL GOES NEXT<Badge tone="amber">KINEMATIC</Badge></div>
          <div className="cardsub">From {selected?.name}</div>
          <div className="metrics tight">
            {(sel.forecast?.points || []).map((p: ForecastPoint) => <div key={p.hours_ahead}>
              <small>+{p.hours_ahead} h</small><b className="md">{p.latitude.toFixed(3)}, {p.longitude.toFixed(3)}</b>
            </div>)}
          </div>
        </Card>}
      </aside>

      {/* ---------------- map ---------------- */}
      <section className="mapwrap">
        <div className="maphead">
          <div><span className="eyebrow">MONITORING MAP</span><h1>{scan.region || "Monitoring area"}</h1>
            <div className="subtle">{scan.observed_at ? `${String(scan.snapshot_id).toUpperCase()} · ${scan.observed_at.slice(0, 16).replace("T", " ")} UTC` : "Stored result"}</div></div>
          <div className="maptools">
            {detected ? <><Badge tone="red">SPILL</Badge><Badge tone="amber">SOURCE ESTIMATE</Badge></> : <Badge tone="blue">ALL CLEAR</Badge>}
            <a className="icon-button" title="Open full map" aria-label="Open full map" target="_blank" rel="noreferrer" href={fullMapUrl.toString()}><ExternalLink size={15}/></a>
          </div>
        </div>
        <MapView {...mapProps}/>
        {running && <div className="scanning" role="status"><span className="spinner"/>Analysing imagery…</div>}
      </section>

      {/* ---------------- right: the selected vessel, and its route if it's at risk ---------------- */}
      <VesselDetail selected={selected} sel={sel} selectedRisk={selectedRisk} scan={scan} rankByMmsi={rankByMmsi}
        routeShown={routeShown} onToggleRoute={() => {if (!selected) return; setRerouteFor(routeShown ? null : selected.id); setPlaying(false); setReplayT(null);}}
        environment={scan.environment}/>
    </main>

    <div className="below-main">
    {/* ---------------- replay: its own slot, not squeezed into the map card ---------------- */}
    <ReplayBar detected={detected} timeline={timeline} replayOn={replayT != null} replayT={replayT} setReplayT={setReplayT} playing={playing} setPlaying={setPlaying} replayFrame={replayFrame}/>

    {/* ---------------- attribution: who was near the estimated source ---------------- */}
    {detected && <Card>
      <div className="eyebrow">TOP CANDIDATES<span className="eyebrowright">{shownCandidates.length} in range</span></div>
      <p className="reportnote">AIS-only correlation — no independent SAR vessel detection is connected.</p>
      <CandidateList candidates={shownCandidates.slice(0, topN)} selectedId={evidenceCandidate?.ship_id} onSelect={selectCandidate}/>
      {shownCandidates.length > topN && <button className="view-all-button" onClick={() => openPanel("candidates")}>View all {shownCandidates.length} candidates</button>}
      {evidenceCandidate && <>
        <EvidencePanel candidate={evidenceCandidate} entry={shown} weights={weights}/>
        <button className="reportbtn" disabled={whatIfBusy != null || !shown?.age?.release_at} onClick={() => askWhatIf(evidenceCandidate)}>
          {whatIfBusy ? "Testing…" : "Test source consistency"}
        </button>
        {whatIf[whatIfKey(shownSpill?.ship_id ?? "", evidenceCandidate.mmsi)] && <p className="compact-result">
          {(() => {const t = whatIf[whatIfKey(shownSpill?.ship_id ?? "", evidenceCandidate.mmsi)]; return t.available ? `${t.within_envelope ? "Consistent" : "Not consistent"} · miss ${fmt(t.miss_distance_km, 2)} km` : "Test unavailable";})()}
        </p>}
      </>}
    </Card>}

    {/* ---------------- response: which spill first, and what to do ---------------- */}
    {detected && (allSpills.length > 1 && (scan.response_priorities?.length ?? 0) > 0
      ? <ResponsePriorityStrip priorities={scan.response_priorities || []} spills={allSpills} selected={selected}
          onSelect={(shipId) => {setFocusedSpillId(shipId); setSelected(fleet.find((f) => f.id === shipId) ?? null); setRerouteFor(rerouteOnSelect(shipId));}}/>
      : <Card>
          <div className="eyebrow">RESPONSE</div>
          <div className="response-task"><span className="data-tag">{shown?.response_priority ?? "REVIEW"} · {shown?.response?.urgency ?? "INVESTIGATE"}</span>
            <p>{shown?.response?.action ?? "Verify the detection and notify the relevant maritime authority."}</p></div>
          <GovernmentActions topCandidate={top?.name} urgency={shown?.response?.urgency}/>
        </Card>)}

    {/* ---------------- environmental & human impact: honest about what isn't measured ---------------- */}
    {detected && <Card>
      <div className="eyebrow">ENVIRONMENTAL & HUMAN IMPACT</div>
      <div className="metrics">
        <div><small>Potential envelope</small><b>{fmt(area?.radius_km, 2)} km radius · {fmt(area?.area_km2, 1)} km²</b></div>
        <div><small>Centred on</small><b>{spill ? `${fmt(spill.latitude, 3)}, ${fmt(spill.longitude, 3)}` : NOT_AVAILABLE}</b></div>
      </div>
      <div className="impact-checklist">
        <div><Fish size={17}/><div><b>Fishing &amp; aquaculture</b><span>Active fishing grounds and licensed aquaculture sites inside the envelope.</span></div></div>
        <div><Leaf size={17}/><div><b>Protected areas &amp; wildlife</b><span>Marine protected areas, nesting sites, and any threatened-species range.</span></div></div>
        <div><Users size={17}/><div><b>Coastal communities</b><span>Drinking-water intakes and livelihoods that depend on these waters.</span></div></div>
        <div><Waves size={17}/><div><b>Tourism &amp; recreation</b><span>Beaches, dive sites and recreational waters that may need closure.</span></div></div>
      </div>
    </Card>}

    {/* ---------------- forward risk: vessels projected to enter the spill, and their reroute ---------------- */}
    {detected && shownRisk && <VesselsAtRiskStrip risk={shown?.risk} selected={selected} selectedRisk={selectedRisk}
      rerouteFor={rerouteFor} setRerouteFor={(id) => {setRerouteFor(id); setPlaying(false); setReplayT(null);}}
      onSelect={(shipId, spillShipId) => {setFocusedSpillId(spillShipId ?? null); setSelected(fleet.find((f) => f.id === shipId) ?? null); setRerouteFor(rerouteOnSelect(shipId));}}/>}
    </div>


    <footer className="workstation-footer">
      <span>Attribution score is an investigation aid, not a legal determination of responsibility.</span>
      <span>{fallback ? "Stored result" : scan.traffic?.co_presence === "constructed" ? "Recorded AIS · aligned scenario" : "SAR + AIS"}{scan.ais_currency?.stale ? " · AIS delayed" : ""}</span>
    </footer>

    {panel === "candidates" && <ModalFrame title={`All ${shownCandidates.length} candidates`} onClose={closePanel}>
      <CandidateList candidates={shownCandidates} selectedId={evidenceCandidate?.ship_id} onSelect={(c) => {selectCandidate(c); closePanel();}}/></ModalFrame>}
    {panel === "method" && <FlowModal onClose={closePanel} spillName={shownSpill?.ship_name}/>}
    {panel === "models" && <ModelInfoModal onClose={closePanel}/>}
    {panel === "report" && <ReportModal scan={scan} detected={detected} onClose={closePanel} entry={shown} index={shownSpillIndex} total={allSpills.length} candidates={shownCandidates} weights={weights} counterfactuals={reportCounterfactuals} reroute={reportReroute} risk={shown?.risk}/>}
  </div>;
}

export default App;
