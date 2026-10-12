from unittest.mock import patch

from fastapi import HTTPException

from services.scenario_api import ScenarioRequest, ScenarioRunRequest, generate, run_scenario


def test_scenario_api_supports_configured_regions_and_start_time():
    result = generate(ScenarioRequest(
        region_id="region_002",
        scenario="severe",
        rainfall_mm_h=80,
        water_level_rise_m_h=0.25,
        steps=4,
        seed=2026,
        start_time="2026-10-12T08:00:00+05:30",
    ))
    assert result["region"]["name"] == "Vijayawada"
    assert result["time_series"][0]["timestamp"] == "2026-10-12T08:00:00+05:30"
    assert result["provenance"]["flood_assessment_status"] == "NOT_ASSESSED"


def test_scenario_run_integrates_orchestrator_and_never_assesses_flood(monkeypatch):
    captured = {}

    def fake_transmit(**kwargs):
        captured.update(kwargs)
        return {
            "orchestrator": {"policy": "safe_wait", "simulation_only": True},
            "attempts": [],
            "critical_delivered": False,
            "simulation_only": True,
        }

    monkeypatch.setattr("services.scenario_api.transmit_semantic_message", fake_transmit)
    request = ScenarioRunRequest(
        region_id="region_001",
        scenario="severe",
        rainfall_mm_h=80,
        water_level_rise_m_h=0.25,
        communication_condition="partial",
        playback="normal",
        seed=2026,
        steps=5,
        step_index=2,
        start_time="2026-10-12T00:00:00+05:30",
    )
    result = run_scenario(request)
    assert captured["channel_context"]["rain_mm"] == result["selected_time_step"]["rainfall_mm_h"]
    assert captured["channel_context"]["node_outage_probability"] == 0.28
    assert result["orchestrator"]["policy"] == "safe_wait"
    assert result["flood_assessment"]["status"] == "NOT_ASSESSED"
    assert result["flood_assessment"]["score"] is None
    assert result["provenance"]["synthetic"] is True
    assert result["provenance"]["selected_step_index"] == 2


def test_scenario_api_rejects_unknown_region():
    try:
        generate(ScenarioRequest(region_id="unknown"))
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Unknown regions must be rejected")
