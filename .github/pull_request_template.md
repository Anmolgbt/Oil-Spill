## What this changes

<!-- One or two sentences. What is different after this PR? -->

## Why

<!-- The problem, not the patch. -->

## How it was verified

<!-- What you actually ran, and what it printed. If you did not verify
     something, say so rather than leaving it implied. -->

- [ ] `cd backend && .venv/bin/python -m uvicorn main:app --port 8000` starts
- [ ] `POST /fleet/scan {"snapshot_id":"t1"}` returns `CLEAR`, `t3` returns `SPILL_DETECTED`
- [ ] `cd frontend && npm run build` passes (this includes the typecheck)
- [ ] Checked the change in a browser

## Honesty checklist

This project's central claim is that it never presents an estimate as an
observation. If this PR touches anything user-facing:

- [ ] No value the models cannot produce is rendered as a number
- [ ] Every projection is still labelled as one, and no disclaimer was weakened
- [ ] Anything back-derived is still visually distinct from anything measured
