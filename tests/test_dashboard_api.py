from unittest.mock import patch

from api import RunRequest, dashboard


def test_dashboard_response_contains_only_user_facing_fields():
    internal_result = {
        "region": {"id": "region_001", "name": "Kakinada", "river": "Godavari", "latitude": 1.0},
        "weather": {
            "source": "Open-Meteo",
            "current": {"temperature_c": 29.0},
            "selected_hour": {"time": "2026-10-12T18:00", "temperature_c": 28.0, "source_type": "forecast"},
            "hourly_conditions": [{"synthetic_or_internal": "must not leak"}],
        },
        "river_discharge": {"available": False, "discharge_m3s": None},
        "water_level": {"available": False, "current_level_m": None, "latest_observed_m": 1.0},
        "flood_assessment": {"status": "NOT_ASSESSED", "state": "NOT_ASSESSED", "complete": False, "reason": "Evidence missing"},
        "flood_dashboard": {
            "assessment_status": "NOT_ASSESSED",
            "environmental_signal": "UNKNOWN",
            "message": "Evidence missing",
            "readiness": {"assessment_ready": False},
        },
        "flood_indicators": {
            "rainfall": {"classification": "LOW", "current_rain_mm": 0.0},
            "river": {"classification": "UNKNOWN", "available": False},
            "water_level": {"classification": "UNKNOWN", "available": False},
        },
        "communication": {"attempts": [{"secret_internal_simulation": True}]},
        "orchestrator": {"policy": "internal"},
        "semantic_priorities": {"internal": True},
        "channel_prediction": {"internal": True},
        "provenance": {"synthetic": True},
    }
    with patch("api.run_pipeline", return_value=internal_result):
        response = dashboard(RunRequest(region_id="region_001", time_of_day="18:00"))

    assert response["weather"]["selected_hour"]["time"] == "2026-10-12T18:00"
    assert response["region"] == {"id": "region_001", "name": "Kakinada", "river": "Godavari"}
    for private_key in ("communication", "orchestrator", "semantic_priorities", "channel_prediction", "provenance"):
        assert private_key not in response
    assert "hourly_conditions" not in response["weather"]
