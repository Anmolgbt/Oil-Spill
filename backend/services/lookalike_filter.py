"""
Look-alike discrimination (oil vs biogenic slick, low-wind zone, ship wake).

DEMO_MODE on  -> class probabilities from the demo fixture
DEMO_MODE off -> classifier output, not yet connected
"""
from core.config import DEMO_MODE, FIXTURE_PROVENANCE

from .data_store import get_incident


def load_demo_lookalike():
    """
    Class probabilities read from the demo fixture. Nothing hardcoded here, and
    nothing classified either: these are fixture values, not model output. The
    provenance stamp says so, so the panel is never mistaken for real inference.
    """
    return {**get_incident()["lookalike"], "provenance": FIXTURE_PROVENANCE}


def run_filter(detection=None):
    """
    Classify a detection as oil or look-alike.

    `detection` will carry the spill-model output once real mode is connected;
    it is accepted now so the call site does not change later.
    """
    if DEMO_MODE:
        return load_demo_lookalike()

    raise NotImplementedError(
        "Look-alike classifier not connected yet. Expected return shape: "
        "{'classes': [{'label': str, 'probability': float}], 'decision': str}"
    )
