from fastapi import APIRouter
from models.schemas import HindcastRequest
from services.drift_model import run_hindcast
router=APIRouter(tags=["hindcast"])
@router.post("/hindcast")
def hindcast(req:HindcastRequest):
    return run_hindcast(req.hours or 4, req.n_particles or 40)
