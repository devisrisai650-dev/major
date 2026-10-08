"""Connect selected flood semantics to the simulated RIS communication loop."""
from __future__ import annotations

from pathlib import Path

from ris_agent import QLearningRISAgent
from ris_environment import RISEnvironment

PRIORITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def priority_for_message(priorities: dict) -> str:
    available = [
        item["priority"]
        for item in priorities.values()
        if item.get("available") and item.get("priority") in PRIORITY_ORDER
    ]
    return max(available, key=PRIORITY_ORDER.get) if available else "LOW"


def transmit_semantic_message(
    packet: str,
    priorities: dict,
    policy_path: str | Path,
    max_attempts: int = 5,
    seed: int = 2026,
    learn: bool = False,
) -> dict:
    """Transmit one semantic packet; learning is opt-in."""
    if not packet:
        raise ValueError("Semantic packet must not be empty")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")

    policy_path = Path(policy_path)
    agent = QLearningRISAgent(seed=seed)
    if not policy_path.exists():
        raise FileNotFoundError(
            f"Trained RIS policy not found: {policy_path}. "
            "Run evaluate_ris_agent.py first to train the software policy."
        )
    agent.load(policy_path)
    agent.epsilon = 0.0

    env = RISEnvironment(\n        seed=seed, max_steps=max_attempts,\n        channel_context=channel_context,\n        node_loss_probability=node_loss_probability,\n    )
    priority = priority_for_message(priorities)
    observation = env.reset(priority=priority)
    attempts = []
    received = None

    for attempt_number in range(1, max_attempts + 1):
        state = agent.encode_state(observation)
        action = agent.choose_action(
            observation, env.action_mask(observation), explore=False
        )
        next_observation, reward, env_done, info = env.step(action, packet=packet)
        terminal = bool(
            info["delivered"] or env_done or attempt_number == max_attempts
        )
        next_state = agent.encode_state(next_observation)
        if learn:
            agent.learn(
                state,
                action,
                reward,
                next_state,
                env.action_mask(next_observation),
                terminal,
            )
        attempts.append({
            "attempt": attempt_number,
            "candidate": info["channel_candidate"],
            "ris_configuration": info["selected_ris_config"],
            "channel_condition": info["channel_condition"],
            "snr_db": info["snr_db"],
            "latency_ms": info["latency_ms"],
            "delivered": info["delivered"],
            "waited": info["waited"],
            "reward": reward,
        })
        observation = next_observation
        if info["delivered"]:
            received = info["receiver_packet"]
            break

    if learn:
        agent.save(policy_path)

    return {
        "priority": priority,
        "delivered": received == packet,
        "packet_received": received,
        "attempts": attempts,
        "policy_path": str(policy_path),
        "simulation_only": True,
        "learned": learn,
        "used_seed": seed,
    }
