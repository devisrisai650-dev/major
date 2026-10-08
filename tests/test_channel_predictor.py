import pytest

import services.channel_predictor as predictor


def test_predictor_reports_unavailable_when_measurements_are_missing():
    result = predictor.predict_channel(None, None, None, None, None)
    assert result["available"] is False
    assert result["model_status"] == "unavailable_real_measurements"
    assert result["link_availability"] == "UNVERIFIED"


def test_predictor_rejects_nonfinite_inputs():
    result = predictor.predict_channel(float("nan"), 0.1, 0.1, 0.1, 1.0)
    assert result["available"] is False
    assert result["model_status"] == "invalid_inputs"


def test_predictor_model_path_is_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("FLOODAI_CHANNEL_MODEL_PATH", str(tmp_path / "missing.json"))
    predictor._model = None
    predictor._loaded_model_path = None
    with pytest.raises(FileNotFoundError):
        predictor.load_channel_model()
