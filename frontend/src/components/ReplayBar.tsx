import type React from "react";
import {Pause, Play, RotateCcw} from "lucide-react";
import {clock} from "../lib/replay";
export interface ReplayTimeline {start: number; end: number; observedAt: number; releaseAt: number | null; maxAhead: number; passes: {id: string; at: number}[];}
export interface ReplayBarProps {detected: boolean; timeline: ReplayTimeline | null; replayOn: boolean; replayT: number | null; setReplayT: (t: number | null) => void; playing: boolean; setPlaying: React.Dispatch<React.SetStateAction<boolean>>; replayFrame: {band: string} | null;}
export function ReplayBar({detected, timeline: t, replayT, setReplayT, playing, setPlaying, replayFrame}: ReplayBarProps) {
  if (!detected || !t || t.end <= t.start) return null;
  return <section className="incident-timeline" aria-label="Incident timeline">
    <button className="icon-button" aria-label={playing ? "Pause timeline" : "Play timeline"} onClick={() => {
      if (replayT == null || replayT >= t.end) setReplayT(t.start);
      setPlaying((v) => !v);
    }}>{playing ? <Pause size={17} /> : <Play size={17} />}</button>
    <div className="timeline-track"><div className="timeline-labels"><span>{t.passes[0]?.id.toUpperCase() ?? "Release"} · {new Date(t.start).toISOString().slice(11, 16)}</span><span>{new Date(t.observedAt).toISOString().slice(11, 16)} Satellite</span><span>+{t.maxAhead}h Forecast</span></div>
      <div className="timeline-observations">{t.passes.map((pass) => <button key={pass.id} onClick={() => {setPlaying(false); setReplayT(pass.at);}}>{pass.id.toUpperCase()} <small>{new Date(pass.at).toISOString().slice(11,16)}</small></button>)}{t.releaseAt != null && <span>Release bound {new Date(t.releaseAt).toISOString().slice(11,16)}</span>}</div>
      <input type="range" aria-label="Incident timeline" aria-valuetext={clock(replayT ?? t.observedAt)} min={t.start} max={t.end} step={Math.max(1, Math.round((t.end - t.start) / 600))} value={replayT ?? t.observedAt} onChange={(e) => {setPlaying(false); setReplayT(Number(e.target.value));}} />
    </div>
    <span className="timeline-state">{replayT == null ? "Detection" : `${new Date(replayT).toISOString().slice(11, 16)} · ${replayFrame?.band ?? "estimated"}`}</span>
    <button className="icon-button" aria-label="Reset timeline" onClick={() => {setPlaying(false); setReplayT(null);}}><RotateCcw size={16} /></button>
  </section>;
}
