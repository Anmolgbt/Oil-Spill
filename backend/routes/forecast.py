from fastapi import APIRouter
from models.schemas import ForecastRequest
from services.drift_model import run_forecast
from services.data_store import get_incident
router=APIRouter(tags=["forecast"])
@router.post("/forecast")
def forecast(req:ForecastRequest):
    inc=get_incident()
    return {"polygons":run_forecast(req.hours)["features"],"confidence":inc["forecast"]["confidence"],"at_risk_areas":inc["forecast"]["at_risk_areas"]}
