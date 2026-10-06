import numpy as np
import pandas as pd
from ris_agent import QLearningRISAgent
from ris_environment import RISEnvironment
from services.semantic_priority import build_semantic_priorities, calculate_semantic_compression, generate_semantic_message, select_transmission_parameters
from services.water_level import _quality_checks

def flood_state(rate=0.15):
    return {"rainfall": {"current_rain_mm": 5.0, "last_6h_precipitation_mm": 20.0},
            "river": {"discharge_m3s": 25.0, "available": True, "data_type": "modeled_daily_forecast"},
            "water_level": {"current_m": 1.2, "available": True, "rate_of_change_m_per_hour": rate, "station": "test"}}

def test_priority_rules():
    p = build_semantic_priorities({}, flood_state())
    assert "assessment_status" not in p
    assert p["water_level_rate"]["priority"] == "HIGH"
    missing = build_semantic_priorities({}, {**flood_state(), "water_level": {"available": False, "rate_of_change_m_per_hour": None}})
    assert missing["water_level"]["priority"] == "LOW"

def test_message_provenance():
    p = build_semantic_priorities({}, flood_state())
    selected = select_transmission_parameters(p)
    message = generate_semantic_message("Test", flood_state(), selected)
    assert "SOURCE=" in message and "QUALITY=" in message
    assert "FLOOD_ASSESSMENT=NOT_ASSESSED" in message
    assert calculate_semantic_compression(len(p), len(selected)) >= 0

def test_qc_rejects_bad_rows():
    frame = pd.DataFrame({"Data Acquisition Time": ["01/01/2026 00:00", "01/01/2026 00:00", "01/01/2026 01:00"], "River Water Level Telemetry Hourly (meter)": [1.0, 1.1, -5.0]})
    cleaned, quality = _quality_checks(frame)
    assert quality["duplicate_timestamp_rows"] == 1
    assert quality["range_rejected_rows"] == 1
    assert len(cleaned) == 1

def test_qc_failed_value_does_not_drive_rate():
    frame = pd.DataFrame({"Data Acquisition Time": ["01/01/2026 00:00", "01/01/2026 01:00", "01/01/2026 02:00"], "River Water Level Telemetry Hourly (meter)": [1.0, 999.0, 1.2]})
    cleaned, _ = _quality_checks(frame)
    assert list(cleaned.iloc[:, 1]) == [1.0, 1.2]

def test_partial_observation():
    env = RISEnvironment(seed=10, max_steps=2, observation_mode="partial", snr_noise_std_db=1.5, observation_delay=1)
    obs = env.reset(priority="HIGH")
    assert obs["simulation_only"] is True
    assert obs["observation_mode"] == "partial"
    assert obs["observation_delay_steps"] == 1

def test_oracle_observation():
    env = RISEnvironment(seed=10, max_steps=2, observation_mode="oracle")
    obs = env.reset(priority="HIGH")
    assert np.array_equal(obs["snr_db"], env.measurements["snr_db"])

def test_inference_is_read_only():
    agent = QLearningRISAgent(seed=1)
    before = agent.q.copy()
    env = RISEnvironment(seed=1, max_steps=1)
    obs = env.reset(priority="HIGH")
    action = agent.choose_action(obs, env.action_mask(), explore=False)
    env.step(action)
    assert np.array_equal(agent.q, before)

def test_qtable_roundtrip(tmp_path):
    agent = QLearningRISAgent(seed=2)
    path = tmp_path / "policy.npz"
    agent.save(path)
    loaded = QLearningRISAgent(seed=3)
    loaded.load(path)
    assert np.array_equal(agent.q, loaded.q)
