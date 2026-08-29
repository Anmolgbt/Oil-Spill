from fastapi import APIRouter
from services import ais_service
router=APIRouter(tags=["ais"])
@router.post("/ais/candidates")
def ais_candidates(): return ais_service.get_candidates()
@router.get("/ais/tracks")
def ais_tracks(): return ais_service.get_tracks()
@router.get("/ais/consistency-check")
def ais_consistency_check(): return ais_service.sar_ais_consistency_check()
