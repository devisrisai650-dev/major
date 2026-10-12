from evaluate_orchestrator import SCENARIOS, run_episode, summarize_paired_results
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



def test_paired_summary_reports_direction_and_bootstrap_interval():
    rows = []
    values = [
        (1, 1, 20.0, 21.0),
        (0, 1, 30.0, 32.0),
        (1, 1, 18.0, 19.0),
        (1, 0, 25.0, 24.0),
    ]
    for seed, (drl_delivery, orch_delivery, drl_latency, orch_latency) in enumerate(values, start=1):
        for controller, delivered, latency in (
            ("drl_only", drl_delivery, drl_latency),
            ("orchestrated", orch_delivery, orch_latency),
        ):
            rows.append({
                "scenario": "light",
                "controller": controller,
                "seed": seed,
                "message_index": seed - 1,
                "delivered": delivered,
                "mean_attempt_latency_ms": latency,
                "fallback_activated": int(controller == "orchestrated" and seed == 2),
                "safe_wait_activated": int(controller == "orchestrated" and seed == 4),
            })

    summary = summarize_paired_results(rows, bootstrap_samples=500)
    assert len(summary) == 1
    result = summary[0]
    assert result["paired_episodes"] == 4
    assert result["delivery_difference_orchestrated_minus_drl"] == 0.0
    assert result["delivery_difference_ci95_low"] <= 0.0
    assert result["delivery_difference_ci95_high"] >= 0.0
    assert result["latency_difference_ms_orchestrated_minus_drl"] == 0.75
    assert result["orchestrator_fallback_activation_rate"] == 0.25
    assert result["orchestrator_safe_wait_activation_rate"] == 0.25
    assert result["simulation_only"] is True


def test_paired_summary_rejects_unmatched_episodes():
    rows = [{
        "scenario": "light",
        "controller": "drl_only",
        "seed": 1,
        "message_index": 0,
        "delivered": 1,
        "mean_attempt_latency_ms": 20.0,
        "fallback_activated": 0,
        "safe_wait_activated": 0,
    }]
    import pytest

    with pytest.raises(ValueError, match="Incomplete controller pair"):
        summarize_paired_results(rows)
