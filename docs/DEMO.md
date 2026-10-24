# Demo walkthrough

About six minutes. The story: *we watch a fleet, the satellite finds oil, we work
backwards to who was there, and then we test that answer instead of asserting it.*

Every number below is what the shipped build shows on pass T3. Vessels appear under
pseudonyms (Vessel A–L): their tracks are real AIS, but the incident is constructed, so
no real ship is named as a suspect.

## Before you start

```bash
./run_demo.sh          # or the two commands in the README
```

Open http://localhost:5173 and wait for the first scan. It takes about **6 seconds**,
because the AIS corpus is scored once and then cached. Every later scan is well under a
second. **Load the page before you start presenting.**

## 1. What we are looking at (40 s)

Twelve vessels in a Gulf of Mexico traffic cluster, observed by satellite every 4 hours.
The left panel is the fleet, and the map shows the area. The percentage on each row is
the CNN's calibrated confidence in its own call for that vessel's tile. It never rounds
up to 100%: the strongest calls show as `>99%`.

Give the provenance early, before anyone asks:

- **Real:** the AIS tracks (MarineCadastre.gov), the SAR imagery (the CSIRO Sentinel-1
  dataset) and both trained models.
- **Constructed:** which vessels get an oily tile on the last pass, and the fact that
  these vessels are at sea at the same time.
- **Pseudonymised:** the vessel names and MMSIs.

On co-presence: the corpus samples transits, not continuous surveillance. Across all 88
days, the best window holds 3 of 347 vessels with a fix at all three passes. So each
vessel's timestamps are shifted onto a shared clock. No position is altered. Open **How
this was derived** to show where this is stated. Volunteering it is much stronger than
being caught by it.

## 2. Clean passes (30 s)

Click **T1**. Green banner: *No oil signature in pass t1. 12 vessels checked.* No
investigation panels appear, because there is nothing to investigate.

Click **T2**. It is clean again. This matters for the next step, because it is what bounds
the age.

## 3. Detection (45 s)

Click **T3**. The banner turns red and two vessels flip:

- **Vessel B**: `>99.9%` calibrated probability
- **Vessel A**: 98%

Both are real classifier outputs on real SAR tiles. Say plainly what that does and does
not mean. These tiles come from the same public dataset the model was trained on, so this
shows the pipeline working end to end. It is **not** evidence that the detector is 99%
accurate. The held-out figure is under *Questions you should expect*.

## 4. Walk the investigation (90 s)

The models run the moment a pass lands, so the findings are already on screen. Click
**How this was derived** for the five stages, and read the second line under each one.
Those lines are the point of the whole design.

- **Characterization:** maximum age **4 h**. The previous pass was clear, so the oil is at
  most one pass interval old. *Derived from cadence, not measured from imagery.*
- **Hindcast:** probable source **28.497, −94.832**, released around **17:39 UTC**. *This is
  kinematic, along an assumed vector. No measured wind or current is loaded.*
- **AIS search:** 360 fixes in the window and a **16.7 km** radius. *Both the source and the
  window are estimates.*
- **Candidates:** eleven vessels ranked.

The radius is three drift-envelope radii, not a round number. On the second detection it
rejects 7 of 12 vessels.

If someone asks about the envelope: **5.58 km radius, 97.7 km²** is the sea area the oil
could have reached. It is **not** the size of the slick. The classifier produces no mask,
so no slick area exists. This is the strongest honesty point in the demo, so do not skip
it.

## 5. Why this vessel? (60 s)

In **Top candidates**, select **Vessel K**, the top-ranked vessel:

```
Proximity   88.4 · 40% weight      closest approach 1.95 km at 16:32 UTC
Trajectory  72.8 · 30% weight      approaching source
Behaviour   97.5 · 30% weight      Isolation Forest flagged 1 AIS fix
0.40 × 88.37 + 0.30 × 72.84 + 0.30 × 97.47 = 86.44
```

The behaviour term is the Isolation Forest's own verdict on that vessel's real track. Say
the wording deliberately: *analytical association, not proof of responsibility.*

## 6. The strongest moment: test it (90 s)

The ranking only says who was nearby and moving unusually. It does not say whether that
vessel's oil could have reached the slick. So test it. Click **Test source consistency**
for each:

| Rank | Vessel | Score | Counterfactual (threshold 6.00 km) |
|---|---|---|---|
| #1 | Vessel K | 86.4 | **2.88 km, consistent** |
| #2 | Vessel B | 73.5 | **4.37 km, consistent** |
| #3 | Vessel H | 72.7 | 9.15 km, not consistent |
| #4 | **Vessel L** | 68.8 | **3.82 km, consistent** |

There are two things to dwell on:

1. **The third-ranked vessel is ruled out while the fourth-ranked one is not.** The
   ranking asks *was it nearby and moving oddly?* The counterfactual asks *would its oil
   have ended up where the oil is?* They are different questions.
2. **The verdict rests on an assumption.** Vessel K is consistent by 3.12 km under the
   kinematic drift, but by only **0.06 km** under the environment-derived drift. Under that
   drift, **Vessel L ranks first instead of Vessel K**. The evidence assessment calls this
   *leading candidate unstable*.

Then select **Vessel A's** spill in **Response priority**. None of its five candidates is
consistent with the observation under either drift. The report states *no strong
candidate*, even though the ranking still shows a leader at 50.17. Read out the closing
line: *that is a statement about the evidence, NOT a finding that any vessel is
innocent.*

If you have time for one sentence, use this one: *the system is designed to be able to
tell you it does not know.*

## 7. Respond (45 s)

**Recommended actions** lists investigate, alert, contain and verify. The verify step asks
for inspection and oil sampling: *the ranking alone is not grounds for detention.*

**Vessels at risk** shows which vessels are projected to enter a risk zone within 6 h.
Across both spills there are three: Vessel L (already inside), Vessel K (about 35 min)
and Vessel C (about 105 min). Select **Vessel C** and press **Optimize route**:

- Heading **87° → 75° (−12°)**
- Distance **63.46 → 64.05 km (+0.59)**
- 3.0 km safety buffer · **clears the zone**

Label it: *simulated route, requires navigation review*. It ignores traffic separation,
depth, weather and COLREGs.

## 8. Replay (45 s)

Press **Play timeline**. The incident runs from T1 through the detection to the forecast,
with vessels moving along their real AIS tracks. The bands under the scrubber separate
what was **observed** (AIS, and the one satellite detection), what was **estimated** (the
hindcast) and what is **projected** (the forecast). A vessel past its last AIS fix is drawn
hollow. Animation never makes an estimate look like an observation.

## 9. Report (30 s)

**Report** opens the printable record. It contains the stages with their limits, the score
arithmetic, **every counterfactual that was run, including the ones that cleared a
vessel**, the evidence assessment, the reroute and the provenance. Explain why the
exculpatory results are kept: a report that only kept incriminating tests would be a case
for the prosecution, not an instrument.

## Questions you should expect

**"Why no spill area?"** The classifier outputs one number per tile. Area needs a
segmentation model, which we have not trained. We show the drift envelope and label it as
such.

**"How accurate is the detector?"** On 574 tiles from 451 satellite scenes it never saw, it
reaches 96.3% accuracy, 94.3% precision, 94.8% recall and ROC-AUC 0.993. Roughly one
alarm in 18 is false and one spill in 19 is missed. Say "about 95%": the 95% interval on
recall is 90.7–98.1%. The split is grouped by scene. A perceptual-hash audit found 58 test
tiles that look like training tiles; removing them leaves accuracy at 96.1%.

**"Is the demo itself proof that it works?"** No, and say so first. The demo's tiles come
from the training dataset. The 574-tile result is the measurement.

**"Are the ships real?"** The tracks are real AIS, shown under pseudonyms. Two things are
constructed: which vessels get an oily tile on T3 (a seeded draw made before any model
runs) and their simultaneity (timestamps shifted onto a shared clock). Positions are never
altered.

**"Why the Gulf of Mexico?"** No open AIS corpus has Indian coastal traffic at this
density. The method is region-agnostic. The paper sets out a roadmap for Indian waters:
Sentinel-1 over the Arabian Sea, INCOIS currents, IMD winds and Coast Guard workflows.

**"Does this prove who did it?"** No, and the system never claims to. It narrows a search
from a whole fleet to the vessels that were plausibly present, tests each of them, and
reports when the test disagrees with the ranking.

**"Is the drift physics real?"** It is a stated first-order approximation: current plus 3%
windage, with fixed inputs. There are three vectors, and how much they disagree is reported
on every scan. A gridded reanalysis can replace the fixed inputs without a code change.

## Fallback, if the backend dies mid-demo

The dashboard falls back to the stored result, and the badge changes to **Stored result**.
It keeps working. Nothing is presented as live when it is not.
