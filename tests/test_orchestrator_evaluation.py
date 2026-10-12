from evaluate_orchestrator import SCENARIOS, run_episode
from ris_agent import QLearningRISAgent


def test_orchestrator_evaluation_has_outage_stress_scenario():
    stress = SCENARIOS["outage_stress"]
    assert stress["node_outage_probability"] > SCENARIOS["severe"]["node_outage_probability"]
    assert stress["node_recovery_probability"] < SCENARIOS["severe"]["node_recovery_probability"]
    assert stress["rain_mm"] > SCENARIOS["severe"]["rain_mm"]


def test_orchestrator_episode_reports_activation_metrics(tmp_path):
    policy = tmp_path / "ris_q_table.npz"
    QLearningRISAgent(seed=4).save(policy)
    row = run_episode(
        policy_path=policy,
        seed=12,
        steps=3,
        scenario="outage_stress",
        controller="orchestrated",
        message_index=2,
    )
    assert row["simulation_only"] is True
    assert row["scenario"] == "outage_stress"
    assert row["message_index"] == 2
    assert 0 <= row["delivered"] <= 1
    assert row["fallback_activated"] in {0, 1}
    assert row["safe_wait_activated"] in {0, 1}
    assert row["drl_decisions"] + row["fallback_decisions"] + row["safe_wait_decisions"] == row["steps_used"]
