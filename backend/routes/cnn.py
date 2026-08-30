from fastapi import APIRouter, File, HTTPException, UploadFile

from ml.cnn_inference import model_info, predict_image

router = APIRouter(tags=["ai-cnn"], prefix="/ai/cnn")

MAX_BYTES = 20 * 1024 * 1024


@router.get("/status")
def cnn_status():
    """Checkpoint, device and load report. Does not require an image."""
    return model_info()


@router.post("/predict")
async def cnn_predict(file: UploadFile = File(...)):
    """
    Run the trained CNN on an uploaded image.

    Binary classification only: returns a class and the softmax confidence of
    that class. No mask, boundary or area is produced, because the model does
    not perform segmentation.
    """
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty upload.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image larger than 20 MB.")

    try:
        result = predict_image(image_bytes=data)
    except ImportError as exc:
        raise HTTPException(503, f"Inference dependencies unavailable: {exc}")
    except FileNotFoundError:
        raise HTTPException(503, "Model checkpoint not found in models_artifacts/.")
    except Exception as exc:
        raise HTTPException(400, f"Could not run inference: {type(exc).__name__}: {exc}")

    return {"filename": file.filename, **result}
