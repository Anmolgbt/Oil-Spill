from fastapi import APIRouter, HTTPException

from models.schemas import SimulationRequest
from services.pipeline import run_investigation
from services.simulation_service import get_available_snapshots, get_latest_snapshot

router = APIRouter(tags=["pipeline"])


@router.post("/simulate")
def simulate(req: SimulationRequest):
    """Run the full spill-first investigation over one satellite pass."""
    result = run_investigation(req.snapshot_id)
    if result["status"] == "NO_SNAPSHOT":
        raise HTTPException(404, result["message"])
    return result


@router.get("/snapshots")
def snapshots():
    """Available satellite passes, oldest first."""
    return {"snapshots": get_available_snapshots(), "latest": get_latest_snapshot()}
