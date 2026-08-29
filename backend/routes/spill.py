from fastapi import APIRouter
from models.schemas import DetectSpillRequest
from services.spill_detection import detect_spill
from services.lookalike_filter import run_filter
from services.data_store import get_incident
router=APIRouter(tags=["spill"])
@router.post("/detect-spill")
def detect(req:DetectSpillRequest):
    return {"detection":detect_spill(scene_id=req.scene_id),"lookalike":run_filter()}
@router.post("/characterize-spill")
def characterize():
    inc=get_incident()
    return {"metrics":inc["spill_metrics"],"source_reconstruction":inc["source_reconstruction"]}
