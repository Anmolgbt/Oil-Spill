from fastapi import APIRouter

from services.stored_result import (get_investigation, load_ai_output,
                                        load_cnn_metrics, model_artifacts)

router = APIRouter(tags=["ai-result"])


@router.get("/ai-result")
def ai_result():
    """The completed AI investigation, adapted for the dashboard."""
    return get_investigation()


@router.get("/ai-result/raw")
def ai_result_raw():
    """The stored AI output exactly as handed off, with no adaptation."""
    return load_ai_output()


@router.get("/ai-result/metrics")
def ai_result_metrics():
    """CNN validation metrics and confusion matrix."""
    return load_cnn_metrics()


@router.get("/ai-result/models")
def ai_result_models():
    """Which trained artifacts are present, and whether inference is live."""
    return model_artifacts()
