from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.investigation import (DEFAULT_SOURCE_TIME, DEFAULT_SPILL_LAT,
                                    DEFAULT_SPILL_LON, run_live_investigation)

router = APIRouter(tags=["live-pipeline"], prefix="/ai")

MAX_BYTES = 20 * 1024 * 1024


@router.post("/investigate")
async def investigate(
    file: Optional[UploadFile] = File(None),
    spill_lat: Optional[float] = Form(None),
    spill_lon: Optional[float] = Form(None),
    source_time: Optional[str] = Form(None),
):
    """
    Run the full investigation with both trained models.

    Upload a satellite image, or omit it to use the bundled sample scene. The
    spill coordinate is an input: the CNN classifies, it does not geolocate.
    Defaults reproduce the notebook's completed case.
    """
    image_bytes = None
    image_path = None

    if file is not None:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(400, "Empty upload.")
        if len(image_bytes) > MAX_BYTES:
            raise HTTPException(413, "Image larger than 20 MB.")
    else:
        from core.config import AI_OUTPUT_DIR
        image_path = AI_OUTPUT_DIR / "samples" / "class_1.jpg"
        if not image_path.is_file():
            raise HTTPException(400, "No image supplied and no sample scene available.")

    try:
        return run_live_investigation(
            image_bytes=image_bytes, image_path=image_path,
            spill_lat=spill_lat, spill_lon=spill_lon, source_time=source_time,
        )
    except ImportError as exc:
        raise HTTPException(503, f"Inference dependencies unavailable: {exc}")
    except FileNotFoundError as exc:
        raise HTTPException(503, f"Model artifact missing: {exc}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(400, f"Pipeline failed: {type(exc).__name__}: {exc}")


@router.get("/investigate/defaults")
def investigate_defaults():
    """Inputs the pipeline falls back to — the notebook's completed-case values."""
    return {
        "spill_lat": DEFAULT_SPILL_LAT,
        "spill_lon": DEFAULT_SPILL_LON,
        "source_time": DEFAULT_SOURCE_TIME,
        "note": ("The CNN does not geolocate, so the spill coordinate is an "
                 "input. These defaults reproduce the notebook's completed case."),
    }
