"""Paired DRL-only versus rule-based orchestration stress evaluation.

Every row is one simulated critical-message delivery episode. Controllers use
matched seeds within each scenario/message. This tests whether fallback/wait
paths actually activate under stress; it does not imply field performance.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

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
        "rain_mm": 60.0,
        "flow_velocity_mps": 1.8,
        "water_depth_m": 1.8,
        "debris_density": 0.9,
        "los_obstruction": 0.9,
        "node_outage_probability": 0.12,
        "node_recovery_probability": 0.15,
    },
    "outage_stress": {
        "rain_mm": 80.0,
        "flow_velocity_mps": 2.0,
        "water_depth_m": 2.0,
        "debris_density": 1.0,
        "los_obstruction": 1.0,
        "node_outage_probability": 0.45,
        "node_recovery_probability": 0.05,
    },
}


def run_episode(
    policy_path: Path,
    seed: int,
    steps: int,
    scenario: str,
    controller: str,
    message_index: int = 0,
) -> dict:
    if controller not in {"drl_only", "orchestrated"}:
        raise ValueError(f"Unknown controller: {controller}")
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
        "message_index": message_index,
        "priority": "CRITICAL",
        "delivered": int(delivered),
        "steps_used": len(policies),
        "delivery_rate": float(delivered),
        "mean_attempt_latency_ms": sum(latencies) / len(latencies) if latencies else None,
        "drl_decisions": policies.count("drl_ris_cnoma"),
        "fallback_decisions": policies.count("fixed_ris_cnoma_fallback"),
        "safe_wait_decisions": policies.count("safe_wait"),
        "fallback_activated": int("fixed_ris_cnoma_fallback" in policies),
        "safe_wait_activated": int("safe_wait" in policies),
        "steps_with_outage": outage_steps,
        "simulation_only": True,
    }



def _bootstrap_mean_ci(values, samples: int = 2000, seed: int = 12345):
    """Percentile bootstrap CI for paired per-message differences."""
    values = np.asarray(list(values), dtype=float)
    if values.size == 0:
        return None, None
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(samples, values.size), replace=True).mean(axis=1)
    low, high = np.percentile(draws, [2.5, 97.5])
    return float(low), float(high)


def summarize_paired_results(rows: list[dict], bootstrap_samples: int = 2000) -> list[dict]:
    """Summarize matched DRL/orchestrated episodes with paired bootstrap CIs."""
    pairs = {}
    for row in rows:
        key = (row["scenario"], int(row["seed"]), int(row["message_index"]))
        controller = row["controller"]
        if controller not in {"drl_only", "orchestrated"}:
            raise ValueError(f"Unknown controller in evaluation rows: {controller}")
        if controller in pairs.setdefault(key, {}):
            raise ValueError(f"Duplicate controller row for paired episode {key}: {controller}")
        pairs[key][controller] = row

    by_scenario = {}
    for key, controllers in pairs.items():
        if set(controllers) != {"drl_only", "orchestrated"}:
            raise ValueError(f"Incomplete controller pair for episode {key}")
        by_scenario.setdefault(key[0], []).append(controllers)

    summaries = []
    for scenario in SCENARIOS:
        matched = by_scenario.get(scenario, [])
        if not matched:
            continue
        drl_delivery = np.asarray([float(p["drl_only"]["delivered"]) for p in matched])
        orch_delivery = np.asarray([float(p["orchestrated"]["delivered"]) for p in matched])
        delivery_diffs = orch_delivery - drl_delivery
        delivery_low, delivery_high = _bootstrap_mean_ci(
            delivery_diffs, samples=bootstrap_samples, seed=12345
        )

        latency_pairs = [
            (float(p["drl_only"]["mean_attempt_latency_ms"]),
             float(p["orchestrated"]["mean_attempt_latency_ms"]))
            for p in matched
            if p["drl_only"]["mean_attempt_latency_ms"] is not None
            and p["orchestrated"]["mean_attempt_latency_ms"] is not None
        ]
        latency_diffs = np.asarray([b - a for a, b in latency_pairs], dtype=float)
        latency_low, latency_high = _bootstrap_mean_ci(
            latency_diffs, samples=bootstrap_samples, seed=54321
        )
        summaries.append({
            "scenario": scenario,
            "paired_episodes": len(matched),
            "drl_delivery_rate": float(drl_delivery.mean()),
            "orchestrated_delivery_rate": float(orch_delivery.mean()),
            "delivery_difference_orchestrated_minus_drl": float(delivery_diffs.mean()),
            "delivery_difference_ci95_low": delivery_low,
            "delivery_difference_ci95_high": delivery_high,
            "latency_pairs": len(latency_pairs),
            "drl_mean_attempt_latency_ms": (
                float(np.mean([a for a, _ in latency_pairs])) if latency_pairs else None
            ),
            "orchestrated_mean_attempt_latency_ms": (
                float(np.mean([b for _, b in latency_pairs])) if latency_pairs else None
            ),
            "latency_difference_ms_orchestrated_minus_drl": (
                float(latency_diffs.mean()) if latency_pairs else None
            ),
            "latency_difference_ci95_low_ms": latency_low,
            "latency_difference_ci95_high_ms": latency_high,
            "orchestrator_fallback_activation_rate": float(np.mean([
                p["orchestrated"]["fallback_activated"] for p in matched
            ])),
            "orchestrator_safe_wait_activation_rate": float(np.mean([
                p["orchestrated"]["safe_wait_activated"] for p in matched
            ])),
            "simulation_only": True,
        })
    return summaries


def write_paired_summary(rows: list[dict], output_path: Path, bootstrap_samples: int = 2000):
    summary = summarize_paired_results(rows, bootstrap_samples=bootstrap_samples)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if summary:
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
    return summary

def main():
    parser = argparse.ArgumentParser(
        description="Paired DRL-only versus orchestrated software simulation"
    )
    parser.add_argument("--policy", default="models/ris_q_table.npz")
    parser.add_argument("--seeds", type=int, default=5, help="Independent seed groups")
    parser.add_argument("--messages", type=int, default=20, help="Messages per seed/scenario")
    parser.add_argument("--steps", type=int, default=40, help="Maximum attempts per message")
    parser.add_argument("--output", default="outputs/orchestrator_comparison.csv")
    parser.add_argument("--summary-output", default=None, help="Paired summary CSV; defaults beside --output")
    args = parser.parse_args()
    if args.seeds < 1 or args.messages < 1 or args.steps < 1:
        parser.error("--seeds, --messages and --steps must be positive")
    policy_path = Path(args.policy)
    if not policy_path.exists():
        parser.error(
            f"Policy file not found: {policy_path}. Run evaluate_ris_agent.py first."
        )

    rows = []
    for scenario_index, scenario in enumerate(SCENARIOS):
        for seed_group in range(args.seeds):
            for message_index in range(args.messages):
                # Both controllers receive exactly the same environment seed.
                seed = 30000 + scenario_index * 100000 + seed_group * args.messages + message_index
                for controller in ("drl_only", "orchestrated"):
                    rows.append(run_episode(
                        policy_path, seed, args.steps, scenario, controller, message_index
                    ))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary_path = (
        Path(args.summary_output)
        if args.summary_output
        else output.with_name(f"{output.stem}_paired_summary.csv")
    )
    summary = write_paired_summary(rows, summary_path)
    print("SIMULATION-ONLY ORCHESTRATOR STRESS COMPARISON")
    print(f"Rows: {len(rows)}")
    print(f"Episode output: {output}")
    print(f"Paired summary: {summary_path}")
    for item in summary:
        print(
            f"{item['scenario']:>13} | paired n={item['paired_episodes']:>4} | "
            f"delivery delta={item['delivery_difference_orchestrated_minus_drl']:+.3f} "
            f"(95% bootstrap CI {item['delivery_difference_ci95_low']:+.3f}, "
            f"{item['delivery_difference_ci95_high']:+.3f}) | "
            f"latency delta={item['latency_difference_ms_orchestrated_minus_drl']} ms"
        )
    for scenario in SCENARIOS:
        for controller in ("drl_only", "orchestrated"):
            selected = [
                row for row in rows
                if row["scenario"] == scenario and row["controller"] == controller
            ]
            delivery = sum(row["delivered"] for row in selected) / len(selected)
            fallback_rate = sum(row["fallback_activated"] for row in selected) / len(selected)
            wait_rate = sum(row["safe_wait_activated"] for row in selected) / len(selected)
            print(
                f"{scenario:>13} | {controller:>12} | "
                f"critical delivery={delivery:.3f} | "
                f"fallback-active={fallback_rate:.3f} | safe-wait-active={wait_rate:.3f} | "
                f"n={len(selected)}"
            )
    print("Review fallback activation and paired delivery differences; do not infer field performance.")


if __name__ == "__main__":
    main()
