from pathlib import Path

from ris_agent import QLearningRISAgent
from semantic_transmission import transmit_semantic_message


def test_transmission_returns_per_attempt_orchestrator_decisions(tmp_path: Path):
    policy_path = tmp_path / "ris_q_table.npz"
    QLearningRISAgent(seed=10).save(policy_path)
    result = transmit_semantic_message(
        packet="FLOOD_ASSESSMENT=NOT_ASSESSED | PRIORITY=HIGH",
        priorities={"rain": {"available": True, "priority": "HIGH"}},
        policy_path=policy_path,
        max_attempts=3,
        seed=42,
        learn=False,
    )

    orchestrator = result["orchestrator"]
    assert result["simulation_only"] is True
    assert orchestrator["policy"] == "rule_based"
    assert orchestrator["decision_count"] == len(orchestrator["decisions"])
    assert orchestrator["decision_count"] == len(result["attempts"])
    assert sum(orchestrator["policy_counts"].values()) == len(result["attempts"])
    assert all("orchestrator_policy" in attempt for attempt in result["attempts"])
    assert all(
        decision["policy"] in {
            "drl_ris_cnoma",
            "fixed_ris_cnoma_fallback",
            "safe_wait",
        }
        for decision in orchestrator["decisions"]
    )
    assert policy_path.exists()
