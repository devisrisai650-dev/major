from services.flood_state import analyze_flood_state


def test_stale_or_missing_gauge_keeps_assessment_not_assessed():
    weather = {
        "current": {"rain_mm": 35.0},
        "rainfall_windows": {"last_6h_precipitation_mm": 80.0},
    }
    discharge = {
        "available": True,
        "discharge_m3s": 900.0,
        "data_type": "modeled_daily_forecast",
        "time": "2026-10-11",
    }
    stale_gauge = {
        "available": False,
        "is_recent": False,
        "latest_observed_m": 44.0,
        "current_level_m": None,
        "reason": "stale replay observation",
    }

    result = analyze_flood_state(weather, discharge, stale_gauge)
    assessment = result["flood_assessment"]

    assert assessment["status"] == "NOT_ASSESSED"
    assert assessment["state"] == "NOT_ASSESSED"
    assert assessment["score"] is None
    assert assessment["complete"] is False
    assert "fresh configured river-gauge reading" in assessment["missing_or_unconfigured"]
    assert "not a flood warning" in assessment["reason"].lower()
    assert "all-clear" in assessment["reason"].lower()


def test_missing_rainfall_and_gauge_are_reported_as_missing():
    result = analyze_flood_state(
        {"current": {}, "rainfall_windows": {}},
        {"available": False, "data_type": "unavailable"},
        {"available": False, "is_recent": False},
    )
    missing = result["flood_assessment"]["missing_or_unconfigured"]

    assert "current local rainfall" in missing
    assert "complete observed 6-hour rainfall window" in missing
    assert "fresh configured river-gauge reading" in missing
    assert "verified official station-specific warning thresholds" in missing
