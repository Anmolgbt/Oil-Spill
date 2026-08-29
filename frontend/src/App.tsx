import {useEffect,useMemo,useState} from "react";
import {MapContainer,TileLayer,Polygon,Polyline,Marker,CircleMarker,Popup,Tooltip,useMap} from "react-leaflet";
import L from "leaflet";
import {AlertTriangle,Anchor,ArrowDownLeft,ArrowUpRight,Check,ChevronRight,Clock3,FileText,Info,Layers,Navigation,Pause,Play,RotateCcw,Satellite,Ship,ShieldAlert,Wind,X} from "lucide-react";
import {apiUrl,attribute,candidates,consistency,detectSpill,forecast,getIncident,geo,hindcast,report,simulate,snapshotList,tracks} from "./lib/api";

const center:[number,number]=[19.68,71.39];
const icon=(color:string)=>L.divIcon({className:"vessel-icon",html:`<div style="background:${color}"></div>`,iconSize:[16,16],iconAnchor:[8,8]});
const steps=["Spill Detection","Source Reconstruction","AIS Correlation","Vessel Attribution","Forecast"];
const pct=(v:any,fallback="—")=>typeof v==="number"?`${Math.round(v*100)}%`:fallback;
const num=(v:any,fallback="—")=>typeof v==="number"?String(v):fallback;
const hhmm=(iso:any)=>typeof iso==="string"&&iso.length>=16?iso.slice(11,16):"—";
// Ring of lat/lng around a point, so a computed spill/origin can be drawn on the
// map without needing a prepared GeoJSON fixture.
const ring=(lat:number,lon:number,km:number):[number,number][]=>{
 const dLat=km/110.574, dLon=km/(111.32*Math.cos(lat*Math.PI/180));
 return Array.from({length:37},(_,i)=>{const a=i*10*Math.PI/180; return [lat+dLat*Math.cos(a),lon+dLon*Math.sin(a)] as [number,number]});
};
const areaRadiusKm=(km2:any)=>typeof km2==="number"&&km2>0?Math.sqrt(km2/Math.PI):1.5;
const label=(v:number)=>v>=90?"Excellent":v>=70?"Good":v>=50?"Moderate":"Weak";
// Map one ranked ship from /simulate onto the shape the existing panels render.
const fromPipeline=(v:any,tracksById:any)=>({
 vessel_id:v.ship_id, vessel_name:v.name, vessel_type:v.vessel_type, mmsi:v.mmsi, flag:v.imo,
 attribution_score:v.attribution_score, confidence:v.confidence, assessment:v.assessment,
 evidence:v.evidence||[], factors:v.factors||{}, weights:v.weights, contributions:v.contributions,
 ais_dark:v.ais_dark, anomaly:v.anomaly,
 labels:{time_match:label(v.factors?.time_match??0),source_overlap:label(v.factors?.source_overlap??0),
         trajectory:label(v.factors?.trajectory??0),behaviour:v.anomaly?.is_anomaly?"Anomalous":"Normal"},
 track:tracksById[v.ship_id]||[],
});
const MONTHS=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const shortDate=(iso:any)=>{const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso??"")); return m?`${+m[3]} ${MONTHS[+m[2]-1]} ${m[1]}`:(iso??"—")};
const bottomSteps=["SATELLITE","SPILL","HINDCAST","SOURCE","AIS","RANKING","EVIDENCE","FORECAST","REPORT"];
const bottomProgress=[0,2,4,6,7,7];
const bottomDoneCount=[0,1,4,6,7,9];
function Card({children,className=""}:{children:any,className?:string}){return <section className={"card "+className}>{children}</section>}
function Badge({children,tone="blue"}:{children:any,tone?:string}){return <span className={"badge "+tone}>{children}</span>}
function MapResizeFix(){
 const map=useMap();
 useEffect(()=>{
  const refresh=()=>map.invalidateSize({animate:false});
  const timer=window.setTimeout(refresh,120);
  const container=map.getContainer().parentElement;
  const observer=container && typeof ResizeObserver!=="undefined" ? new ResizeObserver(refresh) : null;
  if(observer && container) observer.observe(container);
  window.addEventListener("resize",refresh);
  return()=>{window.clearTimeout(timer); observer?.disconnect(); window.removeEventListener("resize",refresh);};
 },[map]);
 return null;
}
function MapFocus({at}:{at:[number,number]|null}){
 const map=useMap();
 useEffect(()=>{ if(at) map.flyTo(at,10,{duration:1.1}); },[at&&at[0],at&&at[1]]);
 return null;
}
function App(){
 const [inc,setInc]=useState<any>(null),[spill,setSpill]=useState<any>(null),[cand,setCand]=useState<any[]>([]),[cons,setCons]=useState<any>(null),[fc,setFc]=useState<any>(null),[source,setSource]=useState<any>(null),[tracksData,setTracksData]=useState<any>(null),[stage,setStage]=useState(0),[spillGeo,setSpillGeo]=useState<any>(null),[running,setRunning]=useState(false),[hind,setHind]=useState<any>(null),[hindStep,setHindStep]=useState(0),[forecastStep,setForecastStep]=useState(0),[selected,setSelected]=useState<any>(null),[reportData,setReportData]=useState<any>(null),[reportOpen,setReportOpen]=useState(false),[apiLive,setApiLive]=useState(true),[time,setTime]=useState("10:45"),[replay,setReplay]=useState(false),[replayIndex,setReplayIndex]=useState(0),[sim,setSim]=useState<any>(null),[simMsg,setSimMsg]=useState(""),[snaps,setSnaps]=useState<string[]>([]),[snapIdx,setSnapIdx]=useState(0);
 useEffect(()=>{(async()=>{const i=await getIncident();setInc(i);setApiLive(!!(await fetch("http://localhost:8000/health").then(r=>r.ok).catch(()=>false)));setSource(await geo("source_region.geojson"));setSpillGeo(await geo("spill_polygon.geojson"));setTracksData(await tracks());const sl=await snapshotList();if(sl?.snapshots?.length)setSnaps(sl.snapshots);})()},[]);
 const wait=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));
 const reset=()=>{setStage(0);setSpill(null);setHind(null);setHindStep(0);setCand([]);setCons(null);setFc(null);setSelected(null);setForecastStep(0);setTime("10:45");setSim(null);setSimMsg("");};

 // Primary path: one POST /simulate drives the whole run. The stage animation is
 // kept purely for pacing — every value shown comes from the response.
 const runPipeline=async(result:any)=>{
  setSim(result);
  const steps=result.steps||{};

  setStage(1);
  await wait(900);

  if(result.status!=="SPILL_CONFIRMED"){
   setSimMsg(result.message||"No oil signature detected — continuing monitoring.");
   setStage(5);
   return;
  }

  setStage(2);
  await wait(450);
  const hc=steps.hindcast;
  if(hc?.particles){setHind({particles:hc.particles,steps:hc.steps});
   for(let i=0;i<=(hc.steps??4);i++){ setHindStep(i); await wait(380); }}
  await wait(500);

  setStage(3);
  await wait(450);
  const ais=steps.ais||{};
  const tracksById:any=Object.fromEntries((ais.vessels||[]).map((v:any)=>[v.id,v.track||[]]));
  setTracksData({type:"FeatureCollection",features:(ais.vessels||[]).filter((v:any)=>v.track?.length).map((v:any)=>({
    type:"Feature",properties:{vessel_id:v.id,vessel_name:v.name,ais_dark:!!v.gaps?.length},
    geometry:{type:"LineString",coordinates:v.track.map((p:any)=>[p.lon,p.lat])}}))});
  const dark=(ais.vessels||[]).filter((v:any)=>v.gaps?.length);
  setCons({sar_detected_vessels:ais.searched??0,ais_matched_vessels:(ais.searched??0)-dark.length,
           inconsistent_vessels:dark.length,flagged_vessel_name:dark[0]?.name??"None"});
  await wait(900);

  setStage(4);
  await wait(450);
  const ranked=(steps.attribution?.ranked||[]).map((v:any)=>fromPipeline(v,tracksById));
  setCand(ranked);
  if(ranked.length) setSelected(ranked[0]);
  await wait(1100);

  setStage(5);
  await wait(450);
  const features=steps.forecast?.features||[];
  setFc({polygons:features,confidence:"Computed",at_risk_areas:inc.forecast.at_risk_areas});
  for(let i=0;i<=Math.max(0,features.length-1);i++){ setForecastStep(i); await wait(380); }
 };

 // Fallback path: the original sequential calls, which themselves fall back to
 // the static fixtures in public/demo-data/.
 const runLegacy=async()=>{
  setStage(1); await wait(650); setSpill(await detectSpill()); await wait(1100);
  setStage(2); await wait(450); setHind(await hindcast());
  for(let i=0;i<=4;i++){ setHindStep(i); await wait(420); }
  await wait(650);
  setStage(3); await wait(450); setCand((await candidates()).vessels); setCons(await consistency()); await wait(1100);
  setStage(4); await wait(450); setSelected(await attribute("V001")); await wait(1300);
  setStage(5); await wait(450); setFc(await forecast());
  for(let i=0;i<=4;i++){ setForecastStep(i); await wait(420); }
  await wait(650);
 };

 const run=async()=>{
  setRunning(true);
  reset();
  const snapshotId=snaps[snapIdx];
  const result=await simulate(snapshotId);
  if(result) await runPipeline(result); else await runLegacy();
  // Advance to the next pass; hold on the last one rather than wrapping.
  if(snaps.length) setSnapIdx(i=>Math.min(i+1,snaps.length-1));
  setRunning(false);
 };
 useEffect(()=>{if(!replay)return;const id=setInterval(()=>setReplayIndex(i=>{if(!inc?.replay_events)return i; if(i>=inc.replay_events.length-1){setReplay(false);return i}return i+1}),1100);return()=>clearInterval(id)},[replay,inc]);
 const vesselById=useMemo(()=>Object.fromEntries((cand||[]).map(v=>[v.vessel_id,v])),[cand]);
 if(!inc)return <div className="loading">Loading OILTRACE AI…</div>;
 // Precedence: /simulate result > legacy /detect-spill > incident fixture.
 const det=spill?.detection;
 const simSpill=sim?.spill, simOrigin=sim?.origin, simAis=sim?.steps?.ais, simHind=sim?.steps?.hindcast;
 const clear=sim&&sim.status!=="SPILL_CONFIRMED";
 // Provenance: are the model-backed stages real inference or demo stubs?
 const mlBacked=sim?.provenance?.oil_detection?.source==="ml_model";
 const oilPct=pct(simSpill?.oil_probability??det?.oil_probability??inc.kpis.spill_probability);
 const areaKm2=num(simSpill?.estimated_area_km2??det?.estimated_area_km2??inc.kpis.estimated_area_km2);
 const sourcePct=pct(simOrigin?.confidence??inc.kpis.source_confidence);
 const vesselCount=simAis?.searched??(cand.length||inc.kpis.potential_vessels);
 const detectedShip=sim?.steps?.detection?.detections?.[0];
 const snapshotId=sim?.snapshot_id;
 // Map geometry: computed circles when the pipeline ran, fixtures otherwise.
 const simSpillRing=simSpill?ring(simSpill.latitude,simSpill.longitude,areaRadiusKm(simSpill.estimated_area_km2)):null;
 const simSourceRing=simOrigin?ring(simOrigin.origin_lat,simOrigin.origin_lon,simHind?.spread_km??3):null;
 const focus:[number,number]|null=simSpill?[simSpill.latitude,simSpill.longitude]:null;
 return <div className="app">
  <header className="topbar"><div className="brand"><div className="brandmark"><Anchor size={18}/></div><div><b>OILTRACE AI</b><small>MARITIME OIL-SPILL INTELLIGENCE & ATTRIBUTION</small></div></div><div className="incident"><span className="live-dot"/> {apiLive?"API LIVE":"LOCAL DEMO DATA"} <Badge tone={mlBacked?"blue":"amber"}>{mlBacked?`ML · ${sim.provenance.oil_detection.model_version??"model"}`:"DEMO / SYNTHETIC"}</Badge><strong>{inc.incident_id}</strong></div></header>
  <div className="alertbar"><AlertTriangle size={16}/><b>{clear?"MONITORING — NO SPILL DETECTED":"HIGH PRIORITY MARITIME POLLUTION ALERT"}</b><span>{clear?simMsg:`Oil spill probability ${oilPct} · ${vesselCount} vessels correlated · ${cand.length?cand.filter((v:any)=>v.attribution_score>=80).length:inc.sar_ais_check.inconsistent_vessels} high-priority investigation candidate.`}</span></div><div className="kpis"><Kpi icon={<Satellite/>} label="Spill Probability" value={oilPct} note={detectedShip?`${detectedShip.ship_name} · pass ${snapshotId?.toUpperCase()}`:inc.lookalike.decision}/><Kpi icon={<Layers/>} label="Estimated Area" value={`${areaKm2} km²`} note={simSpill?`${simSpill.mask_pixels?.toLocaleString()??"—"} mask px × ${num(simSpill.pixel_area_km2)} km²`:`${num(inc.spill_metrics.length_km)} × ${num(inc.spill_metrics.width_km)} km footprint`}/><Kpi icon={<Navigation/>} label="Source Confidence" value={sourcePct} note={simOrigin?`Release ${hhmm(simOrigin.release_window_start)}–${hhmm(simOrigin.release_window_end)} UTC`:"Probabilistic region"}/><Kpi icon={<Ship/>} label="Potential Vessels" value={String(vesselCount)} note={simAis?`${simAis.retained} retained · ${simAis.eliminated} eliminated`:`${vesselCount} correlated · ${inc.sar_ais_check.inconsistent_vessels} high-priority`}/></div>
  <main className="layout">
   <aside className="left"><Card><div className="eyebrow">INVESTIGATION</div><h2>Incident workflow</h2><button className="start" onClick={run} disabled={running}><Play size={16}/>{running?"INVESTIGATION RUNNING":"START INVESTIGATION"}</button><div className="pipeline">{steps.map((s,i)=><div className={"step "+(stage>=i+1?"done":"")+(stage===i+1?" active":"")} key={s}><div className="step-icon">{stage>=i+1?<Check size={14}/>:i+1}</div><div><b>{s}</b><small>{i===0?"SAR scene + look-alike":i===1?"Wind/current hindcast":i===2?"AIS source-window search":i===3?"Evidence-weighted score":"48-hour drift outlook"}</small></div>{stage>=i+1&&<Check size={14}/>}</div>)}</div></Card>
    <Card><div className="eyebrow">SATELLITE ANALYSIS</div><div className="scene"><img src={apiUrl(detectedShip?.image_url)??"/demo-images/sar_overlay.jpg"}/></div><div className="scene-meta"><span>{snapshotId?`PASS ${snapshotId.toUpperCase()}${detectedShip?` · ${detectedShip.ship_id}`:""}`:inc.satellite.sensor}</span><span>{sim?.observed_at?`${shortDate(sim.observed_at.slice(0,10))} · ${hhmm(sim.observed_at)} UTC`:`${shortDate(inc.satellite.acquisition_date)} · ${inc.satellite.acquisition_time}`}</span></div>{simSpill&&<div className="scene-meta"><span>{num(simSpill.latitude)}° N</span><span>{num(simSpill.longitude)}° E</span></div>}<div className="metrics"><div><small>OIL PROB.</small><b>{oilPct}</b></div><div><small>AREA</small><b>{areaKm2}</b></div><div><small>CONF.</small><b>{String(inc.spill_metrics.confidence).toUpperCase()}</b></div></div></Card>
    <Card><div className="eyebrow">LOOK-ALIKE ANALYSIS</div>{inc.lookalike.classes.map((x:any)=><div className="barrow" key={x.label}><span>{x.label}</span><b>{Math.round(x.probability*100)}%</b><i><em style={{width:`${x.probability*100}%`}}/></i></div>)}<div className="accepted"><Check size={14}/> {inc.lookalike.decision}</div></Card>
   </aside>
   <section className="mapwrap"><div className="maphead"><div><span className="eyebrow">LIVE INVESTIGATION MAP</span><h1>Arabian Sea · Gujarat Coast AOI</h1><div className="investigation-status">{running&&stage===1&&"ANALYZING SAR SCENE…"}{running&&stage===2&&"BACKTRACKING SLICK PARTICLES…"}{running&&stage===3&&"CORRELATING HISTORICAL AIS…"}{running&&stage===4&&"RANKING SOURCE VESSELS…"}{running&&stage===5&&"PROJECTING 48-HOUR DRIFT…"}{!running&&stage===0&&(snaps.length?`READY · NEXT PASS ${snaps[snapIdx]?.toUpperCase()}`:"READY FOR INVESTIGATION")}{!running&&stage===5&&(clear?"NO SPILL — MONITORING":"INCIDENT RECONSTRUCTED")}</div></div><div className="maptools"><Badge tone="amber">SOURCE {sourcePct}</Badge><Badge tone="red">{inc.sar_ais_check.inconsistent_vessels} AIS-INCONSISTENT</Badge></div></div>
    <MapContainer center={center} zoom={9} className="map" scrollWheelZoom><MapResizeFix/><MapFocus at={focus}/><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
      {simSourceRing&&stage>=2&&<Polygon positions={simSourceRing} pathOptions={{color:"#f59e0b",fillColor:"#f59e0b",fillOpacity:.16,weight:2,dashArray:"6 6"}}><Tooltip>Probable release region · {sourcePct} confidence</Tooltip></Polygon>}
      {!simSourceRing&&source&&stage>=3&&<Polygon positions={source.features[0].geometry.coordinates[0].map((p:number[])=>[p[1],p[0]])} pathOptions={{color:"#f59e0b",fillColor:"#f59e0b",fillOpacity:.16,weight:2,dashArray:"6 6"}}><Tooltip>Probable source region · {sourcePct} confidence</Tooltip></Polygon>}
      {stage>=1&&!clear&&(simSpillRing?<Polygon positions={simSpillRing} pathOptions={{color:"#f97316",fillColor:"#f97316",fillOpacity:.38,weight:2}}><Tooltip>Detected slick · {areaKm2} km²</Tooltip></Polygon>:<SpillLayer geo={spillGeo} area={areaKm2}/>)}
      {stage>=3&&tracksData?.features?.map((f:any)=><Polyline key={f.properties.vessel_id} positions={f.geometry.coordinates.map((p:number[])=>[p[1],p[0]])} pathOptions={{color:f.properties.vessel_id==="V001"?"#ef4444":"#60a5fa",weight:f.properties.vessel_id==="V001"?3:1.5,opacity:.65}}/>)}
      {stage>=3&&(cand.length?cand:[]).map((v:any)=>{const p=v.track.find((x:any)=>x.time.includes(time==="10:00"?"T10:00":time==="10:15"?"T10:15":time==="10:30"?"T10:30":"T10:45"))||v.track[5];return <Marker key={v.vessel_id} position={[p.lat,p.lon]} icon={icon(v.vessel_id==="V001"?"#ef4444":"#38bdf8")} eventHandlers={{click:()=>setSelected(v)}}><Popup><b>{v.vessel_name}</b><br/>{v.attribution_score}/100 · {v.confidence}</Popup></Marker>})}
      {stage>=2&&hind&&hind.particles.map((p:any)=><CircleMarker key={p.id} center={[p.path[Math.min(hindStep,p.path.length-1)].lat,p.path[Math.min(hindStep,p.path.length-1)].lon]} radius={2.8} pathOptions={{color:"#fbbf24",fillColor:"#fbbf24",fillOpacity:.85,weight:0}}/>)}
      {stage>=5&&fc&&fc.polygons?.slice(0,forecastStep+1).map((f:any)=><Polygon key={f.properties.hours} positions={f.geometry.coordinates[0].map((p:number[])=>[p[1],p[0]])} pathOptions={{color:"#38bdf8",fillColor:"#38bdf8",fillOpacity:.05,weight:2,dashArray:"5 7"}}/>)}
      {stage>=3&&<div className="source-label"><span>PROBABLE RELEASE REGION</span><b>{simOrigin?`${hhmm(simOrigin.release_window_start)}–${hhmm(simOrigin.release_window_end)} UTC`:`${sourcePct} CONFIDENCE`}</b><small>Probabilistic · not an exact origin</small></div>}
      <div className="legend"><b>MAP LEGEND</b><span><i className="dot spill"/>Detected oil slick</span><span><i className="dot source-dot"/>Probable release region</span><span><i className="dot hi"/>High-priority candidate</span><span><i className="dot vessel"/>AIS vessel</span><span><i className="line-dot forecast"/>Forecast envelope</span></div>
    </MapContainer>
    <div className="mapbottom"><div className="env"><Wind size={15}/><span>WIND <b>{num(inc.environment.wind_towards_deg)}° · {num(inc.environment.wind_speed_kt)} kt</b></span><span>CURRENT <b>{num(inc.environment.current_towards_deg)}° · {num(inc.environment.current_speed_ms)} m/s</b></span></div><div className="timebar"><Clock3 size={15}/><b>AIS TIME</b>{inc.slider_times.map((t:string)=><button className={time===t?"sel":""} onClick={()=>setTime(t)} key={t}>{t}</button>)}</div></div>
   </section>
   <aside className="right"><Card className="source-recon"><div className="eyebrow">SOURCE RECONSTRUCTION</div><h2>Observed ≠ release location</h2><p>Wind and current can move a slick after release. Backward hindcasting tests where particles converge.</p><div className="window"><small>ESTIMATED RELEASE WINDOW</small><b>{hhmm(simOrigin?.release_window_start??inc.source_reconstruction.release_window_start)} — {hhmm(simOrigin?.release_window_end??inc.source_reconstruction.release_window_end)} UTC</b><Badge tone="amber">{simOrigin?"COMPUTED":String(inc.source_reconstruction.confidence_label).toUpperCase()} · {sourcePct}</Badge></div><div className="physics"><div><ArrowDownLeft/><small>{simOrigin?"PROBABLE ORIGIN":"BACKWARD HINDCAST"}</small><b>{simOrigin?`${num(simOrigin.origin_lat)}, ${num(simOrigin.origin_lon)}`:hind?`${hindStep}/4 hr`:"READY"}</b></div><div><Wind/><small>DRIFT</small><b>{num(simHind?.drift_speed_kmh??inc.source_reconstruction.drift_speed_kmh)} km/h · {num(simHind?.drift_bearing_deg??inc.source_reconstruction.drift_bearing_deg)}°</b></div></div></Card>
    <Card><div className="eyebrow">SAR–AIS CONSISTENCY</div><div className="consrow"><div><b>{cons?.sar_detected_vessels??inc.sar_ais_check.sar_detected_vessels}</b><small>SAR CONTACTS</small></div><ChevronRight/><div><b>{cons?.ais_matched_vessels??inc.sar_ais_check.ais_matched_vessels}</b><small>AIS MATCHED</small></div><ChevronRight/><div className="warn"><b>{cons?.inconsistent_vessels??inc.sar_ais_check.inconsistent_vessels}</b><small>INCONSISTENT</small></div></div><div className="alert"><ShieldAlert size={15}/><span><b>{cons?.flagged_vessel_name??inc.sar_ais_check.flagged_vessel_name}</b><br/>Potential AIS-dark interval · Requires investigation</span></div></Card>
    <Card><div className="eyebrow">CANDIDATE VESSEL FILTERING</div><div className="subtle">{simAis?`Search scope: ${simAis.search_radius_km} km around the computed origin, ${hhmm(simAis.release_window[0])}–${hhmm(simAis.release_window[1])} UTC · ${simAis.searched} searched, ${simAis.eliminated} eliminated`:"Search scope: probable source region + release-time window"}</div><div className="candidates">{cand.length?cand.map((v:any)=><button key={v.vessel_id} className={"candidate "+(selected?.vessel_id===v.vessel_id?"selected":"")} onClick={()=>setSelected(v)}><div className="rank">#{cand.indexOf(v)+1}</div><div className="cv"><b>{v.vessel_name}</b><small>{v.vessel_type} · {v.factors?.distance_km??"—"} km · {v.labels?.time_match??"—"} time match</small></div><strong>{v.attribution_score}</strong></button>):<div className="empty">{clear?simMsg:"Run investigation to reconstruct AIS candidates."}</div>}</div></Card>
    {selected&&<Card className="evidence"><div className="eyebrow">EXPLAINABLE RESULT</div><div className="potential">HIGH-PRIORITY INVESTIGATION CANDIDATE</div><div className="vname">{selected.vessel_name}</div><div className="score"><b>{selected.attribution_score}</b><span>/100</span><Badge tone={selected.confidence==="High"?"red":"amber"}>{selected.confidence} confidence</Badge></div><div className="factorlist">{Object.entries({time_match:"Time Match",source_overlap:"Source Region",trajectory:"Trajectory",distance_score:"Distance",behaviour:"Behaviour",ais_consistency:"AIS Consistency",relevance:"Vessel Relevance"}).map(([k,label]:any)=><div key={k}><span>{label}</span><b>{selected.factors[k]}</b><i><em style={{width:`${selected.factors[k]}%`}}/></i></div>)}</div><ul>{selected.evidence.slice(0,5).map((e:string)=><li key={e}><Check size={13}/>{e}</li>)}</ul><div className="disclaimer"><Info size={14}/>{inc.disclaimer}</div></Card>}
   </aside>
  </main>
  <footer><div className="footer-pipeline">{bottomSteps.map((label,i)=>{const done=i<bottomDoneCount[stage]; const active=stage<5&&i===bottomProgress[stage]; return <div key={label} className={"bottom-step "+(done?"done ":"")+(active?"active":"")}><span>{i+1}</span><b>{label}</b></div>})}</div><div className="footer-actions"><button onClick={()=>{setReplay(true);setReplayIndex(0)}}><RotateCcw size={15}/> Replay Incident</button><button className="reportbtn" onClick={async()=>{setReportData(await report());setReportOpen(true)}}><FileText size={15}/> Generate Report</button></div></footer>
  {replay&&<div className="modal"><div className="modalbox replaybox"><button className="close" onClick={()=>setReplay(false)}><X/></button><div className="eyebrow">INCIDENT REPLAY</div><h2>Reconstructing the chain of evidence</h2><div className="replaytimeline">{inc.replay_events.map((e:any,i:number)=><div className={"revent "+(i<=replayIndex?"on":"")} key={e.time}><b>{e.time}</b><span/><div><strong>{e.label}</strong><p>{e.detail}</p></div></div>)}</div><div className="replaystate"><Play size={14}/> {inc.replay_events[replayIndex]?.label}</div></div></div>}
  {reportOpen&&reportData&&<div className="modal"><div className="modalbox reportbox"><button className="close" onClick={()=>setReportOpen(false)}><X/></button><div className="reportprint"><div className="reporthead"><div><b>OILTRACE AI</b><small>INVESTIGATION REPORT · DEMO / SYNTHETIC DATA</small></div><Badge tone="amber">UNDER INVESTIGATION</Badge></div><h2>{inc.title}</h2><p>{inc.region}</p><div className="reportgrid"><div><small>SPILL PROBABILITY</small><b>{oilPct}</b></div><div><small>AREA</small><b>{areaKm2} km²</b></div><div><small>RELEASE WINDOW</small><b>{hhmm(inc.source_reconstruction.release_window_start)}–{hhmm(inc.source_reconstruction.release_window_end)} UTC</b></div><div><small>SOURCE CONFIDENCE</small><b>{sourcePct}</b></div></div><h3>Candidate ranking</h3>{(cand.length?cand.map((v:any)=>({vessel_id:v.vessel_id,vessel_name:v.vessel_name,score:v.attribution_score,confidence:v.confidence,assessment:v.assessment})):reportData.top_candidates).map((v:any,i:number)=><div className="reportcandidate" key={v.vessel_id}><b>#{i+1} {v.vessel_name}</b><strong>{v.score}/100</strong><span>{v.confidence} · {v.assessment}</span></div>)}<h3>Forecast risk</h3><p>48-hour forecast confidence: <b>{inc.forecast.confidence}</b>. At-risk areas include {inc.forecast.at_risk_areas.map((a:any)=>a.name).join(", ")}.</p><div className="disclaimer"><Info size={14}/>{reportData.disclaimer}</div></div><button className="print" onClick={()=>window.print()}><FileText size={15}/> Print / Save PDF</button></div></div>}
 </div>
}
function Kpi({icon,label,value,note}:{icon:any,label:string,value:string,note:string}){return <Card className="kpi"><div className="kicon">{icon}</div><div><small>{label}</small><b>{value}</b><span>{note}</span></div></Card>}
function SpillLayer({geo,area}:{geo:any,area:any}){const ring=geo?.features?.[0]?.geometry?.coordinates?.[0]; return <Polygon positions={(ring||[]).map((p:number[])=>[p[1],p[0]])} pathOptions={{color:"#f97316",fillColor:"#f97316",fillOpacity:.38,weight:2}}><Tooltip>Observed SAR slick · {area} km²</Tooltip></Polygon>}
export default App;
