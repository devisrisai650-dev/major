from unittest.mock import patch

from api import app
from services.scenario_api import ScenarioRunRequest, run_scenario


def test_scenario_routes_are_mounted():
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/scenarios/options" in paths
    assert "/api/scenarios/generate" in paths
    assert "/api/scenarios/run" in paths


def test_rising_scenario_communications_run_never_assesses_real_flood_risk():
    fake_transmission = {
        "attempts": [{"delivered": True}],
        "critical_delivered": True,
        "orchestrator": {"policy": "test-simulated-policy"},
    }
    request = ScenarioRunRequest(
        region_id="region_001",
        scenario="rising",
        rainfall_mm_h=80,
        water_level_rise_m_h=0.25,
        communication_condition="partial",
        playback="normal",
        seed=2026,
        steps=24,
        start_time="2026-10-14T00:00:00+05:30",
        initial_water_level_m=1.0,
        step_index=3,
        communication_attempts=3,
        learn=False,
    )

    with patch("services.scenario_api.transmit_semantic_message", return_value=fake_transmission):
        result = run_scenario(request)

    assert result["scenario"]["provenance"]["synthetic"] is True
    assert result["selected_time_step"]["data_source"] == "synthetic_scenario"
    assert result["flood_assessment"]["status"] == "NOT_ASSESSED"
    assert result["flood_assessment"]["complete"] is False
    assert "not live measurements" in result["disclaimer"]
