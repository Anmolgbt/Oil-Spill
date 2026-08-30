from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.fleet_pipeline import load_fleet, run_fleet_scan
from services.snapshots import get_available_snapshots, get_latest_snapshot

router = APIRouter(tags=["fleet"], prefix="/fleet")


class ScanRequest(BaseModel):
    snapshot_id: Optional[str] = None


@router.get("")
def fleet():
    """The monitored vessels and the satellite passes available."""
    data = load_fleet()
    return {
        "scenario_day": data.get("scenario_day"),
        "snapshot_times": data.get("snapshot_times", {}),
        "available_snapshots": get_available_snapshots(),
        "latest_snapshot": get_latest_snapshot(),
        "note": data.get("note"),
        "ships": [
            {k: v for k, v in s.items() if k != "track"} for s in data["ships"]
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
