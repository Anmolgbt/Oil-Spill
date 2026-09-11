import {useEffect, useMemo, useState} from "react";
import {AlertTriangle, Anchor, Check, ChevronRight, ExternalLink, FileText, Info, Pause, Play, X} from "lucide-react";
import {NOT_AVAILABLE, fleetViewport, getInvestigation, runCounterfactual, runFleetScan, show, showCoord, showPct} from "./lib/oiltrace";
import {HOUR_MS, REPLAY_MAX_AHEAD_H, clock, slickAt, vesselAt} from "./lib/replay";
import {Badge, Card, ScoreBar, fmt, ring} from "./ui";
import {MapView} from "./components/MapView";
import {ReportModal} from "./components/ReportModal";
import {WhyThisVessel} from "./components/WhyThisVessel";
import {InvestigationBar} from "./components/InvestigationBar";
import {FlowModal} from "./components/FlowModal";
import {EnvironmentStrip} from "./components/EnvironmentStrip";
import {DriftComparison} from "./components/DriftComparison";
import {DemoMode} from "./components/DemoMode";
import {ReplayBar} from "./components/ReplayBar";
import {VesselDetail} from "./components/VesselDetail";
import {ModelInfoButton, ModelInfoModal} from "./components/ModelInfoModal";
import {PassUploader} from "./components/PassUploader";
import {ResponsePriorityStrip} from "./components/ResponsePriorityStrip";
import {VesselsAtRiskStrip} from "./components/VesselsAtRiskStrip";
import type {ReplayFrame} from "./components/MapView";
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
 * The map, the stage definitions, the replay maths and the shared atoms live in
 * their own modules; what remains here is the dashboard's state and layout.
 */

const FALLBACK_CENTER: [number, number] = [28.55, -94.85];


function App() {
  const [scan, setScan] = useState<Scan | null>(null);
  const [running, setRunning] = useState(false);
  const [selected, setSelected] = useState<Ship | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [error, setError] = useState("");
  const [fallback, setFallback] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);
  // The drift field is context, not a finding, so it starts hidden.
  const [showEnvironment, setShowEnvironment] = useState(false);
  const [showSourceHeatmap, setShowSourceHeatmap] = useState(false);
  // A guided run for someone seeing this for the first time. ?demo=1 opens it
  // directly, so a walkthrough can be handed over as a link.
  const [demo, setDemo] = useState(
    () => new URLSearchParams(window.location.search).get("demo") === "1");
  // Which spill the map overlays follow. Separate from `selected` (the vessel
  // in the detail panel): selecting an at-risk vessel used to make the shown
  // spill fall back to spills[0], which silently swapped the at-risk list and
  // wiped the detour the user had just clicked in to see.
  const [focusedSpillId, setFocusedSpillId] = useState<string | null>(null);
  const [flowOpen, setFlowOpen] = useState(false);
  const [modelInfoOpen, setModelInfoOpen] = useState(false);
  // Which vessel's detour has been explicitly asked for. The backend computes a
  // detour for every at-risk vessel on every scan, but a route change is an
  // action someone takes, not a fact about the sea — so it stays off the map
  // until requested.
  const [rerouteFor, setRerouteFor] = useState<string | null>(null);
  // Counterfactual results, keyed `${spillShipId}:${mmsi}` so testing a vessel
  // against one spill does not overwrite its result against the other.
  const [whatIf, setWhatIf] = useState<Record<string, any>>({});
  const [whatIfBusy, setWhatIfBusy] = useState<string | null>(null);
  // REPLAY. `replayT` is null when the replay is off and the dashboard shows
  // the pass as scanned; a number puts the map under the timeline's control.
  const [replayT, setReplayT] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);

  const load = async (snapshotId?: string) => {
    setRunning(true);
    setError("");
    setSelected(null);
    setFocusedSpillId(null);
    setRerouteFor(null);
    setWhatIf({});
    setReplayT(null);
    setPlaying(false);

    // 1. live fleet scan  2. stored completed case  3. bundled JSON
    const fleetScan = await runFleetScan(snapshotId);
    if (fleetScan) {
      setScan(fleetScan);
      setFallback(false);
      // Open on the vessel the signature was found near, so the panel is never
      // empty on a pass that detected something.
      const top = fleetScan.detections?.[0];
      if (top) setSelected(fleetScan.fleet.find((f: Ship) => f.id === top.id) ?? top);
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
  const isFullMap = new URLSearchParams(window.location.search).get("view") === "map";
  useEffect(() => {
    const snapshot = new URLSearchParams(window.location.search).get("snapshot") || undefined;
    load(snapshot);
  }, []);

  const fleet = scan?.fleet || [];
  const spill = scan?.spill;
  const source = scan?.source;
  const candidates = scan?.candidates || [];
  const forecast = scan?.forecast;
  const age = scan?.age;
  const area = scan?.affected_area;
  const detected = scan?.status === "SPILL_DETECTED";

  const rankByMmsi = useMemo(
    () => Object.fromEntries(candidates.map((c: Candidate) => [c.mmsi, c])),
    [candidates]
  );

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
  const shownAge = shown?.age ?? age;
  const shownCandidates = shown?.candidates ?? candidates;
  const shownAis = shown?.ais ?? scan?.ais;
  // The backend owns the weighting; the panel only displays it. Falling back to
  // the documented 0.40/0.30/0.30 keeps the breakdown renderable against the
  // stored case, which carries no weights block.
  const weights = shownAis?.weights ?? {proximity: 0.4, trajectory: 0.3, behaviour: 0.3};
  // Surfaced rather than reworded: the scan already asserts this.
  const causationProven = scan?.interpretation?.vessel_causation_proven;
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
    const risk = riskByShipId[rerouteFor];
    return ship && risk?.detour
      ? {ship, detour: risk.detour, entryMinutes: risk.estimated_entry_minutes}
      : null;
  }, [rerouteFor, fleet, riskByShipId]);

  /* ---- replay timeline ------------------------------------------------- */

  // Pass times are derived from the newest pass and the stated revisit
  // interval; the scan does not carry a snapshot_times block.
  const timeline = useMemo(() => {
    if (!scan?.observed_at || !detected) return null;
    const observedAt = Date.parse(scan.observed_at);
    if (Number.isNaN(observedAt)) return null;
    const intervalH = scan.pass_interval_hours || 4;
    const ids: string[] = scan.available_snapshots || [];
    // Shape of one tick on the replay scrubber, inferred rather than declared
    // twice: the map below is the only producer.
    const passes = ids.map((id, i) => ({
      id,
      at: observedAt - (ids.length - 1 - i) * intervalH * HOUR_MS,
    }));
    // Cap the forecast tail. The full +48 h horizon makes a 56 h timeline in
    // which the observed window (t1 to t3) is 14% of the scrubber and almost
    // every position reads "projected" — the replay would spend most of its
    // length showing a straight line nobody measured. The far horizons are
    // already given numerically in WHERE THIS OIL GOES NEXT; the replay is
    // about the incident, so it stops at the nearest forecast point beyond
    // REPLAY_MAX_AHEAD_H.
    const ahead = (shown?.forecast?.points || []).map((p: ForecastPoint) => p.hours_ahead || 0);
    const within = ahead.filter((h: number) => h <= REPLAY_MAX_AHEAD_H);
    const maxAhead = within.length ? Math.max(...within)
                                   : (ahead.length ? Math.min(...ahead) : 0);
    const releaseAt = shown?.age?.release_at ? Date.parse(shown.age.release_at) : observedAt;
    return {
      start: passes.length ? passes[0].at : observedAt,
      end: observedAt + maxAhead * HOUR_MS,
      observedAt, releaseAt, passes,
      maxAhead,
      horizonHours: scan.risk_overview?.forecast_horizon_hours || 6,
    };
  }, [scan, detected, shown]);

  const replayOn = replayT != null && timeline != null;

  // What the replay says about the moment on screen. The observed/projected
  // boundary is the point of the whole feature, so it is computed once here
  // and every consumer reads the same answer.
  const replayFrame = useMemo((): ReplayFrame | null => {
    if (!replayOn || !timeline) return null;
    const t = replayT as number;
    const dwell = Math.max(5 * 60_000, (timeline.end - timeline.start) / 100);
    const atPass = Math.abs(t - timeline.observedAt) <= dwell;
    return {
      t,
      slick: shown ? slickAt(shown, t, timeline.observedAt, dwell) : null,
      vessels: fleet.map((sh: Ship) => ({sh, at: vesselAt(sh, t, timeline.horizonHours)})),
      band: atPass
        ? "observed"
        : t < timeline.observedAt
          ? (t < timeline.releaseAt ? "before" : "estimated")
          : "projected",
    };
  }, [replayOn, replayT, timeline, shown, fleet]);

  // Playback. Compresses the whole span into roughly half a minute; the step
  // is coarser under prefers-reduced-motion, which trades smoothness for far
  // fewer visual updates rather than removing the feature.
  useEffect(() => {
    if (!playing || !timeline) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const tickMs = reduced ? 500 : 100;
    const span = timeline.end - timeline.start;
    const perTick = span / (30_000 / tickMs);
    const id = window.setInterval(() => {
      setReplayT((prev) => {
        const next = (prev ?? timeline.start) + perTick;
        if (next >= timeline.end) { setPlaying(false); return timeline.end; }
        return next;
      });
    }, tickMs);
    return () => window.clearInterval(id);
  }, [playing, timeline]);

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


  // Order matters, and the pair used to be `!scan && !error` followed by
  // `error` — which left a path where an error arrived WITH no scan and fell
  // through to a render that dereferences scan. Typing scan as Scan | null is
  // what surfaced it. Error first, then absence, so what follows is narrowed.
  if (error) return <div className="loading">{error}</div>;
  if (!scan) return <div className="loading">Loading OILTRACE…</div>;

  const mode = fallback ? "STORED RESULT" : "LIVE INFERENCE";

  // Full-size map tab: just the map, filling the window, plus a thin header
  // so the pass and vessel count are still visible without the docked panels.
  if (isFullMap) {
    return (
      <div className="app fullmap">
        <header className="topbar">
          <div className="brand">
            <div className="brandmark"><Anchor size={18} /></div>
            <div><b>OILTRACE</b><small>MAP · PASS {scan.snapshot_id ? String(scan.snapshot_id).toUpperCase() : "—"}</small></div>
          </div>
          <div className="incident">
            <Badge tone={fallback ? "amber" : "blue"}>{mode}</Badge>
            <span className="subtle">{fleet.length} vessels{detected ? " · spill detected" : " · all clear"}</span>
          </div>
        </header>
        <div className="mapfill">
          <MapView view={view} envelope={envelope} detected={detected} shownSpill={shownSpill}
                    shownArea={shownArea} shownSource={shownSource} source={source}
                    shownForecast={shownForecast} selectedRisk={selectedRisk} selected={selected}
                    setSelected={setSelected} fleet={fleet} riskByShipId={riskByShipId}
                    legendOpen={legendOpen} setLegendOpen={setLegendOpen}
                    environment={scan.environment} showEnvironment={showEnvironment}
                    setShowEnvironment={setShowEnvironment}
                    sourceHeatmap={shownSourceHeatmap} showSourceHeatmap={showSourceHeatmap}
                    setShowSourceHeatmap={setShowSourceHeatmap}
                    forecastHeatmap={shownForecastHeatmap}
                    candidateTracks={candidateTracks}
                    mapStyle={{height: "100%", width: "100%"}} />
        </div>
      </div>
    );
  }

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
          <button className="reportbtn demobtn" onClick={() => setDemo((v) => !v)}
                  title="Walk through the investigation step by step">
            <Play size={14} /> {demo ? "END DEMO" : "DEMO"}
          </button>
          <ModelInfoButton onClick={() => setModelInfoOpen(true)} />
          {/* Distinct class: three header buttons now share .reportbtn's styling,
              and "the one that opens the report" needs to be nameable. */}
          <button className="reportbtn openreport" onClick={() => setReportOpen(true)}
                  title="Open the monitoring report">
            <FileText size={14} /> Report
          </button>
        </div>
      </header>

      {/* An uploaded pass runs past where the AIS corpus ends, so the vessel
          positions behind every forward figure are older than the pass. Said
          plainly, because the numbers themselves do not show it. */}
      {scan.ais_currency?.stale && (
        <div className="stalebar">
          <Info size={15} />
          <span>
            <b>AIS is {fmt(scan.ais_currency.newest_fix_lag_hours, 1)} h behind this pass.</b>{" "}
            Vessel positions, entry times and detours are computed from the newest fix
            before it, not from where the vessels are now.
          </span>
        </div>
      )}

      {/* One-line verdict. Red only when the model actually found oil. */}
      <div data-demo="detection" className={"alertbar" + (detected ? "" : " ok")}>
        {detected ? <AlertTriangle size={16} /> : <Check size={16} />}
        <b>{detected ? "OIL SPILL DETECTED" : "NO OIL DETECTED"}</b>
        <span>{scan.message}</span>
      </div>

      {detected && (
        <InvestigationBar spillName={shownSpill?.ship_name}
                          candidateCount={shownCandidates.length}
                          ageHours={shownAge?.estimated_hours}
                          onOpenFlow={() => setFlowOpen(true)} />
      )}

      <main className="layout">
        {/* ---------------- left: fleet + forecast ---------------- */}
        <aside className="left">
          <Card>
            <div className="eyebrow">
              MONITORED FLEET
              <span className="eyebrowright">
                {running ? "scanning…" : `${fleet.length} vessels`}
              </span>
            </div>
            {!demo && (scan.available_snapshots || []).length > 1 && (
              <div className="timebar spaced">
                <b>PASS</b>
                {(scan.available_snapshots ?? []).map((sid: string) => (
                  <button key={sid} className={scan.snapshot_id === sid ? "sel" : ""}
                          disabled={running} onClick={() => load(sid)}>
                    {sid.toUpperCase()}
                  </button>
                ))}
              </div>
            )}

            {/* Live input: drop tiles in and they become the next pass, which
                is scanned as soon as it is written. */}
            {!demo && <PassUploader
              existing={scan.available_snapshots || []}
              busy={running}
              onCreated={(sid) => load(sid)}
              onDeleted={() => load(scan.snapshot_id ?? undefined)}
            />}
            <div className="candidates">
              {fleet.length ? fleet.map((s: Ship) => (
                <button key={s.id}
                        className={"candidate " + (selected?.id === s.id ? "selected" : "")}
                        onClick={() => setSelected(s)}>
                  <div className="rank">
                    {/* Computed from state; a class per case would be worse. */}
                    <i className="dot" style={{background: s.oil_detected ? C.spillFill : C.vesselFill}} />
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

          {/* Forecast belongs to a specific spill, so it shows only for a flagged
              vessel — and only once the investigation that justifies it has run. */}
          {sel && (
            <Card dataDemo="forecast">
              <div className="eyebrow">
                WHERE THIS OIL GOES NEXT <Badge tone="amber">KINEMATIC</Badge>
              </div>
              <div className="cardsub">
                From {selected?.name}
              </div>
              <div className="metrics tight">
                {(sel.forecast?.points || []).map((p: ForecastPoint) => (
                  <div key={p.hours_ahead}>
                    <small>+{p.hours_ahead} h</small>
                    <b className="md">{showCoord(p.latitude, 3)}, {showCoord(p.longitude, 3)}</b>
                  </div>
                ))}
              </div>
              <div className="cardnote">
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
                ? <><Badge tone="red">SPILL</Badge>
                    <Badge tone="amber">SOURCE ESTIMATE</Badge></>
                : <Badge tone="blue">ALL CLEAR</Badge>}
              <button className="reportbtn" title="Open the map full-size in a new tab"
                      onClick={() => window.open(
                        `${window.location.pathname}?view=map${scan.snapshot_id ? `&snapshot=${scan.snapshot_id}` : ""}`,
                        "_blank"
                      )}
>
                <ExternalLink size={13} /> Open map in new tab
              </button>
            </div>
          </div>

          <MapView view={view} envelope={envelope} detected={detected} shownSpill={shownSpill}
                    shownArea={shownArea} shownSource={shownSource} source={source}
                    shownForecast={shownForecast} selectedRisk={selectedRisk} selected={selected}
                    setSelected={setSelected} fleet={fleet} riskByShipId={riskByShipId}
                    legendOpen={legendOpen} setLegendOpen={setLegendOpen}
                    environment={scan.environment} showEnvironment={showEnvironment}
                    setShowEnvironment={setShowEnvironment}
                    sourceHeatmap={shownSourceHeatmap} showSourceHeatmap={showSourceHeatmap}
                    setShowSourceHeatmap={setShowSourceHeatmap}
                    forecastHeatmap={shownForecastHeatmap}
                    candidateTracks={candidateTracks}
                    showDetour={rerouteFor != null && rerouteFor === selected?.id}
                    whatIfShown={shownWhatIf} replayFrame={replayFrame} />

          {running && (
            <div className="scanning" role="status" aria-live="polite">
              <span className="spinner" />
              Running the CNN over every vessel in this pass…
            </div>
          )}

          <div className="mapbottom">
            {/* The conditions driving the impact envelope, with the backend's
                own account of whether they are measured or assumed. */}
            <EnvironmentStrip environment={scan.environment} />
          </div>

          <ReplayBar detected={detected} timeline={timeline}
                     replayOn={replayOn} replayT={replayT} setReplayT={setReplayT}
                     playing={playing} setPlaying={setPlaying}
                     replayFrame={replayFrame} />
        </section>

        <VesselDetail selected={selected} sel={sel} selectedRisk={selectedRisk}
                      scan={scan} rankByMmsi={rankByMmsi} />
      </main>
      {/* ---------------- attribution: who was near the estimated source ----------------
          Attribution comes before response, so this strip sits above
          RESPONSE PRIORITY. */}
      {/* What the drift assumption changes — including, on the first t3
          detection, which vessel ranks first. Above WHY THIS VESSEL because it
          frames the ranking that panel then explains. */}
      {detected && shown?.drift_divergence && (
        <DriftComparison divergence={shown.drift_divergence}
                         legacySource={shownSource}
                         environmentalSource={shown.source_environmental}
                         spillName={shownSpill?.ship_name} />
      )}

      {detected && (
        <WhyThisVessel
          evidence={shown?.evidence}
          shownSpill={shownSpill}
          shownAis={shownAis}
          candidates={shownCandidates}
          weights={weights}
          fleet={fleet}
          selected={selected}
          causationProven={causationProven}
          traffic={scan.traffic}
          whatIf={whatIf}
          whatIfBusy={whatIfBusy}
          whatIfKey={whatIfKey}
          askWhatIf={askWhatIf}
          onSelectCandidate={(c) => {
            // Pin the spill under examination first. Several candidates are
            // themselves flagged vessels, and without this, selecting one
            // silently re-focuses the strip onto that vessel's OWN spill — so
            // the counterfactual would answer a question about a different
            // detection than the one on screen.
            setFocusedSpillId(shownSpill?.ship_id ?? null);
            setSelected(fleet.find((f: Ship) => f.id === c.ship_id) ?? selected);
          }}
        />
      )}

      {/* ---------------- response: which spill first, and who goes ---------------- */}
      {detected && (scan.response_priorities || []).length > 0 && (
        <ResponsePriorityStrip
          priorities={scan.response_priorities || []}
          spills={allSpills}
          fleet={fleet}
          selected={selected}
          onSelect={(shipId) => {
            setFocusedSpillId(shipId);
            setSelected(fleet.find((f: Ship) => f.id === shipId) ?? null);
          }}
        />
      )}

      {/* ---------------- forward risk: vessels projected to enter the spill ---------------- */}
      {detected && shownRisk && (
        <VesselsAtRiskStrip
          risk={shown?.risk}
          fleet={fleet}
          selected={selected}
          selectedRisk={selectedRisk}
          rerouteFor={rerouteFor}
          setRerouteFor={setRerouteFor}
          onSelect={(shipId, spillShipId) => {
            setFocusedSpillId(spillShipId ?? null);
            setSelected(fleet.find((f: Ship) => f.id === shipId) ?? null);
          }}
        />
      )}

      {demo && (
        <DemoMode
          scan={scan}
          spills={allSpills}
          onExit={() => setDemo(false)}
          actions={{
            focusDetection: (n) => {
              const target = allSpills[n];
              if (target) setFocusedSpillId(target.spill.ship_id);
            },
            selectShip: (shipId) => {
              if (shipId) setSelected(fleet.find((f: Ship) => f.id === shipId) ?? null);
            },
            setShowEnvironment: (on) => setShowEnvironment(on),
            askWhatIfTop: () => {
              const c = shownCandidates[0];
              if (c && !whatIf[whatIfKey(shownSpill?.ship_id ?? "", c.mmsi)]) askWhatIf(c);
              if (c) setSelected(fleet.find((f: Ship) => f.id === c.ship_id) ?? null);
            },
            openReport: (open) => setReportOpen(open),
          }}
        />
      )}

      {modelInfoOpen && <ModelInfoModal onClose={() => setModelInfoOpen(false)} />}

      {flowOpen && (
        <FlowModal onClose={() => setFlowOpen(false)} spillName={shownSpill?.ship_name}
                   traffic={scan.traffic} />
      )}

      {reportOpen && (
        <ReportModal
          scan={scan}
          detected={detected}
          onClose={() => setReportOpen(false)}
          entry={shown}
          index={shownSpillIndex}
          total={allSpills.length}
          candidates={shownCandidates}
          weights={weights}
          counterfactuals={reportCounterfactuals}
          reroute={reportReroute}
          causationProven={causationProven}
          liveInference={scan.provenance?.live_inference}
          risk={shown?.risk}
        />
      )}
    </div>
  );
}

export default App;
