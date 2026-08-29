"""
Adapter for the trained AIS behavioural-anomaly model.

Mirrors ml/spill_model.py. The model is being trained separately; this file is
the only place that changes when a checkpoint arrives. It scores a vessel's
track for behaviour that is unusual for its route — sudden course changes,
unexplained slowdowns, loitering, AIS gaps.

Note the ordering: this runs *after* the spill has been detected and traced back
to an origin, on the handful of vessels that survived the spatio-temporal filter.
It is not a first-pass screen over all traffic.
"""
from core.config import ANOMALY_MODEL_PATH


class AnomalyModel:
    """Lazy wrapper around a trained AIS anomaly model."""

    def __init__(self, model_path=None):
        self.model_path = model_path or ANOMALY_MODEL_PATH
        self._model = None

    def load(self):
        """Load the checkpoint into memory once."""
        raise NotImplementedError("Connect trained AIS anomaly model here")

    def predict(self, track):
        """
        Score one vessel track.

        `track` is a list of {time, lat, lon, speed_kt, heading} points.

        Expected return shape:
            {
                "anomaly_score": float,   # 0.0 - 1.0
                "is_anomaly": bool,
                "reason": str,            # human-readable, shown as evidence
            }
        """
        raise NotImplementedError("Connect trained AIS anomaly model here")


_model = None


def get_model():
    """Process-wide singleton, so the checkpoint is loaded at most once."""
    global _model
    if _model is None:
        _model = AnomalyModel()
    return _model
