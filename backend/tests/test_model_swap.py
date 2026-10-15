"""
The retrained models, pinned.

These tests guard what the swap was FOR, not what the models happen to output:

  * the shipped weights load into the shipped architecture with nothing missing;
  * the CNN's verdict is its calibrated probability against the threshold chosen on
    validation - not an argmax, not a re-derived number;
  * AIS "not available" codes (SOG 102.3, COG 360) are no longer scored as extreme
    behaviour - the defect that ranked a missing-value flag as the most anomalous
    vessel in the corpus;
  * a vessel's behaviour score no longer depends on what else was scored with it;
  * the demo detects exactly the vessels the simulation seeded, and nothing else.

Nothing here claims the models are accurate. Held-out accuracy is the training
notebook's job, recorded in artifacts/cnn_config.json and the validation metrics.
"""
import json
from datetime import datetime, timedelta

import pytest

from core.config import AI_OUTPUT_DIR, MODEL_ARTIFACTS_DIR
from services.fleet_pipeline import run_fleet_scan
from services.t3_simulation import GROUND_TRUTH_FILE


# --- CNN --------------------------------------------------------------------

def test_cnn_weights_load_cleanly_into_the_shipped_architecture():
    from ml.cnn_inference import load_model

    _, _, report = load_model()
    assert report["loaded_cleanly"] is True
    assert report["missing_keys"] == [] and report["unexpected_keys"] == []
    assert report["parameters"] == 1_206_370


def test_cnn_decision_rule_is_the_calibrated_probability_against_the_threshold():
    from ml.cnn_inference import config, predict_image

    cfg = config()
    for name in ("class_0.jpg", "class_1.jpg"):
        r = predict_image(image_path=AI_OUTPUT_DIR / "samples" / name)
        p_oil = r["probabilities"]["OIL SPILL"]
        assert r["probabilities"]["OIL SPILL"] + r["probabilities"]["NO OIL SPILL"] == pytest.approx(1.0)
        assert r["oil_probability"] == pytest.approx(p_oil)
        assert r["class_id"] == int(p_oil >= cfg["decision_threshold"])
        # confidence is the probability of the verdict that was returned
        assert r["confidence"] == pytest.approx(p_oil if r["class_id"] == 1 else 1 - p_oil)
        assert r["decision_threshold"] == cfg["decision_threshold"]
        assert r["temperature"] == cfg["temperature"]
        assert r["performs_segmentation"] is False


def test_cnn_classifies_the_two_bundled_sample_tiles():
    from ml.cnn_inference import predict_image

    oil = predict_image(image_path=AI_OUTPUT_DIR / "samples" / "class_1.jpg")
    clean = predict_image(image_path=AI_OUTPUT_DIR / "samples" / "class_0.jpg")
    assert oil["prediction"] == "OIL SPILL" and oil["confidence"] > 0.9
    assert clean["prediction"] == "NO OIL SPILL" and clean["confidence"] > 0.9


def test_cnn_config_records_a_scene_grouped_evaluation():
    cfg = json.loads((MODEL_ARTIFACTS_DIR / "cnn_config.json").read_text())
    assert "scene-grouped" in cfg["evaluation"]["split"]
    assert cfg["evaluation"]["smoke_test"] is False          # never ship a smoke-test model
    assert 0 < cfg["decision_threshold"] < 1
    assert cfg["temperature"] > 0


# --- AIS --------------------------------------------------------------------

def _steady_track(n=24, knots=11.0, step_s=120):
    """A vessel holding a steady 11 kn on a straight course, reported every 2 minutes."""
    km_per_step = knots * 1.852 * step_s / 3600
    t0 = datetime(2021, 3, 1, 8, 0, 0)
    return [{"MMSI": 111, "BaseDateTime": (t0 + timedelta(seconds=i * step_s)).isoformat(),
             "SOG": knots, "COG": 90.0, "LAT": 28.5,
             "LON": -94.8 + i * km_per_step / (111.32 * 0.8788)} for i in range(n)]


def test_ais_missing_value_codes_are_cleared_and_recovered_not_scored_as_extreme():
    from ml.ais_inference import predict_track

    clean = predict_track(_steady_track(), mmsi=111)

    polluted = _steady_track()
    polluted[10]["SOG"] = 102.3          # AIS "speed not available"
    polluted[10]["COG"] = 360.0          # AIS "course not available"
    polluted[11]["SOG"] = 102.3
    result = predict_track(polluted, mmsi=111)

    assert result["sog_missing_value_codes_cleared"] == 2
    assert result["sog_recovered_from_track"] == 2
    # The codes did not become the most extreme behaviour in the track.
    assert result["behaviour_score"] < 50
    assert result["behaviour_score"] == pytest.approx(clean["behaviour_score"], abs=15)


def test_ais_a_real_speed_collapse_is_still_flagged():
    from ml.ais_inference import predict_track

    track = _steady_track()
    for p in track[12:]:                 # abrupt stop, positions stop advancing
        p["SOG"] = 0.5
    for i in range(13, len(track)):
        track[i]["LON"] = track[12]["LON"]
    assert predict_track(track, mmsi=111)["behaviour_score"] > predict_track(_steady_track(), mmsi=111)["behaviour_score"]


def test_ais_score_does_not_depend_on_what_else_is_scored():
    """
    The previous model normalised against the whole corpus, so the same track scored
    differently depending on what it was scored with. This one uses a fixed
    calibration: a vessel's per-record scores must be identical alone or pooled.
    """
    import pandas as pd

    from ml import oiltrace_ais as A
    from ml.ais_inference import _load

    model = _load()
    mine = _steady_track()
    others = [dict(p, MMSI=222, SOG=2.0 + (i % 5), COG=40.0 + 30 * (i % 4)) for i, p in enumerate(_steady_track())]

    def scored(records):
        clean, _ = A.clean_ais(pd.DataFrame(records))
        feat = A.build_features(clean)
        return feat.join(model.score(feat))

    alone = scored(mine)
    pooled = scored(mine + others)
    a = alone[alone["mmsi"] == 111].sort_values("time")["anomaly_score"].to_numpy()
    b = pooled[pooled["mmsi"] == 111].sort_values("time")["anomaly_score"].to_numpy()
    assert len(a) == len(b) > 0
    assert (a[~pd.isna(a)] == b[~pd.isna(b)]).all()
    assert pooled[pooled["mmsi"] == 222]["anomaly_score"].max() != alone["anomaly_score"].max()  # the pool is not a no-op


def test_ais_requires_positions_and_says_so():
    from ml.ais_inference import predict_track

    no_pos = [{k: v for k, v in p.items() if k not in ("LAT", "LON")} for p in _steady_track()]
    with pytest.raises(ValueError, match="LAT"):
        predict_track(no_pos)


def test_ais_corpus_has_no_missing_value_codes_left():
    from ml.ais_inference import scored_corpus

    corpus = scored_corpus()
    assert (corpus["SOG"] < 102.3).all()
    assert (corpus["COG"].dropna() < 360).all()
    assert corpus["anomaly_score"].between(0, 100).all()
    assert {"MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "anomaly_score", "is_anomaly"} <= set(corpus.columns)


# --- the demo ---------------------------------------------------------------

def test_the_demo_detects_exactly_the_seeded_vessels_and_nothing_else():
    truth = set(json.loads(GROUND_TRUTH_FILE.read_text())["oil_positive_ships"])
    for clear_pass in ("t1", "t2"):
        assert run_fleet_scan(clear_pass)["status"] == "CLEAR"
    scan = run_fleet_scan("t3")
    assert {s["id"] for s in scan["fleet"] if s["oil_detected"]} == truth


def test_the_model_card_reports_the_installed_models():
    from routes.models import models

    card = models()
    assert card["detection"]["parameters"] == 1_206_370
    assert card["detection"]["validation"]["test_samples"] == 574
    assert card["detection"]["input"]["size"] == "224 x 224"
    assert card["behaviour"]["hyperparameters"]["n_estimators"] == 300
    assert len(card["behaviour"]["input"]["features"]) == 4
    assert card["behaviour"]["known_flaw"] is None
    assert card["behaviour"]["corpus_required_at_runtime"] is False
