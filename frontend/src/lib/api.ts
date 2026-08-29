const API="http://localhost:8000";
async function request(path:string, options?:RequestInit){
  try{const c=new AbortController();const t=setTimeout(()=>c.abort(),1500);const r=await fetch(API+path,{...options,signal:c.signal,headers:{"Content-Type":"application/json",...(options?.headers||{})}});clearTimeout(t);if(!r.ok)throw new Error("API");return await r.json();}
  catch{return null;}
}
const local=async(name:string)=>fetch(`/demo-data/${name}`).then(r=>r.json());
export async function getIncident(){return (await request("/incident/IND-2026-001")) || local("incident.json")}
export async function detectSpill(){return (await request("/detect-spill",{method:"POST",body:JSON.stringify({})})) || {detection:{},lookalike:(await getIncident()).lookalike}}
export async function hindcast(){return (await request("/hindcast",{method:"POST",body:JSON.stringify({hours:4,n_particles:40})})) || {particles:await local("hindcast_particles.json").then(x=>x.particles),steps:4}}
export async function candidates(){return (await request("/ais/candidates",{method:"POST"})) || {vessels:(await local("vessels.json")).vessels}}
export async function tracks(){return (await request("/ais/tracks")) || local("vessel_tracks.geojson")}
export async function consistency(){return (await request("/ais/consistency-check")) || (await getIncident()).sar_ais_check}
export async function attribute(id:string){return (await request("/attribute",{method:"POST",body:JSON.stringify({vessel_id:id})})) || (await local("vessels.json")).vessels.find((v:any)=>v.vessel_id===id)}
export async function forecast(){return (await request("/forecast",{method:"POST",body:JSON.stringify({hours:[6,12,24,36,48]})})) || {polygons:(await local("forecast_polygons.geojson")).features,confidence:"Medium",at_risk_areas:(await getIncident()).forecast.at_risk_areas}}
export async function report(){return (await request("/report/IND-2026-001")) || {incident:await getIncident(),top_candidates:(await local("vessels.json")).vessels.slice(0,3),disclaimer:(await getIncident()).disclaimer}}
export async function geo(name:string){return local(name)}
