import {useState} from "react";
import {ArrowDownRight, ArrowUpRight, FileText, MapPin, Satellite, ShieldAlert} from "lucide-react";
import {fmt} from "../ui";
import {imageSource, showCoord, showPct} from "../lib/oiltrace";
import {CaseSection} from "./CaseSection";
import {EnvironmentVectors} from "./EnvironmentVectors";
import {SourceSpread} from "./SourceSpread";
import {PassControls} from "./PassControls";
import {CandidateList} from "./CandidateList";
import {EvidencePanel} from "./EvidencePanel";
import {CounterfactualLines} from "./CounterfactualLines";
import {GovernmentActions} from "./GovernmentActions";
import type {Candidate, Counterfactual, Scan, Ship, SpillEntry, Weights} from "../types";

const utc = (value?: string | null) => value ? value.replace("T", " ").replace("Z", " UTC") : "Not available";
const position = (lat?: number, lon?: number) => lat == null || lon == null ? "Not available" : `${showCoord(lat, 4)}°, ${showCoord(lon, 4)}°`;
function Fact({label, children}: {label: string; children: React.ReactNode}) {
  return <div className="case-fact"><small>{label}</small><b>{children}</b></div>;
}
function SatelliteTile({url}: {url?: string}) {
  const [failed, setFailed] = useState(false);
  return url && !failed ? <img src={url} alt="SAR image tile submitted to the oil classifier" onError={() => setFailed(true)}/> : <div className="image-unavailable"><Satellite size={26}/><span>Image unavailable</span></div>;
}
export interface IncidentCaseFileProps {
  scan: Scan; entry?: SpillEntry; candidate?: Candidate; candidates: Candidate[]; selected: Ship | null; weights: Weights;
  onSelect: (candidate: Candidate) => void; onOpenAll: () => void; onReport: () => void; onRouting: () => void;
  onFocusMap: () => void; onForecast: (hours: number) => void; onSnapshot: (id: string) => void;
  snapshotTimes: Record<string, string>; busy: boolean; test?: Counterfactual; testBusy: boolean; onTest: (candidate: Candidate) => void;
}
export function IncidentCaseFile({scan, entry, candidate: c, candidates, selected, weights, onSelect, onOpenAll, onReport, onRouting, onFocusMap, onForecast, onSnapshot, snapshotTimes, busy, test, testBusy, onTest}: IncidentCaseFileProps) {
  const detected = scan.status === "SPILL_DETECTED";
  const spill = entry?.spill ?? scan.spill;
  const source = entry?.source ?? scan.source;
  const area = entry?.affected_area ?? scan.affected_area;
  const age = entry?.age ?? scan.age;
  const env = scan.environment;
  const forecast = entry?.forecast ?? scan.forecast;
  const ship = scan.fleet.find((v) => v.id === spill?.ship_id) ?? selected ?? scan.fleet[0];
  const demo = scan.traffic?.co_presence === "constructed" || scan.provenance?.simulation_seed != null;
  const evidence = entry?.evidence?.candidates.find((e) => e.mmsi === c?.mmsi);
  const inspectedShip = scan.fleet.find((v) => v.id === c?.ship_id) ?? selected;
  const beats = evidence?.narrative?.beats ?? [];
  const support = beats.filter((beat) => beat.tone === "supports");
  const weaken = beats.filter((beat) => beat.tone === "weakens");
  const coverage = evidence?.streams.ais_coverage;
  const risk = entry?.risk;
  const observedImage = imageSource(spill?.image_url ?? ship?.image_url);
  const cf = evidence?.streams.counterfactual;
  return <div className="incident-casefile">
    <CaseSection id="satellite-observation" number="01" title="Satellite observation" question="What did the satellite see?" action={<span className="data-tag">{demo ? "DEMO SCENE ASSIGNMENT" : "SAR INPUT"}</span>}>
      <div className="observation-layout"><figure className="satellite-evidence"><SatelliteTile key={observedImage} url={observedImage}/><figcaption><span>{scan.snapshot_id?.toUpperCase() ?? "Stored tile"} · SAR image</span><span>Classifier input</span></figcaption></figure>
        <div className="observation-analysis"><div className="classification-line"><span className={`classification-symbol ${detected ? "oil" : "clear"}`}><Satellite size={20}/></span><div><small>CLASSIFICATION RESULT</small><h3>{detected ? "Oil-like signature detected" : "No oil classified"}</h3></div><strong>{showPct(spill?.confidence ?? ship?.confidence, 1)}</strong></div>
          <div className="case-facts"><Fact label={demo ? "Scenario observation time" : "Observation time"}>{utc(scan.observed_at)}</Fact><Fact label="Mapped position (AIS anchor)">{position(spill?.latitude ?? ship?.latitude, spill?.longitude ?? ship?.longitude)}</Fact><Fact label="Measured slick area">Not available · no segmentation</Fact><Fact label="Tile source">{scan.provenance?.sar_input?.source ?? "Source not supplied"}</Fact></div>
          <div className="analysis-note"><b>Oil / look-alike analysis</b><p>The CNN classifies the tile as oil or non-oil. A separate look-alike filter and spill boundary are not supplied; the classification needs scene verification.</p></div>
          {demo && <p className="provenance-note">Public SAR imagery is reused across vessels. This tile is scenario evidence, not a satellite capture of the named vessel.</p>}
        </div>
      </div>
      <details className="case-details"><summary>Acquisition & data provenance</summary><div className="case-facts"><Fact label="SAR provenance">{scan.provenance?.sar_input?.source ?? "Unavailable"}</Fact><Fact label="Geolocation">Vessel AIS fix · classifier does not geolocate</Fact><Fact label="Sensor acquisition timestamp">Not supplied with tile</Fact><Fact label="Scene coverage / oil volume">Not supplied</Fact></div><p>{scan.provenance?.sar_input?.note}</p></details>
    </CaseSection>

    {detected && <>
    <CaseSection id="source-reconstruction" number="02" title="Reconstructing the release" question="Where and when could the oil have originated?" action={<button className="text-button" onClick={onFocusMap}>Inspect on map <ArrowUpRight size={13}/></button>}>
      <p className="section-intro">The observed slick location may differ from its release location because wind and ocean currents can transport the oil.</p>
      <div className="source-layout"><div><div className="case-facts"><Fact label="Probable source · ranking basis">{position(source?.latitude, source?.longitude)}</Fact><Fact label="Release window (bounded estimate)">{age?.release_at && scan.observed_at ? `${age.release_at.slice(11, 16)}–${scan.observed_at.slice(11, 16)} UTC` : "Not available"}</Fact><Fact label="Maximum age">{age?.estimated_hours != null ? `${age.estimated_hours} h` : "Not available"}</Fact><Fact label="Source confidence">{source?.confidence == null ? "Not quantified" : showPct(source.confidence, 1)}</Fact></div>
        <div className="release-chain"><span>SAR location</span><ArrowDownRight size={17}/><span>{source?.hours_backward ?? "—"} h hindcast</span><ArrowDownRight size={17}/><span>Probable release</span></div>
        <PassControls ids={scan.available_snapshots ?? []} current={scan.snapshot_id} times={snapshotTimes} busy={busy} onChange={onSnapshot}/>
        <p className="provenance-note">T1 / T2 / T3 are the available satellite-pass scenarios. The release bound uses the revisit interval; it is not an observed discharge time.</p>
      </div><SourceSpread heatmap={entry?.source_heatmap ?? scan.source_heatmap} source={source} spill={spill ?? undefined}/></div>
      <details className="case-details"><summary>Hindcast method & reconstruction limits</summary><p>{source?.method ?? "Method not supplied"}.</p><div className="case-facts"><Fact label="Ranking hindcast">{fmt(source?.drift_speed_kmh, 2)} km/h · {fmt(source?.drift_direction_deg, 0)}°</Fact><Fact label="Environmental reconstruction">{position(entry?.source_environmental?.latitude, entry?.source_environmental?.longitude)}</Fact><Fact label="Integration step">{entry?.source_environmental?.step_minutes ?? "—"} minutes</Fact><Fact label="Source spread">{entry?.source_heatmap?.points.length ?? 0} existing assumption samples</Fact></div><p>The ranking uses the fixed-vector hindcast. Wind/current integration is a separate reconstruction; its path is available on the map.</p></details>
      <div className="environment-study"><div className="subsection-heading"><h3>Wind + current → drift</h3><span className="data-tag">{env?.environment_mode === "historical" ? "HISTORICAL INPUT" : env ? "ASSUMED ENVIRONMENTAL INPUT" : "INPUT UNAVAILABLE"}</span></div>
        <EnvironmentVectors environment={env}/><p className="section-intro">Current plus windage produces the resultant used to size the potential exposure envelope.</p>
        <details className="case-details"><summary>Environmental inputs & three drift representations</summary><div className="case-facts"><Fact label="Environment source">{env?.source ?? "Not available"}</Fact><Fact label="Sample time">{utc(env?.sampled_at)}</Fact><Fact label="Attribution hindcast">{fmt(source?.drift_speed_kmh, 2)} km/h · {fmt(source?.drift_direction_deg, 0)}°</Fact><Fact label="Kinematic forecast">{fmt(forecast?.drift_speed_kmh, 2)} km/h · {fmt(forecast?.drift_direction_deg, 0)}°</Fact><Fact label="Environmental resultant">{fmt(env?.drift?.speed_kmh, 2)} km/h · {fmt(env?.drift?.direction_deg, 0)}°</Fact></div><p>These are distinct vectors in the existing pipeline. Environmental inputs are not silently substituted into the attribution ranking.</p></details>
      </div>
    </CaseSection>

    <CaseSection id="vessel-investigation" number="03" title="Vessels in the source search" question="Which vessels were present, and what did they do?" action={<button className="text-button" onClick={onOpenAll}>View all {candidates.length} candidates <ArrowUpRight size={13}/></button>}>
      <div className="ais-search-strip"><span><b>{scan.traffic?.monitored ?? scan.fleet.length}</b> monitored vessels</span><span><b>{entry?.ais?.records_in_window ?? "—"}</b> AIS fixes searched</span><span><b>{fmt(entry?.ais?.search_radius_km, 1)} km</b> source search radius</span><span><b>{candidates.length}</b> candidates</span></div>
      <div className="vessel-investigation-layout"><div className="case-candidate-list"><div className="eyebrow">TOP 5 · SELECT A VESSEL</div><CandidateList candidates={candidates.slice(0, 5)} selectedId={c?.ship_id} onSelect={onSelect}/></div>
        <div className="vessel-record">{inspectedShip ? <><div className="subsection-heading"><div><small>SELECTED VESSEL</small><h3>{inspectedShip.name}</h3></div><button className="text-button" onClick={onFocusMap}>Inspect track <MapPin size={13}/></button></div><div className="case-facts"><Fact label="Identity">MMSI {inspectedShip.mmsi} · {inspectedShip.vessel_type ?? "Unknown type"}</Fact><Fact label="Position">{position(inspectedShip.latitude, inspectedShip.longitude)}</Fact><Fact label="Speed / course">{fmt(inspectedShip.speed_kt, 1)} kt · {fmt(inspectedShip.course_deg, 0)}°</Fact><Fact label="Dimensions">{fmt(inspectedShip.length_m, 0)} × {fmt(inspectedShip.width_m, 0)} m</Fact><Fact label="Latest AIS fix">{utc(inspectedShip.position_time)}</Fact><Fact label="Coverage in analysis window">{coverage?.fixes != null ? `${coverage.fixes} fixes · max gap ${fmt(coverage.largest_gap_minutes as number, 1)} min` : "Not available"}</Fact><Fact label="Closest source approach">{c?.minimum_distance_km != null ? `${fmt(c.minimum_distance_km, 2)} km · ${c.closest_time?.slice(11, 16) ?? "—"} UTC` : "Not ranked"}</Fact><Fact label="Trajectory">{c?.trajectory_status ?? "Not ranked"}</Fact></div>
          <details className="case-details"><summary>Historical AIS fixes ({inspectedShip.track?.length ?? 0})</summary><div className="ais-fix-table"><table><thead><tr><th>Time UTC</th><th>Latitude</th><th>Longitude</th><th>Speed</th><th>Course</th></tr></thead><tbody>{(inspectedShip.track ?? []).map((fix, i) => <tr key={`${fix.time}-${i}`}><td>{fix.time.slice(11, 19)}</td><td>{showCoord(fix.lat, 4)}</td><td>{showCoord(fix.lon, 4)}</td><td>{fmt(fix.speed_kt, 1)} kt</td><td>{fmt(fix.course_deg, 0)}°</td></tr>)}</tbody></table></div></details></> : <p>No vessel record available.</p>}</div>
      </div>
      <div className="consistency-review"><div><ShieldAlert size={19}/><h3>SAR–AIS consistency</h3></div><p>No independent SAR vessel detections or SAR–AIS matching results are supplied. The map anchors the scenario tile to an AIS fix; a vessel match cannot be established from that assignment.</p><div className="case-facts"><Fact label="AIS track coverage">{coverage?.reason ?? "Not available"}</Fact><Fact label="Behaviour flags">{c?.anomalous_points != null ? `${c.anomalous_points} anomalous fixes` : "Not available"}</Fact><Fact label="SAR–AIS match verdict">Not assessed</Fact></div><small>AIS gaps and movement anomalies are investigation flags, not proof of wrongdoing.</small></div>
    </CaseSection>

    <CaseSection id="attribution-evidence" number="04" title="Attribution & evidence" question="Why is this vessel ranked here?" action={<span className="data-tag">INVESTIGATION AID</span>}>
      {c ? <><div className="attribution-context"><span>Rank <b>#{c.rank} of {candidates.length}</b></span><span>Attribution confidence <b>Not calibrated</b></span><span>Case assessment <b>{entry?.evidence?.assessment?.outcome === "NO_STRONG_CANDIDATE" ? "No strong candidate" : entry?.evidence?.assessment?.outcome === "LEADING_CANDIDATE_UNSTABLE" ? "Leading candidate unstable" : entry?.evidence?.assessment ? "Candidate supported" : "Not assessed"}</b></span></div>
      <div className="attribution-layout"><div><EvidencePanel candidate={c} entry={entry} weights={weights}/></div><div className="evidence-findings"><h3>Supporting observations</h3>{support.length ? <ul>{support.map((beat,i) => <li key={i}>{beat.text}</li>)}</ul> : <p>No supporting observations supplied.</p>}<h3>What weakens the association</h3>{weaken.length ? <ul className="weakens">{weaken.map((beat,i) => <li key={i}>{beat.text}</li>)}</ul> : <p>No weakening observations supplied.</p>}{evidence?.unavailable.length ? <p className="provenance-note">Unavailable: {evidence.unavailable.join(", ")}.</p> : null}</div></div>
      <div className="source-test"><div><h3>Source consistency test</h3><p>Forward-drift the vessel's historical position and compare it with the detection location.</p></div><button className="reportbtn" disabled={testBusy || !age?.release_at} onClick={() => onTest(c)}>{testBusy ? "Testing…" : "Run source test"}</button></div>
      <div className="case-facts"><Fact label="Verdict">{test?.available ? test.within_envelope ? "Consistent" : "Not consistent" : cf?.verdict ? String(cf.verdict) : "Not available"}</Fact><Fact label="Miss / tolerance">{test?.available ? `${fmt(test.miss_distance_km, 2)} / ${fmt(test.consistency_radius_km ?? test.envelope_radius_km, 2)} km` : cf?.miss_km != null ? `${fmt(cf.miss_km as number, 2)} / ${fmt(cf.threshold_km as number, 2)} km` : "Not available"}</Fact><Fact label="Sensitivity">{cf?.robustness ? String(cf.robustness) : "Not assessed"}</Fact></div>
      {test && !test.available && <p className="compact-result">{test.reason}</p>}{test?.available && <CounterfactualLines result={test}/>}
      <details className="case-details"><summary>Assessment reasoning & scoring context</summary><ul>{entry?.evidence?.assessment?.reasons.map((reason,i) => <li key={i}>{reason}</li>)}</ul><p>{entry?.ais?.search_radius_basis}</p></details>
      </> : <p>No candidate attribution is available for this observation.</p>}
    </CaseSection>

    <CaseSection id="forecast-exposure" number="05" title="Forecast & potential exposure" question="Where could the oil move, and what may be exposed?" action={<span className="data-tag">PROJECTED · NOT OBSERVED DAMAGE</span>}>
      <div className="forecast-sequence">{(forecast?.points ?? []).map((point) => <button key={point.hours_ahead} onClick={() => onForecast(point.hours_ahead)}><small>+{point.hours_ahead} HOURS</small><b>{showCoord(point.latitude, 3)}°</b><span>{showCoord(point.longitude, 3)}°</span><em>Show on map ↗</em></button>)}</div>
      <p className="provenance-note">Only modelled horizons are shown. Positions are kinematic projections; forecast confidence is not quantified.</p>
      <div className="exposure-layout"><div><h3>Potentially affected waters</h3><div className="case-facts"><Fact label="Current mapped location">{position(spill?.latitude, spill?.longitude)}</Fact><Fact label="Observed spill footprint">Not measured · classifier only</Fact><Fact label="Potential envelope">{fmt(area?.area_km2, 1)} km² · {fmt(area?.radius_km, 2)} km radius</Fact><Fact label="Response ordering">{entry?.response_priority ?? "Not ranked"}{entry?.damage?.priority_score != null ? ` · ${fmt(entry.damage.priority_score, 1)} / 100` : ""}</Fact></div><p className="section-intro">The envelope marks waters to monitor under the assumed drift. It is not a measured slick or an ecological-damage estimate.</p></div><div className="sensitive-area-status"><h3>Sensitive-area assessment</h3><p>No protected-area, fishing-zone, habitat or coastal-community dataset is connected. Exposure to those areas is not assessed.</p><small>Coastline imagery provides context only. Verify sensitive receptors before response tasking.</small></div></div>
      <div className="subsection-heading"><h3>Operational exposure · next {risk?.forecast_horizon_hours ?? "—"} h</h3><button className="text-button" onClick={onRouting}>Inspect vessel routing <ArrowUpRight size={13}/></button></div>
      {risk ? <><div className="ais-search-strip"><span><b>{risk.vessels_checked}</b> vessels checked</span><span><b>{risk.at_risk_count}</b> projected to enter</span><span><b>{risk.safe_count}</b> stay clear in the model</span></div>{risk.at_risk.length ? <div className="exposure-table"><table><thead><tr><th>Vessel</th><th>Entry estimate</th><th>Risk</th><th>Route status</th></tr></thead><tbody>{risk.at_risk.map((row) => <tr key={row.ship_id}><td>{row.name}</td><td>{row.estimated_entry_minutes} min</td><td>{row.risk}</td><td>{row.detour?.already_inside_zone ? "Exit route" : row.detour?.clears_spill_zone ? "Avoidance available" : "No clear route supplied"}</td></tr>)}</tbody></table></div> : <p>No monitored vessel is projected to enter this envelope.</p>}</> : <p>Operational exposure data unavailable.</p>}
      <details className="case-details"><summary>Forecast and exposure assumptions</summary><p>The vessel-risk model tests constant-speed/course tracks against current and forecast envelopes within its stated horizon. The longer oil forecast is not a 48-hour vessel-risk assessment.</p><p>The response score orders incidents by envelope area, detection confidence and vessel size. It excludes oil volume, weathering, shoreline proximity and habitat sensitivity.</p>{entry?.forecast_environmental?.points?.length ? <div className="exposure-table"><table><thead><tr><th>Environmental projection</th><th>Latitude</th><th>Longitude</th></tr></thead><tbody>{entry.forecast_environmental.points.map((point) => <tr key={point.hours_ahead}><td>+{point.hours_ahead} h</td><td>{showCoord(point.latitude, 4)}</td><td>{showCoord(point.longitude, 4)}</td></tr>)}</tbody></table></div> : null}</details>
    </CaseSection>
    </>}

    <CaseSection id="response-output" number={detected ? "06" : "02"} title="Response & investigation output" question="What should the officer do next?" action={<button className="reportbtn openreport" onClick={onReport}><FileText size={14}/> Generate report</button>}>
      {detected ? <><div className="response-task"><span className="data-tag">{entry?.response_priority ?? "REVIEW"} · {entry?.response?.urgency ?? "INVESTIGATE"}</span><p>{entry?.response?.action ?? "Verify the detection and notify the relevant maritime authority."}</p></div><GovernmentActions/></> : <p>No oil signature was classified in this observation. Continue monitoring and retain the observation record.</p>}
      <div className="report-handoff"><div><h3>Incident evidence package</h3><p>Detection · source estimate · vessel attribution · forecast · exposure · data provenance</p></div><button className="primary-button" onClick={onReport}>Review / export report</button></div>
    </CaseSection>
  </div>;
}
