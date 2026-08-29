# DEMO_SCRIPT.md — 2-Minute Judge Walkthrough

**Setup before judges arrive:**
1. Terminal 1: `cd backend && uvicorn main:app --reload --port 8000`
2. Terminal 2: `cd frontend && npm run dev`
3. Open the frontend URL. Confirm the header badge says **API LIVE** (green)
   — if it says "LOCAL DEMO DATA" that's fine too, the demo still works
   identically, just without the backend running live.

---

### 0:00 — Open with the one-line story

> "A satellite spots an oil slick. The slick has drifted, so we trace it
> backwards through wind and current to find where and when it was
> probably released. Then we reconstruct which vessels were there using
> AIS, and score them with explainable evidence — never a verdict, always
> an investigation aid."

Click **Start Investigation**.

### 0:10 — Satellite scene + detection (auto)

The SAR scene appears, then the oil-spill mask overlay. Point at the KPI
strip: **94% oil probability, 12.8 km² area**. Mention the Look-Alike panel
on the right — "the system checks the dark patch isn't just a biofilm or a
low-wind area before accepting it as oil."

### 0:25 — Backward hindcast (auto-runs)

Point at the map: small particles converge from the observed slick toward
an amber region. "This is a simplified particle drift model — current plus
a fraction of the wind — running backward in time." Source Reconstruction
panel shows the **release-time window (10:20–11:10 UTC)** and **78%
confidence**. Emphasize: *"we never claim an exact origin point — only a
probabilistic region."*

### 0:45 — AIS traffic + SAR-AIS consistency (auto)

Vessel tracks appear on the map. Scroll to the **SAR–AIS Consistency
Check**: "5 vessels visible in the SAR scene, only 4 matched to AIS — one
vessel is flagged AIS-dark and requires manual investigation." This is
deliberately separate from the ranking below — it's a red flag, not a
verdict.

### 1:00 — Candidate ranking + explainable attribution

Point at the **Candidate Vessel Filtering** table — six vessels, ranked.
Click the top row, **MV Ocean Crest**. The Explainable Result panel opens:
**91/100, High confidence**, with the factor-contribution chart and a
plain-English evidence list (source overlap, release-time match,
trajectory similarity, speed anomaly, etc). Read the disclaimer out loud:
*"This score is an investigation aid, not a legal determination of
responsibility."*

*(Optional, if there's time: click "Replay Incident" to show the animated
event timeline reconstructing 10:00 → 14:00.)*

### 1:30 — Forward forecast

Scroll/point to **Forward Forecast**. The dashed blue polygon on the map
grows outward. Mention the at-risk areas list (coastline, fishing ground,
protected marine area) and the **Medium** forecast confidence badge.

### 1:50 — Investigation report

Click **Generate Report**. Show the consolidated, printable report —
satellite metadata, source reconstruction, top 3 candidates with scores,
evidence, forecast, and the disclaimer, all on one page. Mention **Print /
Save PDF**.

### Close (2:00)

> "Every number on this screen is explainable and every claim is hedged
> appropriately — that's the core innovation: an uncertainty-aware,
> end-to-end workflow from a satellite pixel to an investigable lead."

---

## Fallback notes

- If the auto-sequence needs to be paused or re-shown mid-demo, the left
  panel's **Investigation** checklist is clickable-adjacent — hindcast and
  forecast each have their own **Run / Pause / Reset** controls that work
  independently of the guided sequence.
- If a judge asks "what if the backend crashes right now" — kill the
  `uvicorn` process live. The app keeps working identically (header badge
  switches to "LOCAL DEMO DATA"). This is a good, safe flex if you have
  time.
