# Demo walkthrough

Roughly six minutes. The story is: *we watch a fleet, the satellite finds oil, we
work backwards to who was there — and then we test that answer instead of
asserting it.*

## The guided run

Press **DEMO** in the header, or open `?demo=1`, and the app walks the
investigation in thirteen steps: the pass, the detection, the age, the
environmental reconstruction, the source region, the AIS search, the ranking,
why this vessel, the counterfactual, the forecast, the vessels in the way, **the
second detection**, and the report.

Two things about it are deliberate.

**It scrolls to and outlines the real panel.** Nothing in the walkthrough is a
duplicate of a screen — a duplicate is free to drift from the thing it depicts,
and a demo showing a stale copy of your own system is worse than no demo. Every
line of step text is assembled from what the panel already says: the stage
table's own wording, the assessment's reasons, the narrative beats. No claim is
written for the demo that the product does not already make.

**It visits both detections.** The first has a leading candidate whose identity
depends on a drift constant nobody measured; the second is where the system
declines to name anyone at all. Showing only the confident half would
misrepresent the system to exactly the audience the mode exists for.

The mode hides the pass selector and the uploader and nothing else. It does not
lock the interface — someone will interrupt to ask "can you click that?", and
**Next** re-establishes the step rather than the mode forbidding anything.

The rest of this document is the same walkthrough done by hand.

## Before you start

```bash
./run_demo.sh          # or the two commands in the README
```

Open http://localhost:5173 and wait for the first scan. It takes about **6
seconds** — it scores the whole AIS corpus once, then caches, so every later
scan is well under a second. **Load the page before you start presenting**, so
the audience never sees that wait.

## 1. What we are looking at (40 s)

Twelve vessels in a Gulf of Mexico traffic cluster, watched by satellite every
4 hours. The left panel is the fleet; the map is the area; the percentage on each
row is the CNN's confidence in its own call for that vessel's tile. Four vessels
are recorded without a name and show as `VESSEL <MMSI>` — that is what the corpus
knows about them, and unnamed records are normal in real AIS.

Say the provenance early, before you are asked: **the vessels are real** — real
MMSIs, real AIS tracks from the MarineCadastre corpus — **and the SAR imagery and
both models are real.** Two things are constructed: which vessels get an oily tile
on the last pass, and **that these vessels are at sea at the same time**.

On the second: the corpus samples transits, not continuous surveillance. A vessel
appears for one to two hours and leaves; at most four are simultaneously live at
any instant across the whole 88-day corpus. So each vessel's timestamps are
shifted onto a shared clock. No position is altered — only when it is said to
have happened. **Open HOW THIS WAS DERIVED and show them the banner.** Volunteering
this is much stronger than being caught by it.

If asked why not Indian waters: no open AIS corpus carries Indian-flag traffic at
this density. An earlier version of this repo invented an Indian fleet and had to
label every vessel synthetic. Real data was the better trade. Nothing in the
method is region-specific.

## 2. Clean passes (30 s)

Click **T1**. Green banner: *No oil signature in pass t1. 6 vessels checked.*
Every vessel blue and CLEAR. No investigation panels appear — nothing to
investigate.

Click **T2**. Clean again. This matters for the next step: it is what bounds the
age.

## 3. Detection (45 s)

Click **T3**. Red banner. Two vessels flip red:

- **NISALAH** — 97.75%
- **GRAND DOLPHIN** — 54.35%

(Unchanged from the six-vessel build: the same two vessels get the same two oil
tiles under the same seed.)

Both are real classifier outputs on real SAR tiles. Point at the 54% one: the
model is genuinely uncertain there, and the interface shows that rather than
rounding it into a confident answer.

Note what has *not* appeared: no source, no suspects, no forecast. A detection is
a fact; everything else is an inference, and the interface will not assert them
until asked.

## 4. Walk the investigation (90 s)

The findings are already on screen — the models run the moment a pass lands, and
pretending otherwise would be theatre. What the investigation bar shows is the
pipeline that ran; click **HOW THIS WAS DERIVED** for the five stages with their
limits in full. Read the second line under each stage — they are the point of the
whole design.

- **CHARACTERIZATION** — Max age **4 h**. The previous pass was clear, so the oil
  is at most one revisit old. *Derived from cadence, not measured from imagery.*
- **HINDCAST** — Probable source **28.497, −94.832**, released ~**17:39 UTC**.
  The amber line and marker appear on the map. *Kinematic, along an assumed
  vector — no wind, current or wave feed is connected.*
- **AIS SEARCH** — **360 fixes** in the window, **16.7 km** radius. *Filtered
  against an estimated source and an estimated window; both carry the hindcast's
  error.*
- **CANDIDATES** — eleven vessels ranked.

Point at the funnel row: **347 vessels in the AIS corpus → 12 monitored → 12 with
AIS in the release window → 11 within 16.7 km**. On the *second* detection that
last step drops to 5, rejecting 7. The radius is three drift-envelope radii, not
a round number someone picked — and until this build it was a flat 50 km, which
over a 21 × 38 km patch rejected nobody at all.

If someone asks about the drift envelope: **5.6 km radius, 98 km²** is the sea
area the oil could have reached. It is **not** the size of the slick. The
classifier produces no mask, so no slick area exists. This is the strongest
honesty point in the demo — do not skip it.

## 5. Why this vessel? (60 s)

Scroll to **WHY THIS VESSEL?** and click **NISALAH**:

```
PROXIMITY  × 0.40   87.20   contributes 34.88  ·  closest 2.14 km
TRAJECTORY × 0.30   71.25   contributes 21.38  ·  Approaching source
BEHAVIOUR  × 0.30   79.30   contributes 23.79  ·  Isolation Forest flagged 2 AIS fixes
87.20 × 0.40 + 71.25 × 0.30 + 79.30 × 0.30 = 80.04
```

The behaviour term is the Isolation Forest's own verdict on that vessel's real
track. Say the wording deliberately: *analytical association, not proof of
responsibility.*

Worth pointing out: **SAKAKA's trajectory term is 0.00** — a real measured zero,
drawn as a normal empty bar. If a term had come back with no verdict at all it
would be hatched and labelled instead. The interface does not let "no answer"
look like "zero".

If asked why the top score is only ~82 when it used to be ~86: the search radius
now comes from the drift envelope rather than a flat 50 km, and proximity is
`100 × (1 − distance / radius)`. A 50 km denominator over a 21 km patch pushed
every vessel into the top of the range; the derived radius spreads them out.
Same arithmetic, an honest denominator.

## 6. The strongest moment: test it (90 s)

The ranking's **#1 is MR CANOPUS at 81.9**, with NISALAH second at 80.0 and
GRAND DOLPHIN third at 78.9 — three vessels within three points. The ranking
alone cannot separate them. So test them.

Click **WHAT IF … CAUSED THE SPILL?** on each:

| Ranked | Vessel | Score | Counterfactual |
|---|---|---|---|
| #1 | MR CANOPUS | 81.9 | **2.88 km — CONSISTENT** |
| #2 | NISALAH | 80.0 | **4.37 km — CONSISTENT** |
| #3 | GRAND DOLPHIN | 78.9 | 9.72 km — not consistent |
| #6 | **ACHILLEAS** | 70.4 | **3.82 km — CONSISTENT** |

**Two things to dwell on.**

First, the third-ranked vessel is ruled out while the **sixth-ranked one is not**.
The ranking asks *was it nearby and behaving oddly?*; the counterfactual asks
*would its oil actually have ended up where the oil is?* Two different questions,
and an instrument that only ever agreed with itself would not be worth much.

Second, of eleven candidates only **three** are physically consistent. That is
the filter doing its real work — narrowing eleven plausible-looking vessels to
three.

Then select **GRAND DOLPHIN's** spill in RESPONSE PRIORITY. The banner above the
ranking reads **NO STRONG CANDIDATE — 0 of 5 candidates consistent with the
observation**, and explains that GRAND DOLPHIN's 70.54 measures proximity,
trajectory and behaviour but does not test whether its oil would have reached
the slick — and that here that test fails for all five.

The ranked list stays below it with its scores intact, so a judge can see the
70.54 *and* see why it is not support. The closing line is the one to read out:
*that is a statement about the evidence, NOT a finding that any vessel is
innocent.*

This is the most valuable screen in the demo. Two detections on one pass: one
where a leader exists but is not stable, one where the system refuses to name
anyone.

Note the colours: consistency is amber, ruling a vessel out is green. Clearing a
vessel is a successful test, not a failure.

## 6b. What the answer rests on (60 s)

Three panels, in this order, are the difference between a ranking and an
investigation.

**Under each counterfactual, one line of robustness.** MR CANOPUS is consistent
— but by **0.06 km** under the environment-derived drift, against 3.12 km under
the shipped one. Same verdict, completely different confidence. Say it plainly:
*this verdict is resting on an assumption nobody measured.*

**The DRIFT ASSUMPTION strip.** The system carries three drift vectors and they
disagree: the estimated source moves **4.56 km**, the forecast horizons up to
**18.98 km**, and re-ranking the same fleet against the environment-aware source
**puts NISALAH first instead of MR CANOPUS**. If someone asks whether that is
the environmental data doing something — no. **No environmental dataset is
loaded.** It is three constants disagreeing with each other, and the panel says
so twice.

**EVIDENCE QUALITY, inside each candidate.** Five streams graded on one axis:
*how much can this stream tell us*, never *how guilty is this vessel*. That is
why `UNAVAILABLE` sits outside the red-to-green scale rather than at the bottom
of it — a behaviour model that could not run is not evidence a vessel behaved
normally. On this demo every candidate's environmental stream is `UNAVAILABLE`,
and **IN PLAIN TERMS** says so in a sentence rather than leaving it out.

If you have time for one sentence here, use this one: *the system is designed to
be able to tell you it does not know.*

## 7. Respond (45 s)

**VESSELS AT RISK** now shows three vessels projected to enter — ACHILLEAS
(~0 min), MR CANOPUS (~35 min) and HARVEY HERD (~105 min). Select **HARVEY HERD**
and the recommendation appears; **OPTIMIZE ROUTE** draws it on the map:

- Heading **87° → 76° (−11°)**
- Distance **63.46 → 63.98 km (+0.52)**
- 3.0 km safety buffer · **CLEARS THE ZONE**

The green detour draws on the map. Label it: *simulated route avoidance, not
maritime navigation guidance* — no traffic separation, depth, weather or COLREGs.

## 8. Replay (45 s)

Click **PLAY INCIDENT**. The timeline runs T1 → detection → +12 h, with the
vessels moving along their real AIS tracks.

Watch the band under the scrubber change:

- **OBSERVED · no oil detected yet** — real AIS, nothing inferred
- **ESTIMATED · hindcast** — the slick is back-derived; nobody saw oil there
- **OBSERVED · satellite detection** — the one moment the oil was measured
- **PROJECTED · kinematic forecast** — past the last AIS fix and past the pass

A vessel past its last AIS fix goes hollow and dashed. The slick is dashed unless
it is the measured pass. Animating never makes an estimate look like an
observation.

The +24 h and +48 h horizons are listed in **WHERE THIS OIL GOES NEXT** rather
than replayed, so the observed window stays legible on the scrubber.

## 9. Report (30 s)

**Report** → the printable document: the five stages with their limits, the full
score arithmetic, **every counterfactual that was run including the one that
cleared a vessel**, the reroute, and provenance. Print / Save PDF works.

Say why the exculpatory result is in there: a report that only kept the
incriminating tests would be a case for the prosecution, not an instrument.

## Questions you should expect

**"Why no spill area?"** The classifier outputs one number. Area needs
segmentation, which is a different model we have not trained. We show the drift
envelope and label it as such.

**"Why is recall only 71%?"** It misses about one spill in four, while almost
never raising a false alarm. For monitoring that trade-off is the wrong way
round, and lowering the threshold is the obvious next step.

**"Are the ships real?"** Yes — real MMSIs and real AIS tracks; four are unnamed
in the corpus and shown as such. Two things are constructed: which of them gets
an oily tile on t3 (seeded, made before any model runs, never shown to the CNN),
and that they are at sea simultaneously — the corpus samples transits, so their
timestamps are shifted onto a shared clock. Positions are never altered.

**"Why not just use vessels that were actually there together?"** We measured
that. Across the whole 88-day corpus, at most four vessels are simultaneously
live at any instant, whatever pass interval you pick. Unshifted, ten of our
twelve would not have arrived by t1 and eleven would be hours stale by t3. The
shift is what makes a fleet observable from transit samples.

**"Why the Gulf of Mexico?"** No open AIS corpus has Indian-flag traffic at this
density. The method is region-agnostic; pointed at Indian coastal AIS it runs
unchanged.

**"Does this prove who did it?"** No, and the system never claims to. It narrows
a search from a whole fleet to the vessels that were plausibly present, then
tests each of them and reports when the test disagrees with the ranking.

**"Is the drift physics real?"** No. Three fixed vectors, all stated. The
counterfactual uses the hindcast's vector so it is a true inverse — which also
means it inherits that assumption rather than checking it.

## Fallback, if the backend dies mid-demo

The dashboard falls back to the stored result and the badge changes to **STORED
RESULT**. It keeps working. Nothing is presented as live when it is not.
