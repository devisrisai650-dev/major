import requests

import api
from api import RunRequest, dashboard


REGION = {
    "id": "region_001",
    "name": "Kakinada",
    "river": "Godavari",
    "latitude": 1.0,
    "longitude": 2.0,
    "timezone": "Asia/Kolkata",
}
USER = {"id": 1, "email": "user@gmail.com", "role": "user"}


class UnavailableGauge:
    def get_water_level(self, region):
        return {
            "available": False,
            "is_recent": False,
            "reason": "historical replay is stale",
            "station": "Gokavaram_1",
        }


def unavailable_weather(*args, **kwargs):
    raise requests.RequestException("provider offline")


def test_dashboard_falls_back_to_synthetic_data_without_promoting_assessment(monkeypatch):
    monkeypatch.setattr(api, "get_region", lambda region_id: REGION)
    monkeypatch.setattr(api, "get_weather_data", unavailable_weather)
    monkeypatch.setattr(
        api,
        "get_discharge_analysis",
        lambda *args: {"available": False, "reason": "provider offline"},
    )
    monkeypatch.setattr(api, "CsvReplayProvider", UnavailableGauge)

    response = dashboard(
        RunRequest(region_id="region_001", time_of_day="18:00"),
        user=USER,
    )

    assert response["scenario_mode"] == "synthetic_fallback"
    assert response["flood_assessment"]["status"] == "NOT_ASSESSED"
    assert response["flood_assessment"]["complete"] is False
    assert response["water_level"]["available"] is False
    assert response["flood_indicators"]["water_level"]["available"] is False
    assert "synthetic" in response["scenario_notice"].lower()
    assert "not a real-world warning" in response["flood_dashboard"]["message"].lower()
