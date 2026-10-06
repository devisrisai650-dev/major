from unittest.mock import patch

from api import RunRequest, health, run_pipeline


def test_api_health():
    result = health()
    assert result["status"] == "ok"
    assert result["simulation_only"] is True


def test_api_unknown_region():
    request = RunRequest(region_id="does_not_exist", seed=1)
    try:
        run_pipeline(request)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("Unknown region must produce an API 404 error")


def test_api_weather_error_is_controlled():
    request = RunRequest(region_id="region_001", seed=1)
    with patch("api.get_weather_data", side_effect=ValueError("bad payload")):
        try:
            run_pipeline(request)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 502
        else:
            raise AssertionError("Weather failure must produce an API 502 error")
