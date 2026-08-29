"""
Adapter for the trained oil-spill model.

The model is being trained separately. This file is the only place that needs to
change when a .pt or .onnx checkpoint arrives — routes, services and the frontend
all stay as they are.

To connect a model, implement load() and predict() below. predict() must return
the dict shape documented in its docstring; services/spill_detection.py maps that
onto the existing API response.
"""
from core.config import SPILL_MODEL_PATH


class SpillModel:
    """Lazy wrapper around a trained segmentation/classification model."""

    def __init__(self, model_path=None):
        self.model_path = model_path or SPILL_MODEL_PATH
        self._model = None

    def load(self):
        """
        Load the checkpoint into memory once.

        Torch:  self._model = torch.load(self.model_path); self._model.eval()
        ONNX:   self._model = onnxruntime.InferenceSession(self.model_path)
        """
        raise NotImplementedError("Connect trained spill model here")

    def predict(self, image_path):
        """
        Run inference on one satellite image.

        Expected return shape:
            {
                "oil_detected": bool,
                "oil_probability": float,   # 0.0 - 1.0
                "area_km2": float,
                "mask_path": str | None,    # written under data/runtime/
            }
        """
        raise NotImplementedError("Connect trained spill model here")


_model = None


def get_model():
    """Process-wide singleton, so the checkpoint is loaded at most once."""
    global _model
    if _model is None:
        _model = SpillModel()
    return _model
