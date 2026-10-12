"""Paired simulation comparison: DRL-only versus rule-based orchestration."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from orchestrator_agent import choose_fixed_ris_action, select_policy
from ris_agent import QLearningRISAgent
from ris_environment import RISEnvironment


SCENARIOS = {
    "light": {
        "rain_mm": 2.0,
        "flow_velocity_mps": 0.2,
        "water_depth_m": 0.2,
        "debris_density": 0.1,
        "los_obstruction": 0.1,
        "node_outage_probability": 0.01,
        "node_recovery_probability": 0.35,
    },
    "moderate": {
        "rain_mm": 12.0,
        "flow_velocity_mps": 0.8,
        "water_depth_m": 0.8,
        "debris_density": 0.35,
        "los_obstruction": 0.4,
        "node_outage_probability": 0.04,
        "node_recovery_probability": 0.25,
    },
    "severe": {
        "rain_mm": 35.0,
        "flow_velocity_mps": 1.6,
        "water_depth_m": 1.6,
        "debris_density": 0.8,
        "los_obstruction": 0.8,
        "node_outage_probability": 0.12,
        "node_recovery_probability": 0.15,
    },
}


def run_episode(policy_path: Path, seed: int, steps: int, scenario: str, controller: str):
    agent = QLearningRISAgent(seed=seed)
    agent.load(policy_path)
    agent.epsilon = 0.0
    env = RISEnvironment(
        seed=seed,
        max_steps=steps,
        channel_context=SCENARIOS[scenario],
    )
    observation = env.reset(priority="CRITICAL")
    delivered = False
    latencies = []
    policies = []
    outage_steps = 0

    for _ in range(steps):
        mask = env.action_mask(observation)
        if controller == "drl_only":
            policy = "drl_ris_cnoma"
            action = agent.choose_action(observation, mask, explore=False)
        else:
            decision = select_policy(observation, mask, "CRITICAL")
            policy = decision["policy"]
            if policy == "drl_ris_cnoma":
                action = agent.choose_action(observation, mask, explore=False)
            elif policy == "fixed_ris_cnoma_fallback":
                action = choose_fixed_ris_action(observation, mask)
            else:
                action = env.wait_action

        policies.append(policy)
        next_observation, _, done, info = env.step(action)
        if info["latency_ms"] is not None:
            latencies.append(float(info["latency_ms"]))
        outage_steps += int(info.get("node_outage_count", 0) > 0)
        delivered = bool(info["delivered"])
        observation = next_observation
        if delivered or done:
            break

    return {
        "scenario": scenario,
        "controller": controller,
        "seed": seed,
        "priority": "CRITICAL",
        "delivered": int(delivered),
        "steps_used": len(policies),
        "delivery_rate": float(delivered),
        "mean_attempt_latency_ms": sum(latencies) / len(latencies) if latencies else None,
        "drl_decisions": policies.count("drl_ris_cnoma"),
        "fallback_decisions": policies.count("fixed_ris_cnoma_fallback"),
        "safe_wait_decisions": policies.count("safe_wait"),
        "steps_with_outage": outage_steps,
        "simulation_only": True,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Paired DRL-only versus orchestrated software simulation"
    )
    parser.add_argument("--policy", default="models/ris_q_table.npz")
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--output", default="outputs/orchestrator_comparison.csv")
    args = parser.parse_args()
    if args.seeds < 1 or args.steps < 1:
        parser.error("--seeds and --steps must be positive")
    policy_path = Path(args.policy)
    if not policy_path.exists():
        parser.error(
            f"Policy file not found: {policy_path}. Run evaluate_ris_agent.py first."
        )

    rows = []
    for scenario in SCENARIOS:
        for index in range(args.seeds):
            seed = 30000 + index
            for controller in ("drl_only", "orchestrated"):
                rows.append(
                    run_episode(policy_path, seed, args.steps, scenario, controller)
                )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print("SIMULATION-ONLY ORCHESTRATOR COMPARISON")
    print(f"Rows: {len(rows)}")
    print(f"Output: {output}")
    for scenario in SCENARIOS:
        for controller in ("drl_only", "orchestrated"):
            selected = [
                row for row in rows
                if row["scenario"] == scenario and row["controller"] == controller
            ]
            delivery = sum(row["delivered"] for row in selected) / len(selected)
            print(
                f"{scenario:>8} | {controller:>12} | "
                f"critical delivery={delivery:.3f} | n={len(selected)}"
            )
    print("These are software simulation results, not field measurements.")


if __name__ == "__main__":
    main()
