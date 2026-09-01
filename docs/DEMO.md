# Demo walkthrough

Roughly five minutes. The story is: *we watch a fleet, the satellite finds oil,
we work backwards to who was there.*

## Before you start

```bash
./run_demo.sh          # or the two commands in the README
```

Open http://localhost:5173 and wait for the first scan (~3 s — it scores the AIS
corpus once, then caches). Check the badge reads **LIVE INFERENCE**.

## 1. What we are looking at (30 s)

Five vessels off the Gujarat coast, watched by satellite every 8 hours. The left
panel is the fleet; the map is the area; the percentage on each row is the CNN's
confidence in its own call for that vessel's tile.

Say plainly: **the vessels are synthetic, the SAR imagery and both models are
real.** Getting this in early is better than being asked.

## 2. A clean pass (30 s)

Click **T0**. Green banner: *no oil signature, 5 vessels checked*. Every vessel
blue and CLEAR. No investigation panels appear — nothing to investigate.

Click **T1**. Clean again. This matters for the next step.

## 3. Detection (45 s)

Click **T2**. Red banner. Two vessels flip red:

- MV Dwarka Prime — **97.75%**
- MV Sagar Deep — **54.35%**

Both are real classifier outputs on real SAR tiles. Point at the 54% one: the
model is genuinely uncertain there, and the interface shows that rather than
rounding it into a confident answer.

## 4. Characterising the spill (60 s)

Click **MV Dwarka Prime**. The right panel shows its SAR tile and:

- **Max age 8 h** — the previous pass was clear, so the oil is at most one revisit
  old. Derived from cadence, not assumed.
- **Probable source 20.479, 68.121** — traced back along the drift vector.
- **Search zone 12 km · 452 km²** — where the oil could have reached.
- **Slick area — not shown.** If asked: the CNN is a classifier, not a
  segmentation model, so no mask and therefore no area exists. The 452 km² is the
  search zone, not the slick. This is the strongest honesty point in the demo.

## 5. Attribution (60 s)

The AIS search ran ±2 h around the estimated release, clipped to 50 km — that is
the irrelevant-traffic filter the problem statement asks for. One vessel survived.

**MV Dwarka Prime — 66.2 / 100**: proximity 47.2, trajectory 79.5, behaviour 78.2.
The behaviour term is the Isolation Forest's own verdict; this vessel slowed to
1.4 kt and changed course near the estimated source, which is what it flagged.

Say the wording deliberately: *analytical association, not proof of
responsibility.*

## 6. The second detection (45 s)

Click **MV Sagar Deep**. It has its own source (21.054, 65.814 — 250 km away) and
its own result: **no vessels within 50 km**.

This is worth dwelling on. Two separate findings, each characterised on its own
terms. A vessel showing oil is not automatically a suspect — attribution depends
on where it was 8 hours *earlier*, not where the slick is now. That gap is exactly
why hindcasting exists.

## 7. Forecast and the map (30 s)

The left panel projects +6/12/24/48 h. Label it a **kinematic projection** — no
wind, current or wave data is involved, and the map footer says so.

Open the **ⓘ** button on the map for the legend: solid amber traces drift
backwards, dotted blue projects forwards, the dashed red circle is the possible
affected area.

## Questions you should expect

**"Why no spill area?"** The classifier outputs one number. Area needs
segmentation, which is a different model we have not trained. We show the drift
envelope instead and label it as such.

**"Why is recall only 71%?"** It misses about one spill in four, while almost
never raising a false alarm. For monitoring that trade-off is the wrong way round,
and lowering the threshold is the obvious next step.

**"Are the ships real?"** No. The AIS corpus we have is US Gulf traffic with no
Indian-flag vessels, so an Indian fleet could not be drawn from it. The imagery
and both models are real; the vessel identities and tracks are generated.

**"Does this prove who did it?"** No, and the system never claims to. It narrows
a search from a whole fleet to the vessels that were plausibly present.

## Fallback, if the backend dies mid-demo

The dashboard falls back to the stored result and the badge changes to **STORED
RESULT**. It keeps working. Nothing is presented as live when it is not.
