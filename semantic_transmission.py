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
    channel_context: dict | None = None,
) -> dict:
    """Transmit one semantic packet through the software RIS-CNOMA loop."""
    if not packet:
        raise ValueError("Semantic packet must not be empty")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")

    policy_path = Path(policy_path)
    agent = QLearningRISAgent(seed=seed)
    if not policy_path.exists():
        raise FileNotFoundError(
            f"Trained RIS-CNOMA policy not found: {policy_path}. "
            "Run evaluate_ris_agent.py first to train the software policy."
        )
    agent.load(policy_path)
    agent.epsilon = 0.0

    env = RISEnvironment(
        seed=seed,
        max_steps=max_attempts,
        channel_context=channel_context,
    )
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
        terminal = bool(info["delivered"] or env_done or attempt_number == max_attempts)
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
            "power_profile": info["power_profile"],
            "power_user1": info["power_user1"],
            "power_user2": info["power_user2"],
            "channel_condition": info["channel_condition"],
            "snr_db": info["snr_db"],
            "user1_sinr_db": info["user1_sinr_db"],
            "user2_sinr_db": info["user2_sinr_db"],
            "sic_success": info["sic_success"],
            "cnoma_user1_decoded": info["cnoma_user1_decoded"],
            "cnoma_user2_decoded": info["cnoma_user2_decoded"],
            "latency_ms": info["latency_ms"],
            "throughput_mbps": info["throughput_mbps"],
            "delivered": info["delivered"],
            "waited": info["waited"],
            "rain_attenuation_db": info["rain_attenuation_db"],
            "doppler_hz": info["doppler_hz"],
            "reward": reward,
        })
        observation = next_observation
        if info["delivered"]:
            received = info["receiver_packet"]
            break

    if learn:
        agent.save(policy_path)

    delivered = received == packet
    delivered_attempt = next((item for item in attempts if item["delivered"]), None)
    critical_delivered = delivered and priority == "CRITICAL"
    return {
        "priority": priority,
        "delivered": delivered,
        "critical_delivered": critical_delivered,
        "delivery_attempt": delivered_attempt["attempt"] if delivered_attempt else None,
        "delivery_latency_ms": delivered_attempt["latency_ms"] if delivered_attempt else None,
        "delivery_aoi_ms": delivered_attempt["latency_ms"] if delivered_attempt else None,
        "mean_latency_ms": (
            sum(float(item["latency_ms"]) for item in attempts if item["latency_ms"] is not None)
            / max(1, sum(item["latency_ms"] is not None for item in attempts))
        ),
        "mean_throughput_mbps": (
            sum(float(item["throughput_mbps"]) for item in attempts if item["throughput_mbps"] is not None)
            / max(1, sum(item["throughput_mbps"] is not None for item in attempts))
        ),
        "packet_received": received,
        "attempts": attempts,
        "policy_path": str(policy_path),
        "simulation_only": True,
        "learned": learn,
        "used_seed": seed,
        "cnoma_enabled": True,
        "channel_context": channel_context or {},
    }
