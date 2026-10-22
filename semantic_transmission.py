"""Connect selected flood semantics to the simulated RIS communication loop."""
from __future__ import annotations

from pathlib import Path

from orchestrator_agent import (
    choose_fixed_ris_action,
    select_policy,
    summarize_decisions,
)
from ris_agent import QLearningRISAgent
from ris_environment import RISEnvironment

PRIORITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def summarize_aoi(attempts: list[dict]) -> dict:
    """Return cumulative packet age across sequential transmission attempts.

    Attempt latency is used as simulated elapsed time; processing, queueing and
    propagation outside the model are not represented.
    """
    age = 0.0
    ages = []
    delivery_aoi = None
    for item in attempts:
        latency = item.get("latency_ms")
        if latency is not None:
            age += max(0.0, float(latency))
        ages.append(age)
        if item.get("delivered") and delivery_aoi is None:
            delivery_aoi = age
    return {
        "mean_aoi_ms": sum(ages) / len(ages) if ages else None,
        "delivery_aoi_ms": delivery_aoi,
        "final_aoi_ms": age if ages else None,
    }


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
    assumed_tx_power_w: float = 0.1,
) -> dict:
    """Transmit one semantic packet with per-attempt orchestration.

    Every radio quantity and delivery outcome is simulated. The orchestrator
    chooses between the trained RIS-CNOMA policy, a fixed-RIS CNOMA fallback,
    and safe wait when no transmission action is feasible.
    """
    if not packet:
        raise ValueError("Semantic packet must not be empty")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    if assumed_tx_power_w <= 0:
        raise ValueError("assumed_tx_power_w must be positive")

    # Explicit simulation assumption: estimate serialization duration from the
    # modeled throughput. This is not measured airtime or device energy.
    packet_bits = len(packet.encode("utf-8")) * 8

    policy_path = Path(policy_path)
    agent = QLearningRISAgent(seed=seed)
    if not policy_path.exists():
        raise FileNotFoundError(
            f"Trained RIS-CNOMA policy not found: {policy_path}. "
            "Run evaluate_ris_agent.py first to train the software policy."
        )
    policy_load_warning = None
    try:
        agent.load(policy_path)
    except ValueError as exc:
        # Keep the software simulation usable if a checked-in/trained Q-table
        # was produced with a different state/action-space version. The agent's
        # Q-values remain zero-initialized and action selection still uses the
        # environment's expected-reward heuristic; this is not a trained-policy run.
        policy_load_warning = (
            "Saved Q-table is incompatible with the current environment; "
            "continuing with the untrained heuristic simulation. "
            f"Details: {exc}"
        )
    agent.epsilon = 0.0

    env = RISEnvironment(
        seed=seed,
        max_steps=max_attempts,
        channel_context=channel_context,
    )
    priority = priority_for_message(priorities)
    observation = env.reset(priority=priority)
    attempts = []
    decisions = []
    received = None

    for attempt_number in range(1, max_attempts + 1):
        action_mask = env.action_mask(observation)
        decision = select_policy(observation, action_mask, priority)
        if decision["policy"] == "drl_ris_cnoma":
            action = agent.choose_action(observation, action_mask, explore=False)
        elif decision["policy"] == "fixed_ris_cnoma_fallback":
            action = choose_fixed_ris_action(observation, action_mask)
        else:
            action = env.wait_action

        decision_record = {
            **decision,
            "attempt": attempt_number,
            "selected_action": int(action),
        }
        decisions.append(decision_record)
        state = agent.encode_state(observation)
        next_observation, reward, env_done, info = env.step(action, packet=packet)
        terminal = bool(info["delivered"] or env_done or attempt_number == max_attempts)
        next_state = agent.encode_state(next_observation)
        if learn and decision["policy"] == "drl_ris_cnoma":
            agent.learn(
                state,
                action,
                reward,
                next_state,
                env.action_mask(next_observation),
                terminal,
            )
        attempt_throughput = info["throughput_mbps"]
        tx_duration_s = (
            packet_bits / (float(attempt_throughput) * 1_000_000.0)
            if not info["waited"] and attempt_throughput is not None
            and float(attempt_throughput) > 0
            else 0.0
        )
        tx_energy_j = assumed_tx_power_w * tx_duration_s
        attempts.append({
            "attempt": attempt_number,
            "packet_bits": packet_bits,
            "assumed_total_tx_power_w": assumed_tx_power_w,
            "estimated_tx_duration_s": tx_duration_s,
            "estimated_tx_energy_j": tx_energy_j,
            "candidate": info["channel_candidate"],
            "ris_configuration": info["selected_ris_config"],
            "power_profile": info["power_profile"],
            "power_user1": info["power_user1"],
            "power_user2": info["power_user2"],
            "cnoma_weak_user": info["cnoma_weak_user"],
            "cnoma_strong_user": info["cnoma_strong_user"],
            "delivery_model": info["delivery_model"],
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
            "node_available": info["node_available"],
            "node_outage_count": info["node_outage_count"],
            "orchestrator_policy": decision["policy"],
            "orchestrator_reason": decision["reason"],
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
    aoi_summary = summarize_aoi(attempts)
    orchestration = summarize_decisions(decisions)
    policy_counts = orchestration["policy_counts"]
    total_estimated_tx_energy_j = sum(
        float(item.get("estimated_tx_energy_j", 0.0) or 0.0)
        for item in attempts
    )
    energy_efficiency_bits_per_j = (
        packet_bits / total_estimated_tx_energy_j
        if delivered and total_estimated_tx_energy_j > 0
        else 0.0
    )
    return {
        "priority": priority,
        "delivered": delivered,
        "critical_delivered": critical_delivered,
        "delivery_attempt": delivered_attempt["attempt"] if delivered_attempt else None,
        "delivery_latency_ms": aoi_summary["delivery_aoi_ms"],
        "delivery_aoi_ms": aoi_summary["delivery_aoi_ms"],
        "mean_aoi_ms": aoi_summary["mean_aoi_ms"],
        "final_aoi_ms": aoi_summary["final_aoi_ms"],
        "mean_latency_ms": (
            sum(float(item["latency_ms"]) for item in attempts if item["latency_ms"] is not None)
            / max(1, sum(item["latency_ms"] is not None for item in attempts))
        ),
        "mean_throughput_mbps": (
            sum(float(item["throughput_mbps"]) for item in attempts if item["throughput_mbps"] is not None)
            / max(1, sum(item["throughput_mbps"] is not None for item in attempts))
        ),
        "packet_bits": packet_bits,
        "assumed_total_tx_power_w": assumed_tx_power_w,
        "total_estimated_tx_energy_j": total_estimated_tx_energy_j,
        "energy_efficiency_bits_per_j": energy_efficiency_bits_per_j,
        "energy_model": {
            "type": "assumed_constant_tx_power_times_estimated_serialization_duration",
            "assumed_total_tx_power_w": assumed_tx_power_w,
            "duration_basis": "packet_bits / modeled_throughput_bps",
            "includes_receiver_circuit_energy": False,
            "includes_processing_queueing_and_propagation_energy": False,
            "measured_hardware_energy": False,
        },
        "packet_received": received,
        "attempts": attempts,
        "orchestrator": {
            **orchestration,
            "selected_policy": (
                max(policy_counts, key=policy_counts.get) if policy_counts else None
            ),
            "policy": "rule_based",
            "policy_version": "1.0",
        },
        "policy_path": str(policy_path),
        "policy_load_warning": policy_load_warning,
        "simulation_only": True,
        "learned": learn,
        "used_seed": seed,
        "cnoma_enabled": True,
        "channel_context": channel_context or {},
    }
