"""
Live inference for the trained oil-spill CNN.

The model, its preprocessing and its decision rule all come from the training
notebook (OILTRACE_CNN_Final.ipynb) through ONE shared implementation,
ml/oiltrace_cnn.py - the same file the notebook wrote and trained with - so a
prediction made by this backend matches a prediction made in the notebook.
Nothing is re-derived here:

    architecture   oiltrace_cnn.OilSpillCNN   (4 blocks of Conv-BN-ReLU x2, global
                                               average pooling, dropout head)
    preprocessing  oiltrace_cnn.build_transforms
                   Resize 224 -> Grayscale(3) -> ToTensor -> Normalize(0.5, 0.5)
    checkpoint     artifacts/oilspill_cnn_best.pth    (plain state_dict)
    settings       artifacts/cnn_config.json          (image size, normalisation,
                                                       temperature, threshold)

Decision rule - all three values were fitted on the VALIDATION split only:

    probability    softmax(logits / temperature)[oil]      temperature scaling
    verdict        OIL SPILL when probability >= decision_threshold (0.57)
    confidence     the calibrated probability of the verdict that was returned

Evaluation (artifacts/cnn_config.json, data/ai_output/cnn_validation_metrics.json):
a scene-grouped split, so no satellite scene contributes tiles to more than one of
train / validation / test. The reported test metrics are on scenes the model never
saw, and were computed WITHOUT test-time augmentation - which is why none is
applied here.

The model is a BINARY CLASSIFIER. It returns a class and a probability and nothing
else - no mask, no boundary, no area. (ml/oiltrace_cnn.py also contains an
approximate Grad-CAM mask helper; it is deliberately not exposed by this backend,
because a heat-map region is not a segmentation and the product does not claim
one.)
"""
import io
import json
import time

from core.config import MODEL_ARTIFACTS_DIR

CHECKPOINT = MODEL_ARTIFACTS_DIR / "oilspill_cnn_best.pth"
CONFIG_FILE = MODEL_ARTIFACTS_DIR / "cnn_config.json"

CLASS_NAMES = {0: "NO OIL SPILL", 1: "OIL SPILL"}

_model = None
_device = None
_load_report = None
_config = None


def _torch():
    """Import torch lazily so the app still starts when it is not installed."""
    import torch
    return torch


def config():
    """The training run's settings, read once from cnn_config.json."""
    global _config
    if _config is None:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            _config = json.load(f)
    return _config


def _shared():
    """The model/transform implementation shared with the training notebook."""
    from ml import oiltrace_cnn
    return oiltrace_cnn


def build_model():
    """The architecture the notebook trained."""
    return _shared().OilSpillCNN(dropout=config().get("dropout", 0.30))


def build_transform():
    """The evaluation-time preprocessing pipeline the notebook used."""
    cfg = config()
    size = int(cfg["image_size"])
    return _shared().build_transforms(size, cfg["normalize_mean"], cfg["normalize_std"],
                                      train=False)


def get_device():
    """CUDA when available, CPU otherwise. The app must run without CUDA."""
    torch = _torch()
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_model():
    """
    Load the checkpoint once and keep it. Returns (model, device, report).

    The report records missing/unexpected state_dict keys so a checkpoint that
    does not match the architecture is visible rather than silently tolerated.
    """
    global _model, _device, _load_report
    if _model is not None:
        return _model, _device, _load_report

    torch = _torch()
    cfg = config()
    device = get_device()
    model = build_model()

    state = torch.load(CHECKPOINT, map_location=device)
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]

    result = model.load_state_dict(state, strict=False)
    missing = list(getattr(result, "missing_keys", []))
    unexpected = list(getattr(result, "unexpected_keys", []))

    model.to(device)
    model.eval()

    _model, _device = model, device
    _load_report = {
        "checkpoint": CHECKPOINT.name,
        "device": str(device),
        "missing_keys": missing,
        "unexpected_keys": unexpected,
        "loaded_cleanly": not missing and not unexpected,
        "parameters": sum(p.numel() for p in model.parameters()),
        "decision_threshold": cfg["decision_threshold"],
        "temperature": cfg["temperature"],
        "input_size": [int(cfg["image_size"])] * 2,
    }
    return _model, _device, _load_report


def predict_image(image_bytes=None, image_path=None):
    """
    Run the trained CNN on one image.

    Returns the verdict, the calibrated probability of that verdict, the full
    probability pair, and timing and provenance. Nothing here is fixed or derived:
    the probability is the softmax of the model's own logits at the fitted
    temperature, and the verdict is that probability against the decision
    threshold chosen on the validation split.
    """
    from PIL import Image

    torch = _torch()
    model, device, _ = load_model()
    cfg = config()
    threshold = float(cfg["decision_threshold"])
    temperature = float(cfg["temperature"])

    if image_bytes is not None:
        image = Image.open(io.BytesIO(image_bytes))
    elif image_path is not None:
        image = Image.open(image_path)
    else:
        raise ValueError("predict_image needs image_bytes or image_path")

    original_size = image.size
    # Training opened every tile with .convert("L"); the transform then replicates
    # that single channel to three. Matching it keeps live and trained input equal.
    image = image.convert("L")

    input_tensor = build_transform()(image).unsqueeze(0).to(device)

    started = time.perf_counter()
    with torch.no_grad():
        logits = model(input_tensor)
        probabilities = torch.softmax(logits / temperature, dim=1)
    elapsed_ms = (time.perf_counter() - started) * 1000

    probs = probabilities[0].tolist()
    oil_probability = probs[1]
    predicted_class = 1 if oil_probability >= threshold else 0
    confidence = probs[predicted_class]

    return {
        "prediction": CLASS_NAMES[predicted_class],
        "class_id": predicted_class,
        "confidence": confidence,
        "probabilities": {CLASS_NAMES[i]: p for i, p in enumerate(probs)},
        "oil_probability": oil_probability,
        "decision_threshold": threshold,
        "temperature": temperature,
        "inference_ms": round(elapsed_ms, 2),
        "device": str(device),
        "input_size": [int(cfg["image_size"])] * 2,
        "original_size": list(original_size),
        "model": "OilSpillCNN — binary classifier",
        "performs_segmentation": False,
        "provenance": {"source": "ml_model", "model_version": CHECKPOINT.name},
    }


def model_info():
    """Checkpoint / device status, without requiring an image."""
    try:
        _, device, report = load_model()
        return {"available": True, **report}
    except Exception as exc:                      # torch missing, bad checkpoint
        return {
            "available": False,
            "checkpoint": CHECKPOINT.name,
            "checkpoint_present": CHECKPOINT.is_file(),
            "error": f"{type(exc).__name__}: {exc}",
        }
