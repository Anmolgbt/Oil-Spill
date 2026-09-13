import {useEffect, useId, useState} from "react";
import {Badge, ScoreBar, fmt} from "../ui";
import {MAP_COLOURS as C} from "../mapColours";
import {NOT_AVAILABLE, showCoord} from "../lib/oiltrace";
import {CounterfactualLines} from "./CounterfactualLines";
import {OutcomeBanner} from "./OutcomeBanner";
import type {Candidate, Counterfactual, Ais, Evidence, Robustness, RobustnessFlip,
              Ship, Spill, Traffic, Weights} from "../types";

export interface WhyThisVesselProps {
  shownSpill?: Spill | null;
  shownAis?: Ais | null;
  candidates: Candidate[];
  weights: Weights;
  fleet: Ship[];
  selected: Ship | null;
  onSelectCandidate: (c: Candidate) => void;
  causationProven?: boolean;
  traffic?: Traffic | null;
  /** Counterfactual results keyed by the caller's own composite key. */
  whatIf: Record<string, Counterfactual>;
  whatIfBusy: string | null;
  whatIfKey: (spillShipId: string, mmsi: number) => string;
  askWhatIf: (c: Candidate) => void;
  /** Per-stream grades and the detection-level outcome. */
  evidence?: Evidence | null;
}

/**
 * WHY THIS VESSEL — the suspect score, taken apart.
 *
 * The backend has always computed proximity, trajectory and behaviour
 * separately; the dashboard used to show only their weighted total, which asks
 * a viewer to trust a number they cannot check. This renders each term with its
 * weight and the points it contributes, then the arithmetic, so the total can
 * be verified by eye.
 */
export function WhyThisVessel({
  shownSpill, shownAis, candidates: shownCandidates, weights, fleet, selected,
  onSelectCandidate, causationProven, traffic, whatIf, whatIfBusy, whatIfKey, askWhatIf,
  evidence,
}: WhyThisVesselProps) {
  const [showAll, setShowAll] = useState(false);
  const candidateListId = useId();
  const candidateSet = shownCandidates.map((c) => c.mmsi).join(",");
  useEffect(() => setShowAll(false), [shownSpill?.ship_id, candidateSet]);
  const visibleCandidates = showAll ? shownCandidates : shownCandidates.slice(0, 5);
  return (

        <div className="oilstrip">
          <div className="eyebrow">
            WHY THIS VESSEL?
            <span style={{marginLeft: "auto", textTransform: "none", letterSpacing: 0}}>
              {shownSpill?.ship_name} · {shownCandidates.length} vessel{shownCandidates.length === 1 ? "" : "s"}
              {shownAis?.search_radius_km != null && ` within ${fmt(shownAis.search_radius_km, 1)} km of the estimated source`}
            </span>
          </div>

          {/* Whether the evidence supports naming anyone, before the ranking
              that would otherwise imply it does. */}
          <OutcomeBanner assessment={evidence?.assessment} />

          {/* What the irrelevant-traffic filter actually did. The problem
              statement asks for this filtering explicitly, and until the search
              radius was derived from the drift envelope it admitted every
              vessel that existed — a funnel that rejects nobody is worth
              showing precisely so it cannot quietly become one again. */}
          {shownAis?.funnel && (
            <div className="funnel">
              <span><b>{traffic?.corpus_vessels ?? "—"}</b> vessels in the AIS corpus</span>
              <i>→</i>
              <span><b>{shownAis.funnel.monitored}</b> monitored this pass</span>
              <i>→</i>
              <span><b>{shownAis.funnel.with_fixes_in_window}</b> with AIS in the release window</span>
              <i>→</i>
              <span className="kept"><b>{shownAis.funnel.within_radius}</b> within {fmt(shownAis.search_radius_km, 1)} km</span>
              {shownAis.funnel.rejected_too_far > 0 && (
                <em>{shownAis.funnel.rejected_too_far} rejected as too far</em>
              )}
            </div>
          )}

          {shownCandidates.length === 0 ? (
            <div className="empty">
              No vessel was inside the search radius during the estimated release window.
            </div>
          ) : (
            <>
              <div className="oilhead cand">
                <span>#</span><span>Vessel</span><span>Closest approach</span>
                <span>Trajectory</span><span>Score</span>
              </div>
              <div id={candidateListId}>
              {visibleCandidates.map((c: Candidate) => {
                const isOpen = selected?.id === c.ship_id;
                return (
                  <div key={c.mmsi} className="candwrap">
                    <button className={"oilrank " + (isOpen ? "selected" : "")}
                            aria-expanded={isOpen}
                            onClick={() => onSelectCandidate(c)}>
                      <span className="pos">
                        {c.rank}
                        <i className="dot" style={{background: c.rank === 1 ? C.hindcast : C.track}} />
                      </span>
                      <span className="vessel">
                        <b>{c.name}</b>
                        <small>MMSI {c.mmsi} · {c.vessel_type}</small>
                      </span>
                      <span className="meta">
                        {fmt(c.minimum_distance_km, 2)} km
                        {c.closest_time ? ` · ${String(c.closest_time).slice(11, 16)} UTC` : ""}
                      </span>
                      <span className="sus">{c.trajectory_status ?? NOT_AVAILABLE}</span>
                      <span className="pct">{fmt(c.final_suspect_score)}</span>
                    </button>

                    {/* The breakdown, for the vessel actually under examination. */}
                    {isOpen && (
                      <div className="whybox">
                        <div className="whyhead">
                          Why {c.name} scores {fmt(c.final_suspect_score, 2)} / 100
                        </div>
                        {/* The weights ACTUALLY applied to this candidate. When
                            a term is unavailable the backend renormalises the
                            rest, so using the headline weights here would print
                            a sum that does not equal the shown total. */}
                        {(() => {
                          const w = c.weights_applied ?? weights;
                          return (
                            <>
                              {c.scored_on_partial_evidence && (
                                <div className="partialnote">Partial evidence · weights adjusted</div>
                              )}
                              <div className="scorebars">
                                <ScoreBar label="PROXIMITY" value={c.proximity_score ?? null}
                                          weight={w.proximity}
                                          detail={`closest ${fmt(c.minimum_distance_km, 2)} km from the estimated source`} />
                                <ScoreBar label="TRAJECTORY" value={c.trajectory_score ?? null}
                                          weight={w.trajectory}
                                          detail={c.trajectory_status ?? undefined} />
                                <ScoreBar label="BEHAVIOUR" value={c.behaviour_score ?? null}
                                          weight={w.behaviour}
                                          detail={c.behaviour_available === false
                                            ? (c.behaviour_reason ?? "Not available")
                                            : c.anomalous_points != null
                                              ? `Isolation Forest flagged ${c.anomalous_points} AIS fix${c.anomalous_points === 1 ? "" : "es"}`
                                              : undefined} />
                              </div>
                            </>
                          );
                        })()}
                        <div className="whytotal">
                          {/* Two decimals throughout: the row exists to be checked
                              by hand, and rounding the operands makes the sum
                              disagree with the total. */}
                          <span>
                            {fmt(c.proximity_score, 2)} × {(c.weights_applied ?? weights).proximity.toFixed(2)}
                            {" + "}{fmt(c.trajectory_score, 2)} × {(c.weights_applied ?? weights).trajectory.toFixed(2)}
                            {c.behaviour_score != null
                              ? <>{" + "}{fmt(c.behaviour_score, 2)} × {(c.weights_applied ?? weights).behaviour.toFixed(2)}</>
                              : <> (behaviour term omitted — unavailable)</>}
                          </span>
                          <b>= {fmt(c.final_suspect_score, 2)}</b>
                        </div>



                        {/* The independent test. Ranking asks "was it nearby and
                            behaving oddly?"; this asks "would its oil actually
                            have ended up where the oil is?" — a different
                            question that can and does disagree. */}
                        {(() => {
                          const key = whatIfKey(shownSpill?.ship_id ?? "", c.mmsi);
                          const res = whatIf[key];
                          const busy = whatIfBusy === key;
                          if (!res) {
                            return (
                              <button className="whatifbtn" disabled={busy}
                                      onClick={() => askWhatIf(c)}>
                                {busy ? "Simulating…" : `WHAT IF ${c.name} CAUSED THE SPILL?`}
                              </button>
                            );
                          }
                          if (!res.available) {
                            return (
                              <div className="whatifbox none" role="status">
                                {res.reason}
                                <button className="whatifbtn ghost" disabled={busy}
                                        onClick={() => askWhatIf(c)}>
                                  {busy ? "Retrying…" : "Try again"}
                                </button>
                              </div>
                            );
                          }
                          const consistent = res.within_envelope === true;
                          return (
                            <div className={"whatifbox " + (consistent ? "match" : "nomatch")}>
                              <div className="whatifhead">
                                <b>IF {res.name} WERE THE SOURCE</b>
                                <Badge tone={consistent ? "amber" : "blue"}>
                                  {consistent ? "CONSISTENT" : "NOT CONSISTENT"}
                                </Badge>
                              </div>
                              <div className="metrics three" style={{marginTop: 2}}>
                                <div>
                                  <small>Its AIS position then</small>
                                  <b>{showCoord(res.assumed_release.latitude, 3)}, {showCoord(res.assumed_release.longitude, 3)}</b>
                                </div>
                                <div>
                                  <small>Simulated slick now</small>
                                  <b>{showCoord(res.simulated_now.latitude, 3)}, {showCoord(res.simulated_now.longitude, 3)}</b>
                                </div>
                                <div>
                                  <small>Miss from observed</small>
                                  <b style={{color: consistent ? "var(--warn)" : "var(--ok)"}}>
                                    {fmt(res.miss_distance_km, 2)} km
                                  </b>
                                </div>
                              </div>
                              <p className="whatifsay">Tolerance: {fmt(res.consistency_radius_km ?? res.envelope_radius_km, 2)} km</p>
                              <CounterfactualLines result={res} />
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                );
              })}
              </div>
              {shownCandidates.length > 5 && (
                <div className="candidate-list-footer">
                  <span>{showAll ? shownCandidates.length : 5} of {shownCandidates.length} candidates</span>
                  <button className="reportbtn" aria-expanded={showAll}
                          aria-controls={candidateListId} onClick={() => setShowAll((value) => !value)}>
                    {showAll ? "Show top 5" : `View all ${shownCandidates.length} candidates`}
                  </button>
                </div>
              )}
            </>
          )}

          <div className="subtle" style={{marginTop: 8, fontSize: 12}}>Ranking does not establish responsibility.</div>
        </div>
  );
}
