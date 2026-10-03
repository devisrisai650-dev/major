from datetime import datetime, timedelta, timezone

import numpy as np

from ris_agent import QLearningRISAgent
from ris_environment import RISEnvironment
from semantic_transmission import priority_for_message
from services.gauge_provider import CsvReplayProvider, LiveProvider
from services.semantic_priority import (
    build_semantic_priorities,
    calculate_semantic_compression,
    generate_semantic_message,
    select_transmission_parameters,
)
from services.water_level import _quality_checks


def _flood_state(water_level=1.2, rate=0.12):
    return {
        "rainfall": {
            "current_rain_mm": 5.0,
            "last_6h_precipitation_mm": 20.0,
        },
        "river": {
            "discharge_m3s": 25.0,
            "available": True,
            "data_type": "modeled_daily_forecast",
        },
        "water_level": {
            "current_m": water_level,
            "available": True,
            "rate_of_change_m_per_hour": rate,
            "station": "test",
        },
    }


def test_assessment_metadata_does_not_force_critical():
    priorities = build_semantic_priorities({}, _flood_state())
    assert "assessment_status" not in priorities
    assert priority_for_message(priorities) == "HIGH"


def test_rising_qc_passed_gauge_is_high_priority():
    priorities = build_semantic_priorities({}, _flood_state(rate=0.15))
    assert priorities["water_level_rate"]["priority"] == "HIGH"
    assert priorities["water_level_rate"]["available"]


def test_medium_fields_are_selected_and_message_is_not_empty():
    priorities = build_semantic_priorities({}, _flood_state())
    selected = select_transmission_parameters(priorities)
    message = generate_semantic_message("Test", _flood_state(), selected)
    assert selected
    assert "RAINFALL_CURRENT=" in message
    assert "SOURCE=" in message
    assert calculate_semantic_compression(len(priorities), len(selected)) >= 0


def test_qc_removes_duplicate_and_out_of_range_rows():
    frame = __import__("pandas").DataFrame({
        "Data Acquisition Time": [
            "01/01/2026 00:00",
            "01/01/2026 00:00",
            "01/01/2026 01:00",
            "01/01/2026 02:00",
        ],
        "River Water Level Telemetry Hourly (meter)": [1.0, 1.1, -5.0, 1.2],
    })
    cleaned, quality = _quality_checks(frame)
    assert quality["duplicate_timestamp_rows"] == 1
    assert quality["range_rejected_rows"] == 1
    assert len(cleaned) == 2


def test_qc_failed_values_do_not_drive_rate():
    frame = __import__("pandas").DataFrame({
        "Data Acquisition Time": [
            "01/01/2026 00:00",
            "01/01/2026 01:00",
            "01/01/2026 02:00",
        ],
        "River Water Level Telemetry Hourly (meter)": [1.0, 999.0, 1.2],
    })
    cleaned, _ = _quality_checks(frame)
    assert list(cleaned.iloc[:, 1]) == [1.0, 1.2]


def test_replay_and_live_provider_boundaries():
    assert CsvReplayProvider().get_water_level(
        {
            "water_level_file": "missing.csv",
            "water_level_station": "missing",
            "river": "test",
        }
    )["mode"] == "historical_replay"
    try:
        LiveProvider().get_water_level({})
    except NotImplementedError:
        pass
    else:
        raise AssertionError("LiveProvider must remain unimplemented")


def test_inference_does_not_change_q_table():
    agent = QLearningRISAgent(seed=1)
    before = agent.q.copy()
    env = RISEnvironment(seed=1, max_steps=1)
    observation = env.reset(priority="HIGH")
    action = agent.choose_action(observation, env.action_mask(), explore=False)
    next_obs, reward, done, _ = env.step(action)
    agent.load if False else None
    assert np.array_equal(agent.q, before)
    assert next_obs["simulation_only"]


def test_environment_reseed_resets_both_rngs():
    env = RISEnvironment(seed=10, max_steps=2)
    first = env.reset(priority="HIGH")
    first_snr = first["snr_db"].copy()
    env.reseed(10)
    second = env.reset(priority="HIGH")
    assert np.array_equal(first_snr, second["snr_db"])


def test_atomic_qtable_save_roundtrip(tmp_path):
    agent = QLearningRISAgent(seed=2)
    path = tmp_path / "policy.npz"
    agent.save(path)
    loaded = QLearningRISAgent(seed=3)
    loaded.load(path)
    assert np.array_equal(agent.q, loaded.q)
