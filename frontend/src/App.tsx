import {useEffect,useMemo,useState} from "react";
import {MapContainer,TileLayer,Polygon,Polyline,Marker,CircleMarker,Popup,Tooltip,useMap} from "react-leaflet";
import L from "leaflet";
import {AlertTriangle,Anchor,ArrowDownLeft,ArrowUpRight,Check,ChevronRight,Clock3,FileText,Info,Layers,Navigation,Pause,Play,RotateCcw,Satellite,Ship,ShieldAlert,Wind,X} from "lucide-react";
import {attribute,candidates,consistency,detectSpill,forecast,getIncident,geo,hindcast,report,tracks} from "./lib/api";

const center:[number,number]=[19.68,71.39];
const icon=(color:string)=>L.divIcon({className:"vessel-icon",html:`<div style="background:${color}"></div>`,iconSize:[16,16],iconAnchor:[8,8]});
const steps=["Spill Detection","Source Reconstruction","AIS Correlation","Vessel Attribution","Forecast"];
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
function App(){
 const [inc,setInc]=useState<any>(null),[spill,setSpill]=useState<any>(null),[cand,setCand]=useState<any[]>([]),[cons,setCons]=useState<any>(null),[fc,setFc]=useState<any>(null),[source,setSource]=useState<any>(null),[tracksData,setTracksData]=useState<any>(null),[stage,setStage]=useState(0),[spillGeo,setSpillGeo]=useState<any>(null),[running,setRunning]=useState(false),[hind,setHind]=useState<any>(null),[hindStep,setHindStep]=useState(0),[forecastStep,setForecastStep]=useState(0),[selected,setSelected]=useState<any>(null),[reportData,setReportData]=useState<any>(null),[reportOpen,setReportOpen]=useState(false),[apiLive,setApiLive]=useState(true),[time,setTime]=useState("10:45"),[replay,setReplay]=useState(false),[replayIndex,setReplayIndex]=useState(0);
 useEffect(()=>{(async()=>{const i=await getIncident();setInc(i);setApiLive(!!(await fetch("http://localhost:8000/health").then(r=>r.ok).catch(()=>false)));setSource(await geo("source_region.geojson"));setSpillGeo(await geo("spill_polygon.geojson"));setTracksData(await tracks());})()},[]);
 const wait=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));
 const run=async()=>{
  setRunning(true);
  setStage(0);
  setSpill(null); setHind(null); setHindStep(0); setCand([]); setCons(null); setFc(null); setSelected(null); setForecastStep(0); setTime("10:45");

  setStage(1);
  await wait(650);
  await detectSpill();
  setSpill(true);
  await wait(1100);

  setStage(2);
  await wait(450);
  setHind(await hindcast());
  for(let i=0;i<=4;i++){ setHindStep(i); await wait(420); }
  await wait(650);

  setStage(3);
  await wait(450);
  setCand((await candidates()).vessels);
  setCons(await consistency());
  await wait(1100);

  setStage(4);
  await wait(450);
  setSelected(await attribute("V001"));
  await wait(1300);

  setStage(5);
  await wait(450);
  setFc(await forecast());
  for(let i=0;i<=4;i++){ setForecastStep(i); await wait(420); }
  await wait(650);
  setRunning(false);
 };
 useEffect(()=>{if(!replay)return;const id=setInterval(()=>setReplayIndex(i=>{if(!inc?.replay_events)return i; if(i>=inc.replay_events.length-1){setReplay(false);return i}return i+1}),1100);return()=>clearInterval(id)},[replay,inc]);
 const vesselById=useMemo(()=>Object.fromEntries((cand||[]).map(v=>[v.vessel_id,v])),[cand]);
 if(!inc)return <div className="loading">Loading OILTRACE AI…</div>;
 return <div className="app">
  <header className="topbar"><div className="brand"><div className="brandmark"><Anchor size={18}/></div><div><b>OILTRACE AI</b><small>MARITIME OIL-SPILL INTELLIGENCE & ATTRIBUTION</small></div></div><div className="incident"><span className="live-dot"/> {apiLive?"API LIVE":"LOCAL DEMO DATA"} <Badge tone="amber">DEMO / SYNTHETIC</Badge><strong>{inc.incident_id}</strong></div></header>
  <div className="alertbar"><AlertTriangle size={16}/><b>HIGH PRIORITY MARITIME POLLUTION ALERT</b><span>Oil spill probability 94% · 6 vessels correlated · 1 high-priority investigation candidate.</span></div><div className="kpis"><Kpi icon={<Satellite/>} label="Spill Probability" value="94%" note="Oil-like signature accepted"/><Kpi icon={<Layers/>} label="Estimated Area" value="12.8 km²" note="7.4 × 2.1 km footprint"/><Kpi icon={<Navigation/>} label="Source Confidence" value="78%" note="Probabilistic region"/><Kpi icon={<Ship/>} label="Potential Vessels" value="6" note="6 correlated · 1 high-priority"/></div>
  <main className="layout">
   <aside className="left"><Card><div className="eyebrow">INVESTIGATION</div><h2>Incident workflow</h2><button className="start" onClick={run} disabled={running}><Play size={16}/>{running?"INVESTIGATION RUNNING":"START INVESTIGATION"}</button><div className="pipeline">{steps.map((s,i)=><div className={"step "+(stage>=i+1?"done":"")+(stage===i+1?" active":"")} key={s}><div className="step-icon">{stage>=i+1?<Check size={14}/>:i+1}</div><div><b>{s}</b><small>{i===0?"SAR scene + look-alike":i===1?"Wind/current hindcast":i===2?"AIS source-window search":i===3?"Evidence-weighted score":"48-hour drift outlook"}</small></div>{stage>=i+1&&<Check size={14}/>}</div>)}</div></Card>
    <Card><div className="eyebrow">SATELLITE ANALYSIS</div><div className="scene"><img src="/demo-images/sar_overlay.jpg"/></div><div className="scene-meta"><span>Sentinel-1 SAR</span><span>15 Aug 2026 · 14:00 UTC</span></div><div className="metrics"><div><small>OIL PROB.</small><b>94%</b></div><div><small>AREA</small><b>12.8</b></div><div><small>CONF.</small><b>HIGH</b></div></div></Card>
    <Card><div className="eyebrow">LOOK-ALIKE ANALYSIS</div>{inc.lookalike.classes.map((x:any)=><div className="barrow" key={x.label}><span>{x.label}</span><b>{Math.round(x.probability*100)}%</b><i><em style={{width:`${x.probability*100}%`}}/></i></div>)}<div className="accepted"><Check size={14}/> Oil-like signature accepted</div></Card>
   </aside>
   <section className="mapwrap"><div className="maphead"><div><span className="eyebrow">LIVE INVESTIGATION MAP</span><h1>Arabian Sea · Gujarat Coast AOI</h1><div className="investigation-status">{running&&stage===1&&"ANALYZING SAR SCENE…"}{running&&stage===2&&"BACKTRACKING SLICK PARTICLES…"}{running&&stage===3&&"CORRELATING HISTORICAL AIS…"}{running&&stage===4&&"RANKING SOURCE VESSELS…"}{running&&stage===5&&"PROJECTING 48-HOUR DRIFT…"}{!running&&stage===0&&"READY FOR INVESTIGATION"}{!running&&stage===5&&"INCIDENT RECONSTRUCTED"}</div></div><div className="maptools"><Badge tone="amber">SOURCE 78%</Badge><Badge tone="red">1 AIS-INCONSISTENT</Badge></div></div>
    <MapContainer center={center} zoom={9} className="map" scrollWheelZoom><MapResizeFix/><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
      {source&&stage>=3&&<Polygon positions={source.features[0].geometry.coordinates[0].map((p:number[])=>[p[1],p[0]])} pathOptions={{color:"#f59e0b",fillColor:"#f59e0b",fillOpacity:.16,weight:2,dashArray:"6 6"}}><Tooltip>Probable source region · 78% confidence</Tooltip></Polygon>}
      {stage>=1&&<SpillLayer geo={spillGeo}/>}
      {stage>=3&&tracksData?.features?.map((f:any)=><Polyline key={f.properties.vessel_id} positions={f.geometry.coordinates.map((p:number[])=>[p[1],p[0]])} pathOptions={{color:f.properties.vessel_id==="V001"?"#ef4444":"#60a5fa",weight:f.properties.vessel_id==="V001"?3:1.5,opacity:.65}}/>)}
      {stage>=3&&(cand.length?cand:[]).map((v:any)=>{const p=v.track.find((x:any)=>x.time.includes(time==="10:00"?"T10:00":time==="10:15"?"T10:15":time==="10:30"?"T10:30":"T10:45"))||v.track[5];return <Marker key={v.vessel_id} position={[p.lat,p.lon]} icon={icon(v.vessel_id==="V001"?"#ef4444":"#38bdf8")} eventHandlers={{click:()=>setSelected(v)}}><Popup><b>{v.vessel_name}</b><br/>{v.attribution_score}/100 · {v.confidence}</Popup></Marker>})}
      {stage>=2&&hind&&hind.particles.map((p:any)=><CircleMarker key={p.id} center={[p.path[Math.min(hindStep,p.path.length-1)].lat,p.path[Math.min(hindStep,p.path.length-1)].lon]} radius={2.8} pathOptions={{color:"#fbbf24",fillColor:"#fbbf24",fillOpacity:.85,weight:0}}/>)}
      {stage>=5&&fc&&fc.polygons?.slice(0,forecastStep+1).map((f:any)=><Polygon key={f.properties.hours} positions={f.geometry.coordinates[0].map((p:number[])=>[p[1],p[0]])} pathOptions={{color:"#38bdf8",fillColor:"#38bdf8",fillOpacity:.05,weight:2,dashArray:"5 7"}}/>)}
      {stage>=3&&<div className="source-label"><span>PROBABLE RELEASE REGION</span><b>78% CONFIDENCE</b><small>Probabilistic · not an exact origin</small></div>}
      <div className="legend"><b>MAP LEGEND</b><span><i className="dot spill"/>Detected oil slick</span><span><i className="dot source-dot"/>Probable release region</span><span><i className="dot hi"/>High-priority candidate</span><span><i className="dot vessel"/>AIS vessel</span><span><i className="line-dot forecast"/>Forecast envelope</span></div>
    </MapContainer>
    <div className="mapbottom"><div className="env"><Wind size={15}/><span>WIND <b>235° · 14 kt</b></span><span>CURRENT <b>208° · 0.55 m/s</b></span></div><div className="timebar"><Clock3 size={15}/><b>AIS TIME</b>{inc.slider_times.map((t:string)=><button className={time===t?"sel":""} onClick={()=>setTime(t)} key={t}>{t}</button>)}</div></div>
   </section>
   <aside className="right"><Card className="source-recon"><div className="eyebrow">SOURCE RECONSTRUCTION</div><h2>Observed ≠ release location</h2><p>Wind and current can move a slick after release. Backward hindcasting tests where particles converge.</p><div className="window"><small>ESTIMATED RELEASE WINDOW</small><b>10:20 — 11:10 UTC</b><Badge tone="amber">HIGH · 78%</Badge></div><div className="physics"><div><ArrowDownLeft/><small>BACKWARD HINDCAST</small><b>{hind?`${hindStep}/4 hr`:"READY"}</b></div><div><Wind/><small>DRIFT</small><b>2.7 km/h · 215.5°</b></div></div></Card>
    <Card><div className="eyebrow">SAR–AIS CONSISTENCY</div><div className="consrow"><div><b>{cons?.sar_detected_vessels??5}</b><small>SAR CONTACTS</small></div><ChevronRight/><div><b>{cons?.ais_matched_vessels??4}</b><small>AIS MATCHED</small></div><ChevronRight/><div className="warn"><b>{cons?.inconsistent_vessels??1}</b><small>INCONSISTENT</small></div></div><div className="alert"><ShieldAlert size={15}/><span><b>{cons?.flagged_vessel_name??"MV Coastal Pioneer"}</b><br/>Potential AIS-dark interval · Requires investigation</span></div></Card>
    <Card><div className="eyebrow">CANDIDATE VESSEL FILTERING</div><div className="subtle">Search scope: probable source region + release-time window</div><div className="candidates">{cand.length?cand.map((v:any)=><button key={v.vessel_id} className={"candidate "+(selected?.vessel_id===v.vessel_id?"selected":"")} onClick={()=>setSelected(v)}><div className="rank">#{cand.indexOf(v)+1}</div><div className="cv"><b>{v.vessel_name}</b><small>{v.vessel_type} · {v.factors.distance_km} km · {v.labels.time_match} time match</small></div><strong>{v.attribution_score}</strong></button>):<div className="empty">Run investigation to reconstruct AIS candidates.</div>}</div></Card>
    {selected&&<Card className="evidence"><div className="eyebrow">EXPLAINABLE RESULT</div><div className="potential">HIGH-PRIORITY INVESTIGATION CANDIDATE</div><div className="vname">{selected.vessel_name}</div><div className="score"><b>{selected.attribution_score}</b><span>/100</span><Badge tone={selected.confidence==="High"?"red":"amber"}>{selected.confidence} confidence</Badge></div><div className="factorlist">{Object.entries({time_match:"Time Match",source_overlap:"Source Region",trajectory:"Trajectory",distance_score:"Distance",behaviour:"Behaviour",ais_consistency:"AIS Consistency",relevance:"Vessel Relevance"}).map(([k,label]:any)=><div key={k}><span>{label}</span><b>{selected.factors[k]}</b><i><em style={{width:`${selected.factors[k]}%`}}/></i></div>)}</div><ul>{selected.evidence.slice(0,5).map((e:string)=><li key={e}><Check size={13}/>{e}</li>)}</ul><div className="disclaimer"><Info size={14}/>{inc.disclaimer}</div></Card>}
   </aside>
  </main>
  <footer><div className="footer-pipeline">{bottomSteps.map((label,i)=>{const done=i<bottomDoneCount[stage]; const active=stage<5&&i===bottomProgress[stage]; return <div key={label} className={"bottom-step "+(done?"done ":"")+(active?"active":"")}><span>{i+1}</span><b>{label}</b></div>})}</div><div className="footer-actions"><button onClick={()=>{setReplay(true);setReplayIndex(0)}}><RotateCcw size={15}/> Replay Incident</button><button className="reportbtn" onClick={async()=>{setReportData(await report());setReportOpen(true)}}><FileText size={15}/> Generate Report</button></div></footer>
  {replay&&<div className="modal"><div className="modalbox replaybox"><button className="close" onClick={()=>setReplay(false)}><X/></button><div className="eyebrow">INCIDENT REPLAY</div><h2>Reconstructing the chain of evidence</h2><div className="replaytimeline">{inc.replay_events.map((e:any,i:number)=><div className={"revent "+(i<=replayIndex?"on":"")} key={e.time}><b>{e.time}</b><span/><div><strong>{e.label}</strong><p>{e.detail}</p></div></div>)}</div><div className="replaystate"><Play size={14}/> {inc.replay_events[replayIndex]?.label}</div></div></div>}
  {reportOpen&&reportData&&<div className="modal"><div className="modalbox reportbox"><button className="close" onClick={()=>setReportOpen(false)}><X/></button><div className="reportprint"><div className="reporthead"><div><b>OILTRACE AI</b><small>INVESTIGATION REPORT · DEMO / SYNTHETIC DATA</small></div><Badge tone="amber">UNDER INVESTIGATION</Badge></div><h2>{inc.title}</h2><p>{inc.region}</p><div className="reportgrid"><div><small>SPILL PROBABILITY</small><b>94%</b></div><div><small>AREA</small><b>12.8 km²</b></div><div><small>RELEASE WINDOW</small><b>10:20–11:10 UTC</b></div><div><small>SOURCE CONFIDENCE</small><b>78%</b></div></div><h3>Candidate ranking</h3>{reportData.top_candidates.map((v:any,i:number)=><div className="reportcandidate" key={v.vessel_id}><b>#{i+1} {v.vessel_name}</b><strong>{v.score}/100</strong><span>{v.confidence} · {v.assessment}</span></div>)}<h3>Forecast risk</h3><p>48-hour forecast confidence: <b>{inc.forecast.confidence}</b>. At-risk areas include {inc.forecast.at_risk_areas.map((a:any)=>a.name).join(", ")}.</p><div className="disclaimer"><Info size={14}/>{reportData.disclaimer}</div></div><button className="print" onClick={()=>window.print()}><FileText size={15}/> Print / Save PDF</button></div></div>}
 </div>
}
function Kpi({icon,label,value,note}:{icon:any,label:string,value:string,note:string}){return <Card className="kpi"><div className="kicon">{icon}</div><div><small>{label}</small><b>{value}</b><span>{note}</span></div></Card>}
function SpillLayer({geo}:{geo:any}){const ring=geo?.features?.[0]?.geometry?.coordinates?.[0]; return <Polygon positions={(ring||[]).map((p:number[])=>[p[1],p[0]])} pathOptions={{color:"#f97316",fillColor:"#f97316",fillOpacity:.38,weight:2}}><Tooltip>Observed SAR slick · 12.8 km²</Tooltip></Polygon>}
export default App;
