"""
GET /api/models — the card judges read.

Two things are worth pinning here, and only two:

  1. Every number in the payload traces back to an artifact. The failure mode
     this guards against is a plausible-looking metric getting typed into the
     route by hand and then quietly disagreeing with the checkpoint.
  2. The attribution weights it reports are the weights the ranking actually
     applies. A card that misstates them is worse than no card.

Nothing here checks that the models are any good. That is not what this
endpoint claims and not what these tests measure.
"""
from routes.models import models
from services.investigation import (WEIGHT_BEHAVIOUR, WEIGHT_PROXIMITY,
                                    WEIGHT_TRAJECTORY)
from services.stored_result import load_cnn_metrics


def test_reported_weights_are_the_weights_the_ranking_applies():
    weights = models()["attribution"]["weights"]
    assert weights == {"proximity": WEIGHT_PROXIMITY,
                       "trajectory": WEIGHT_TRAJECTORY,
                       "behaviour": WEIGHT_BEHAVIOUR}
    # The distinction the whole card exists to make.
    assert models()["attribution"]["is_trained_model"] is False
    assert models()["attribution"]["validated"] is False


def test_cnn_facts_come_from_the_artifacts_not_from_this_route():
    from ml.cnn_inference import model_info

    card = models()["detection"]
    info = model_info()
    assert card["parameters"] == info.get("parameters")
    assert card["available"] == info.get("available", False)

    # Metrics are the validation JSON verbatim, or absent — never a stand-in.
    metrics = load_cnn_metrics()
    assert card["validation"] == (metrics or None)

    # What the model cannot do is asserted structurally, not just in prose.
    assert card["capabilities"] == {"performs_classification": True,
                                    "performs_segmentation": False,
                                    "produces_mask": False,
                                    "localises_pixels": False,
                                    "geolocates": False}


def test_missing_facts_are_null_rather_than_invented():
    """Absent artifact fields must surface as None, not as zeros or guesses."""
    payload = models()
    ais = payload["behaviour"]
    for value in (payload["detection"]["parameters"],
                  ais["hyperparameters"]["n_estimators"],
                  ais["input"]["features"]):
        assert value is None or value  # present-and-truthy, or explicitly None
    # A zero here would read as "contamination 0", a real setting.
    assert ais["hyperparameters"]["contamination"] != 0
