from fastapi import APIRouter, HTTPException
from models.schemas import AttributeRequest
from services.vessel_attribution import rank_candidates, explain
router=APIRouter(tags=["attribution"])
@router.post("/attribute")
def attribute(req:AttributeRequest):
    result=explain(req.vessel_id)
    if result is None: raise HTTPException(404,"Unknown vessel_id")
    return result
@router.get("/attribute/ranked")
def ranked(): return {"candidates":rank_candidates()}
