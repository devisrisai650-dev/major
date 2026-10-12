"""Transparent policy orchestrator for the software-only FloodAI link.

The orchestrator selects among implemented control paths; it does not infer a
real-world flood state. The trained DRL policy handles normal conditions, a
deterministic no-RIS CNOMA fallback handles degraded observations, and a safe
wait action is used when no transmission action is feasible.
"""
from __future__ import annotations

from collections import Counter


DEFAULT_DEGRADED_SNR_DB = 3.0


def select_policy(
    observation: dict,
    action_mask,
    priority: str,
    degraded_snr_db: float = DEFAULT_DEGRADED_SNR_DB,
) -> dict:
    """Choose a supported policy from the current simulated observation."""
    if priority not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        raise ValueError(f"Unknown message priority: {priority}")
    if degraded_snr_db < -30 or degraded_snr_db > 40:
        raise ValueError("degraded_snr_db must be between -30 and 40 dB")

    mask = list(bool(value) for value in action_mask)
    if len(mask) < 2:
        raise ValueError("action_mask must include transmission and wait actions")
    wait_action = len(mask) - 1
    feasible_actions = [index for index, allowed in enumerate(mask[:-1]) if allowed]

    node_available = observation.get("node_available")
    available_nodes = (
        int(sum(bool(value) for value in node_available))
        if node_available is not None else None
    )
    snr = observation.get("snr_db")
    availability = observation.get("available")
    usable_snr = []
    if snr is not None and availability is not None:
        for channel_index, row in enumerate(availability):
            for ris_index, available in enumerate(row):
                if available:
                    try:
                        usable_snr.append(float(snr[channel_index][ris_index]))
                    except (IndexError, TypeError, ValueError):
                        continue
    best_snr = max(usable_snr) if usable_snr else None

    if not feasible_actions:
        return {
            "policy": "safe_wait",
            "reason": "No transmission action is feasible under the current availability mask.",
            "priority": priority,
            "best_observed_snr_db": best_snr,
            "available_nodes": available_nodes,
            "wait_action": wait_action,
            "simulation_only": True,
        }

    if best_snr is not None and best_snr < degraded_snr_db:
        availability = observation.get("available", [])
        n_channels = len(availability)
        n_ris_configs = len(availability[0]) if n_channels else 0
        fixed_ris_feasible = any(
            mask[power * n_channels * n_ris_configs + channel * n_ris_configs]
            for power in range(3)
            for channel in range(n_channels)
            if power * n_channels * n_ris_configs + channel * n_ris_configs < len(mask) - 1
        )
        if fixed_ris_feasible:
            policy = "fixed_ris_cnoma_fallback"
            reason = (
                f"Best observed feasible SNR ({best_snr:.2f} dB) is below the "
                f"degraded-link threshold ({degraded_snr_db:.2f} dB); use the "
                "deterministic CNOMA fallback with RIS configuration zero."
            )
        else:
            policy = "drl_ris_cnoma"
            reason = (
                "The link is degraded but no fixed-RIS action is feasible; "
                "delegate to the trained DRL policy rather than selecting an "
                "infeasible fallback."
            )
    else:
        policy = "drl_ris_cnoma"
        reason = (
            "At least one transmission action is feasible and the observed "
            "link does not meet the degraded-link fallback condition; delegate "
            "RIS/resource selection to the trained DRL policy."
        )

    return {
        "policy": policy,
        "reason": reason,
        "priority": priority,
        "best_observed_snr_db": best_snr,
        "available_nodes": available_nodes,
        "wait_action": wait_action,
        "simulation_only": True,
    }


def choose_fixed_ris_action(observation: dict, action_mask) -> int:
    """Choose the strongest feasible CNOMA action while holding RIS config 0."""
    mask = list(bool(value) for value in action_mask)
    wait_action = len(mask) - 1
    snr = observation["snr_db"]
    feasibility = observation.get("cnoma_delivery_feasibility")
    n_channels = len(observation["available"])
    n_ris_configs = len(observation["available"][0]) if n_channels else 0
    if not n_channels or not n_ris_configs:
        return wait_action

    choices = []
    for power_profile in range(3):
        for channel in range(n_channels):
            action = power_profile * n_channels * n_ris_configs + channel * n_ris_configs
            if action >= len(mask) - 1 or not mask[action]:
                continue
            score = (
                float(feasibility[channel][0][power_profile])
                if feasibility is not None else float(snr[channel][0])
            )
            snr_score = float(snr[channel][0])
            choices.append((score, snr_score, -power_profile, -channel, action))
    return max(choices)[-1] if choices else wait_action


def summarize_decisions(decisions: list[dict]) -> dict:
    """Aggregate the actual policy choices made during one simulated message."""
    counts = Counter(item["policy"] for item in decisions)
    return {
        "decisions": decisions,
        "policy_counts": dict(sorted(counts.items())),
        "decision_count": len(decisions),
        "simulation_only": True,
    }
