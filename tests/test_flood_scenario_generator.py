from services.flood_scenario_generator import generate_scenario


def test_severe_scenario_is_reproducible_and_has_provenance():
    args = {
        "region_id": "region_001",
        "region_name": "Kakinada",
        "scenario": "severe",
        "rainfall_mm_h": 80,
        "water_level_rise_m_h": 0.25,
        "communication_condition": "partial",
        "playback": "normal",
        "seed": 73,
        "steps": 12,
        "start_time": "2026-10-12T06:00:00+05:30",
    }
    first = generate_scenario(**args)
    second = generate_scenario(**args)
    assert first["scenario_id"] == second["scenario_id"]
    assert first["time_series"] == second["time_series"]
    assert len(first["time_series"]) == 12
    assert first["provenance"]["synthetic"] is True
    assert first["provenance"]["live_observations_used"] is False
    assert first["provenance"]["flood_assessment_status"] == "NOT_ASSESSED"
    assert first["time_series"][0]["timestamp"] == "2026-10-12T06:00:00+05:30"
    assert first["time_series"][-1]["timestamp"] == "2026-10-12T17:00:00+05:30"
    assert first["configuration"]["rainfall_mm_h"] == 80.0
    assert first["configuration"]["water_level_rise_m_h"] == 0.25


def test_region_and_start_time_are_configurable():
    result = generate_scenario(
        region_id="region_002",
        region_name="Vijayawada",
        start_time="2026-07-01T09:00:00+05:30",
        steps=3,
        seed=1,
    )
    assert result["region"]["name"] == "Vijayawada"
    assert result["time_series"][0]["timestamp"] == "2026-07-01T09:00:00+05:30"
    assert result["time_series"][2]["timestamp"] == "2026-07-01T11:00:00+05:30"


def test_scenario_parameters_are_validated():
    for kwargs in (
        {"scenario": "made_up"},
        {"rainfall_mm_h": -1},
        {"water_level_rise_m_h": 2},
        {"communication_condition": "unknown"},
        {"steps": 1},
        {"start_time": "2026-01-01T00:00:00"},
    ):
        try:
            generate_scenario(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected invalid configuration to fail: {kwargs}")


def test_communication_condition_changes_only_simulation_context():
    healthy = generate_scenario(communication_condition="healthy", seed=10)
    partial = generate_scenario(communication_condition="partial", seed=10)
    total = generate_scenario(communication_condition="total", seed=10)
    assert healthy["channel_context"]["node_outage_probability"] < partial["channel_context"]["node_outage_probability"]
    assert partial["channel_context"]["node_outage_probability"] < total["channel_context"]["node_outage_probability"]
    assert total["time_series"][0]["node_available"] is False
