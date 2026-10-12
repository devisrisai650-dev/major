from api import _classify_demo_flood_scenario


def test_demo_flood_scenario_classifies_high_environmental_severity():
    result = _classify_demo_flood_scenario(
        rain_mm=80,
        rain_6h_mm=336,
        rise_m_per_hour=0.25,
        discharge_m3s=185,
    )

    assert result["status"] == "DEMO_HIGH"
    assert result["signal"] == "HIGH"
    assert "synthetic" in result["label"].lower()


def test_demo_flood_scenario_classifies_elevated_environmental_severity():
    result = _classify_demo_flood_scenario(
        rain_mm=24,
        rain_6h_mm=50,
        rise_m_per_hour=0.08,
        discharge_m3s=102,
    )

    assert result["status"] == "DEMO_ELEVATED"
    assert result["signal"] == "ELEVATED"


def test_demo_flood_scenario_classifies_baseline_values():
    result = _classify_demo_flood_scenario(
        rain_mm=2,
        rain_6h_mm=1,
        rise_m_per_hour=0.01,
        discharge_m3s=37,
    )

    assert result["status"] == "DEMO_BASELINE"
    assert result["signal"] == "LOW"


def test_demo_flood_scenario_fails_closed_when_a_metric_is_missing():
    result = _classify_demo_flood_scenario(
        rain_mm=80,
        rain_6h_mm=None,
        rise_m_per_hour=0.25,
        discharge_m3s=185,
    )

    assert result["status"] == "DEMO_DATA_INCOMPLETE"
    assert result["signal"] == "INCOMPLETE"
