from unittest.mock import patch

import api
from api import RunRequest, dashboard

REGION = {"id": "region_001", "name": "Kakinada", "river": "Godavari",
          "latitude": 1.0, "longitude": 2.0, "timezone": "Asia/Kolkata"}
USER = {"id": 1, "email": "user@gmail.com", "role": "user"}


class FakeGauge:
    def get_water_level(self, region):
        return {"available": False, "latest_observed_m": 1.0, "reason": "replay only"}


def test_dashboard_response_contains_only_user_facing_fields():
    weather = {
        "source": "Open-Meteo",
        "current": {"time": "2026-10-12T12:00", "temperature_c": 29.0, "rain_mm": 0.0},
        "rainfall_windows": {"last_6h_precipitation_mm": 0.0},
        "hourly_conditions": [{"time": "2026-10-12T18:00", "temperature_c": 28.0,
                               "source_type": "forecast", "synthetic_or_internal": "must not leak"}],
    }
    with patch.object(api, "get_region", return_value=REGION), \
         patch.object(api, "get_weather_data", return_value=weather), \
         patch.object(api, "get_discharge_analysis", return_value={"available": False}), \
         patch.object(api, "CsvReplayProvider", FakeGauge):
        response = dashboard(RunRequest(region_id="region_001", time_of_day="18:00"), user=USER)

    assert response["weather"]["current"]["time"].endswith("T12:00")
    assert "selected_hour" not in response["weather"]
    assert response["region"] == {"id": "region_001", "name": "Kakinada", "river": "Godavari"}
    for private_key in ("communication", "orchestrator", "semantic_priorities", "channel_prediction", "provenance"):
        assert private_key not in response
    assert "hourly_conditions" not in response["weather"]
    # Incomplete evidence must never be summarised as a LOW flood signal.
    assert response["flood_dashboard"]["environmental_signal"] == "INCOMPLETE"
    assert response["flood_assessment"]["complete"] is False
    assert response["flood_assessment"]["status"] == "NOT_ASSESSED"
    assert response["scenario_mode"] == "live"
    assert "synthetic" in response["scenario_notice"].lower()
    assert response["water_level"]["available"] is False
