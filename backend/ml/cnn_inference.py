"""
Live inference for the trained oil-spill CNN.

Everything here is reproduced verbatim from the authoritative Colab notebook
(OILTRACE_AIS_Model.ipynb) so that a prediction made by this backend matches a
prediction made in the notebook. Nothing is re-derived or "improved":

    architecture   cell 35  (class OilSpillCNN)
    transform      cell 33  (Resize 224 -> Grayscale(3) -> ToTensor -> Normalize)
    checkpoint     cell 64  (torch.save(cnn_model.state_dict(), ...)) - weights only
    inference      cells 73 / 76
                     image = Image.open(path).convert("RGB")
                     input_tensor = transform(image).unsqueeze(0).to(device)
                     output = cnn_model(input_tensor)
                     probabilities = torch.softmax(output, dim=1)
                     predicted_class = torch.argmax(probabilities, dim=1).item()
                     confidence = probabilities[0, predicted_class].item()
    class names    cell 73  {0: "NO OIL SPILL", 1: "OIL SPILL"}

Note on colour handling: the training Dataset opened images with .convert("L")
while the single-image inference cells use .convert("RGB"). Both funnel through
Grayscale(num_output_channels=3) in the same transform, so the resulting tensor
is identical. The inference path is reproduced here because that is what this
module does.

The model is a BINARY CLASSIFIER. It returns a class and a confidence, and
nothing else - no mask, no boundary, no area. Confidence is the probability of
the predicted class, exactly as the notebook computes it.
"""
import io
import time

from core.config import MODEL_ARTIFACTS_DIR

CHECKPOINT = MODEL_ARTIFACTS_DIR / "oilspill_cnn.pth"

# Notebook cell 73.
CLASS_NAMES = {0: "NO OIL SPILL", 1: "OIL SPILL"}

# Notebook cell 33. Kept as literals; do not substitute other values.
INPUT_SIZE = (224, 224)
NORM_MEAN = [0.485, 0.456, 0.406]
NORM_STD = [0.229, 0.224, 0.225]

_model = None
_device = None
_load_report = None


def _torch():
    """Import torch lazily so the app still starts when it is not installed."""
    import torch
    return torch


def build_model():
    """The exact architecture from notebook cell 35."""
    import torch.nn as nn

    class OilSpillCNN(nn.Module):
        def __init__(self):
            super(OilSpillCNN, self).__init__()

            self.features = nn.Sequential(
                nn.Conv2d(3, 32, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.MaxPool2d(2),

                nn.Conv2d(32, 64, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.MaxPool2d(2),

                nn.Conv2d(64, 128, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.MaxPool2d(2),

                nn.Conv2d(128, 256, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.AdaptiveAvgPool2d((1, 1))
            )

            self.classifier = nn.Sequential(
                nn.Flatten(),
                nn.Linear(256, 128),
                nn.ReLU(),
                nn.Dropout(0.4),
                nn.Linear(128, 2)
            )

        def forward(self, x):
            x = self.features(x)
            x = self.classifier(x)
            return x

    return OilSpillCNN()


def build_transform():
    """The exact preprocessing pipeline from notebook cell 33."""
    from torchvision import transforms

    return transforms.Compose([
        transforms.Resize(INPUT_SIZE),
        transforms.Grayscale(num_output_channels=3),
        transforms.ToTensor(),
        transforms.Normalize(mean=NORM_MEAN, std=NORM_STD),
    ])


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
    }
    return _model, _device, _load_report


def predict_image(image_bytes=None, image_path=None):
    """
    Run the trained CNN on one image.

    Returns the notebook's three values plus timing and provenance. Confidence is
    the softmax probability of the predicted class - not a fixed or derived
    number.
    """
    from PIL import Image

    torch = _torch()
    model, device, report = load_model()

    if image_bytes is not None:
        image = Image.open(io.BytesIO(image_bytes))
    elif image_path is not None:
        image = Image.open(image_path)
    else:
        raise ValueError("predict_image needs image_bytes or image_path")

    original_size = image.size
    image = image.convert("RGB")                      # notebook cells 73 / 76

    transform = build_transform()
    input_tensor = transform(image).unsqueeze(0).to(device)

    started = time.perf_counter()
    with torch.no_grad():
        output = model(input_tensor)
        probabilities = torch.softmax(output, dim=1)
        predicted_class = torch.argmax(probabilities, dim=1).item()
        confidence = probabilities[0, predicted_class].item()
    elapsed_ms = (time.perf_counter() - started) * 1000

    probs = probabilities[0].tolist()
    return {
        "prediction": CLASS_NAMES[predicted_class],
        "class_id": predicted_class,
        "confidence": confidence,
        "probabilities": {CLASS_NAMES[i]: p for i, p in enumerate(probs)},
        "inference_ms": round(elapsed_ms, 2),
        "device": str(device),
        "input_size": list(INPUT_SIZE),
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
