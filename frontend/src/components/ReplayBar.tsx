import type React from "react";
import {Pause, Play} from "lucide-react";
import {clock} from "../lib/replay";

export interface ReplayTimeline {
  start: number;
  end: number;
  observedAt: number;
  releaseAt: number | null;
  maxAhead: number;
  passes: {id: string; at: number}[];
}

export interface ReplayBarProps {
  detected: boolean;
  timeline: ReplayTimeline | null;
  replayOn: boolean;
  replayT: number | null;
  setReplayT: (t: number | null) => void;
  playing: boolean;
  setPlaying: React.Dispatch<React.SetStateAction<boolean>>;
  replayFrame: {band: string} | null;
}

/**
 * The incident on one timeline: T1 through the detection and into the forecast.
 *
 * Extracted from App.tsx unchanged. The bands matter more than the animation —
 * the scrubber shows where observation stops and projection begins, so a viewer
 * cannot mistake a kinematic tail for something anybody watched happen.
 */
export function ReplayBar({
  detected, timeline, replayOn, replayT, setReplayT, playing, setPlaying, replayFrame,
}: ReplayBarProps) {
  return (
    <>
        {/* ---- REPLAY: the whole incident on one timeline ---- */}
        {detected && timeline && (
          <div className="replay">
            <div className="replayhead">
              <span className="eyebrow flush">REPLAY INCIDENT</span>
              {!replayOn ? (
                <button className="playbtn" onClick={() => { setReplayT(timeline.start); setPlaying(true); }}>
                  <Play size={14} /> PLAY INCIDENT
                </button>
              ) : (
                <>
                  <button className="playbtn" onClick={() => {
                    if (!playing && (replayT ?? 0) >= timeline.end) setReplayT(timeline.start);
                    setPlaying((v) => !v);
                  }}>
                    {playing ? <><Pause size={14} /> PAUSE</> : <><Play size={14} /> PLAY</>}
                  </button>
                  <button className="undobtn" onClick={() => { setPlaying(false); setReplayT(null); }}>
                    Exit replay
                  </button>
                </>
              )}
              {replayOn && <b className="replayclock">{clock(replayT as number)}</b>}
            </div>
            <div className="subtle replayrange">
              {timeline.passes[0]?.id.toUpperCase()} to detection, then +{timeline.maxAhead} h of forecast.
              The +24 h and +48 h horizons are listed in WHERE THIS OIL GOES NEXT rather than
              replayed, so the observed window stays legible on the scrubber.
            </div>

            <input className="scrub" type="range"
                   min={timeline.start} max={timeline.end}
                   step={Math.max(1, Math.round((timeline.end - timeline.start) / 600))}
                   value={replayT ?? timeline.start}
                   aria-label="Incident timeline"
                   aria-valuetext={`${clock(replayT ?? timeline.start)}${
                     replayFrame ? ` — ${replayFrame.band}` : ""}`}
                   onChange={(e) => { setPlaying(false); setReplayT(Number(e.target.value)); }} />

            {/* Where the passes sit on the timeline, and where observation
                stops and projection begins. */}
            <div className="replayticks">
              {timeline.passes.map((ps) => (
                <span key={ps.id}
                      // A position on the scrubber: not expressible in CSS.
                      style={{left: `${((ps.at - timeline.start) / (timeline.end - timeline.start)) * 100}%`}}>
                  {ps.id.toUpperCase()}
                </span>
              ))}
            </div>

            {replayOn && replayFrame && (
              <div className={"replaystate " + replayFrame.band} role="status" aria-live="polite">
                <b>
                  {replayFrame.band === "before" && "OBSERVED · no oil detected yet"}
                  {replayFrame.band === "estimated" && "ESTIMATED · hindcast"}
                  {replayFrame.band === "observed" && "OBSERVED · satellite detection"}
                  {replayFrame.band === "projected" && "PROJECTED · kinematic forecast"}
                </b>
                <span>
                  {replayFrame.band === "before" &&
                    "Real AIS positions. The satellite has not yet seen oil, and nothing here is inferred."}
                  {replayFrame.band === "estimated" &&
                    "Vessels are on real AIS, but the slick is back-derived from the detection — nobody observed oil at this position."}
                  {replayFrame.band === "observed" &&
                    "The pass the CNN actually classified. This is the one moment the oil was measured rather than inferred."}
                  {replayFrame.band === "projected" &&
                    "Past the last AIS fix and past the detection: both vessels and slick are kinematic projections with no environmental data."}
                </span>
              </div>
            )}
          </div>
        )}
    </>
  );
}
