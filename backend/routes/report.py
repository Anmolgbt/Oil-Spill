from fastapi import APIRouter
from services.report_service import get_report
router=APIRouter(tags=["report"])
@router.get("/report/{incident_id}")
def report(incident_id:str): return get_report()
