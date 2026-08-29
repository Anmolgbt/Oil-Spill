from fastapi import APIRouter
from services.data_store import get_incident
router=APIRouter(tags=["incident"])
@router.get("/incident/{incident_id}")
def incident(incident_id:str):
    return get_incident()
