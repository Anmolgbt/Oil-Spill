from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ml.ais_inference import model_info, predict_track

router = APIRouter(tags=["ai-ais"], prefix="/ai/ais")

MAX_RECORDS = 50000


class AisPredictRequest(BaseModel):
    records: List[Dict[str, Any]]
    mmsi: Optional[int] = None


@router.get("/status")
def ais_status():
    """Artifact status, feature order and model parameters."""
    return model_info()


@router.post("/predict")
def ais_predict(req: AisPredictRequest):
    """
    Score one vessel's AIS history with the saved Isolation Forest.

    Needs at least two valid, time-ordered records: the notebook drops each
    vessel's first fix because it has no predecessor to difference against.
    """
    if not req.records:
        raise HTTPException(400, "No AIS records supplied.")
    if len(req.records) > MAX_RECORDS:
        raise HTTPException(413, f"Too many records (limit {MAX_RECORDS}).")

    try:
        return predict_track(req.records, mmsi=req.mmsi)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except FileNotFoundError:
        raise HTTPException(503, "Model or scaler not found in models_artifacts/.")
    except ImportError as exc:
        raise HTTPException(503, f"Inference dependencies unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(400, f"Could not run inference: {type(exc).__name__}: {exc}")
