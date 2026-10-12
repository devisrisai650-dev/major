from pathlib import Path
from unittest.mock import patch

from api import RunRequest, _communication_kpis, health, run_pipeline


def test_api_health():
    result = health()
    assert result["status"] == "ok"
    assert result["simulation_only"] is True


def test_api_unknown_region():
    request = RunRequest(region_id="does_not_exist", seed=1)
    try:
        run_pipeline(request)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("Unknown region must produce an API 404 error")


def test_api_weather_error_is_controlled():
    request = RunRequest(region_id="region_001", seed=1)
    with patch("api.get_weather_data", side_effect=ValueError("bad payload")):
        try:
            run_pipeline(request)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 502
        else:
            raise AssertionError("Weather failure must produce an API 502 error")


def test_api_learning_is_opt_in_and_persisted_policy_is_not_changed_when_false(tmp_path):
    policy = tmp_path / "policy.npz"
    from ris_agent import QLearningRISAgent
    agent = QLearningRISAgent(seed=9)
    agent.save(policy)
    before = policy.read_bytes()

    weather = {
        "current": {
            "time": "2026-01-01T00:00",
            "temperature_c": 25,
            "humidity_pct": 70,
            "precipitation_mm": 0,
            "rain_mm": 0,
            "showers_mm": 0,
            "wind_speed_kmh": 5,
            "wind_direction_deg": 0,
            "surface_pressure_hpa": 1000,
        },
        "hourly_observations": [],
        "rainfall_windows": {
            "last_1h_precipitation_mm": 0,
            "last_3h_precipitation_mm": 0,
            "last_6h_precipitation_mm": 0,
            "last_24h_precipitation_mm": 0,
        },
    }
    discharge = {
        "available": False, "discharge_m3s": None,
        "time": None, "data_type": "mock", "reason": "mock",
    }
    water = {
        "available": False, "is_recent": False, "latest_observed_m": 1.0,
        "station": "mock", "current_time": None, "age_hours": None,
        "current_level_m": None, "previous_level_m": None,
        "change_m": None, "rate_of_change_m_per_hour": None,
        "reason": "mock",
    }
    transmission = {
        "priority": "MEDIUM", "delivered": True, "packet_received": "ok",
        "attempts": [], "policy_path": str(policy),
        "simulation_only": True, "learned": False, "used_seed": 7,
        "orchestrator": {
            "policy": "rule_based",
            "selected_policy": "drl_ris_cnoma",
            "policy_counts": {"drl_ris_cnoma": 1},
            "decision_count": 1,
            "decisions": [{"policy": "drl_ris_cnoma", "attempt": 1}],
            "simulation_only": True,
        },
    }
    with patch("api.get_weather_data", return_value=weather),          patch("api.get_discharge_analysis", return_value=discharge),          patch("api.CsvReplayProvider.get_water_level", return_value=water),          patch("api.transmit_semantic_message", return_value=transmission):
        request = RunRequest(region_id="region_001", seed=7, learn=False)
        result = run_pipeline(request)
    assert result["provenance"]["learning_enabled"] is False
    assert policy.read_bytes() == before
    assert Path(result["communication"]["policy_path"]) == policy
    assert result["orchestrator"]["policy"] == "rule_based"
    assert result["orchestrator"]["selected_policy"] == "drl_ris_cnoma"
    assert result["provenance"]["orchestrator_policy"] == "rule_based"

def test_api_reports_mean_delivery_and_final_aoi_separately():
    result = _communication_kpis({
        "attempts": [
            {"delivered": False, "sic_success": False, "snr_db": 2.0},
            {"delivered": True, "sic_success": True, "snr_db": 8.0},
        ],
        "critical_delivered": True,
        "mean_latency_ms": 25.0,
        "mean_aoi_ms": 35.0,
        "delivery_aoi_ms": 50.0,
        "final_aoi_ms": 50.0,
        "mean_throughput_mbps": 1.2,
    })

    assert result["mean_aoi_ms"] == 35.0
    assert result["delivery_aoi_ms"] == 50.0
    assert result["final_aoi_ms"] == 50.0
    assert result["delivery_rate_percent"] == 50.0
    assert result["sic_success_percent"] == 50.0
