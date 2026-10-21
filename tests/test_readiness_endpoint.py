import api


def test_readiness_distinguishes_simulation_from_operational_warning_readiness():
    status = api.readiness()

    assert status["application_ready"] is True
    assert status["operational_flood_warning_ready"] is False
    assert status["gauge_source"] == "historical_csv_replay_only"
    assert status["official_thresholds_verified"] is False
    assert status["channel_model_field_calibrated"] is False
    assert status["simulation_only"] is True
