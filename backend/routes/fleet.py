import json
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from services.counterfactual import test_candidate
from services.ingest import create_pass, delete_pass, next_snapshot_id
from services.fleet_pipeline import load_fleet, run_fleet_scan
from services.snapshots import get_available_snapshots, get_latest_snapshot
from services.t3_simulation import GROUND_TRUTH_FILE

router = APIRouter(tags=["fleet"], prefix="/fleet")


class ScanRequest(BaseModel):
    snapshot_id: Optional[str] = None


class CounterfactualRequest(BaseModel):
    """Everything the test needs, taken from the scan that raised the detection.

    Deliberately explicit rather than re-deriving from a snapshot_id: this is
    pure geometry over AIS the fleet already holds, and re-running the scan
    would put the CNN over every vessel again to answer a question that needs
    no model at all.
    """
    mmsi: int
    release_at: str
    spill_latitude: float
    spill_longitude: float
    age_hours: float
    # The map's affected-area circle. Passed for CONTEXT only — the test derives
    # its own threshold from the drift it actually uses, because judging a drift
    # computed one way against a circle sized another way is what this used to
    # do and could not be defended.
    affected_area_radius_km: Optional[float] = None
    # Override for the derived threshold. Tests use it; callers should not.
    envelope_radius_km: Optional[float] = None
    source_latitude: Optional[float] = None
    source_longitude: Optional[float] = None


@router.get("")
def fleet():
    """The monitored vessels and the satellite passes available."""
    data = load_fleet()
    return {
        "region": data.get("region"),
        "pass_interval_hours": data.get("pass_interval_hours"),
        "snapshot_times": data.get("snapshot_times", {}),
        "available_snapshots": get_available_snapshots(),
        "latest_snapshot": get_latest_snapshot(),
        "note": data.get("note"),
        # Both track arrays are dropped: this endpoint is the roster, and each
        # ship carries ~80 raw fixes plus a longer interpolated display track.
        # Positions for a given pass come from /fleet/scan instead.
        "ships": [
            {k: v for k, v in s.items() if k not in ("track", "display_track")}
            for s in data["ships"]
        ],
    }


@router.post("/scan")
def scan(req: ScanRequest = ScanRequest()):
    """
    Run the CNN over every monitored ship in one satellite pass.

    Returns the whole fleet either way. Hindcast, AIS ranking and forecast are
    included only when oil is actually detected.
    """
    try:
        result = run_fleet_scan(req.snapshot_id)
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Missing data or model artifact: {exc}")
    except ImportError as exc:
        raise HTTPException(503, f"Inference dependencies unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(400, f"Scan failed: {type(exc).__name__}: {exc}")

    if result.get("status") == "NO_SNAPSHOT":
        raise HTTPException(404, result["message"])
    return result


@router.post("/counterfactual")
def counterfactual(req: CounterfactualRequest):
    """
    Test one candidate against the observation: "what if THIS vessel caused it?"

    Runs the hindcast's drift vector forward from the vessel's real AIS position
    at the estimated release time, and reports how far the result lands from
    where oil was actually seen. A distance, not a verdict — a large miss is an
    exculpatory result and is returned as plainly as a small one.
    """
    ships = load_fleet()["ships"]
    ship = next((s for s in ships if s.get("mmsi") == req.mmsi), None)
    if ship is None:
        raise HTTPException(404, f"No monitored vessel with MMSI {req.mmsi}.")

    source = (None if req.source_latitude is None or req.source_longitude is None
              else {"latitude": req.source_latitude, "longitude": req.source_longitude})
    try:
        return test_candidate(
            ship,
            release_at=req.release_at,
            spill_lat=req.spill_latitude,
            spill_lon=req.spill_longitude,
            age_hours=req.age_hours,
            envelope_radius_km=req.envelope_radius_km,
            affected_area_radius_km=req.affected_area_radius_km,
            source=source,
        )
    except ValueError as exc:
        raise HTTPException(400, f"Could not run counterfactual: {exc}")


@router.post("/passes")
async def upload_pass(files: list[UploadFile] = File(...)):
    """
    Create the next satellite pass from uploaded tiles.

    Drop in a folder of SAR images and they become t4 (then t5, ...), which the
    existing pass discovery picks up with no configuration. Scan it like any
    other pass with POST /fleet/scan {"snapshot_id": "t4"}.

    There is no ground truth for an uploaded pass and none is invented — the
    response says so, and nothing here inspects the images beyond checking that
    they decode.
    """
    if not files:
        raise HTTPException(400, "No files in the upload.")
    if len(files) > 64:
        raise HTTPException(413, "Too many files (limit 64).")

    payload = []
    for f in files:
        payload.append((f.filename or "unnamed", await f.read()))

    try:
        return create_pass(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except OSError as exc:
        raise HTTPException(500, f"Could not write the pass: {exc}")


@router.get("/passes/next")
def peek_next_pass():
    """Which id the next upload would take, so the UI can name it before sending."""
    return {"next_snapshot_id": next_snapshot_id(),
            "existing": get_available_snapshots()}


@router.delete("/passes/{snapshot_id}")
def remove_pass(snapshot_id: str):
    """Delete an uploaded pass. The three that ship with the repo are protected."""
    try:
        return delete_pass(snapshot_id)
    except ValueError as exc:
        raise HTTPException(403, str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))


@router.get("/t3-ground-truth-debug")
def t3_ground_truth_debug():
    """
    INTERNAL/DEBUG ONLY — the seeded oil/no-oil assignment for pass t3.

    Never consulted by the CNN or by run_fleet_scan(); this exists only so a
    demo run can be checked against what the simulation actually assigned,
    and so a given SIMULATION_SEED can be shown to replay identically.
    """
    if not GROUND_TRUTH_FILE.is_file():
        raise HTTPException(404, "No t3 ground truth on disk yet — run scripts/build_fleet.py.")
    return json.loads(GROUND_TRUTH_FILE.read_text())
