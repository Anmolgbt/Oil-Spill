import type {SourceHeatmap, Source, Spill} from "../types";
export function SourceSpread({heatmap, source, spill}: {heatmap?: SourceHeatmap; source?: Source; spill?: Spill}) {
  const points = heatmap?.points ?? [];
  if (!points.length) return <div className="empty">Source spread unavailable</div>;
  const all = [...points, ...(source ? [source] : []), ...(spill ? [spill] : [])];
  const minLat = Math.min(...all.map((p) => p.latitude)), maxLat = Math.max(...all.map((p) => p.latitude));
  const minLon = Math.min(...all.map((p) => p.longitude)), maxLon = Math.max(...all.map((p) => p.longitude));
  const x = (lon: number) => 30 + (lon - minLon) / Math.max(maxLon - minLon, .001) * 260;
  const y = (lat: number) => 180 - (lat - minLat) / Math.max(maxLat - minLat, .001) * 150;
  return <figure className="source-spread"><svg viewBox="0 0 320 215" role="img" aria-label="Source positions across the existing drift assumption sweep">
    <path d="M30 30H290M30 80H290M30 130H290M30 180H290M30 30V180M95 30V180M160 30V180M225 30V180M290 30V180" stroke="#e2eaf0" fill="none"/>
    {points.map((p, i) => <circle key={i} cx={x(p.longitude)} cy={y(p.latitude)} r="4" fill="#d1a34a" opacity=".5"/>)}
    {source && spill && <line x1={x(source.longitude)} y1={y(source.latitude)} x2={x(spill.longitude)} y2={y(spill.latitude)} stroke="#ba8b32" strokeWidth="2" strokeDasharray="5 4"/>}
    {source && <circle cx={x(source.longitude)} cy={y(source.latitude)} r="6" fill="#fff" stroke="#976d18" strokeWidth="2"/>}
    {spill && <circle cx={x(spill.longitude)} cy={y(spill.latitude)} r="5" fill="#be4c3e"/>}
    <text x="30" y="203" fontSize="9" fill="#728997">{minLon.toFixed(3)}°</text><text x="290" y="203" textAnchor="end" fontSize="9" fill="#728997">{maxLon.toFixed(3)}°</text><text x="290" y="17" textAnchor="end" fontSize="9" fill="#728997">N ↑</text>
  </svg><figcaption>{points.length} source estimates · assumption sweep, not probability</figcaption></figure>;
}
