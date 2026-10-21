import requests
import pytest
from fastapi import HTTPException

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


def test_live_dashboard_fails_closed_when_weather_provider_is_unavailable(monkeypatch):
    monkeypatch.setattr(api, "get_region", lambda region_id: REGION)
    monkeypatch.setattr(api, "get_weather_data", unavailable_weather)
    monkeypatch.setattr(
        api,
        "get_discharge_analysis",
        lambda *args: {"available": False, "reason": "provider offline"},
    )
    monkeypatch.setattr(api, "CsvReplayProvider", UnavailableGauge)

    with pytest.raises(HTTPException) as exc:
        dashboard(
            RunRequest(region_id="region_001", scenario_mode="live"),
            user=USER,
        )

    assert exc.value.status_code == 502
    assert "weather service unavailable" in exc.value.detail.lower()
