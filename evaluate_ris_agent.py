"""Train the virtual RIS agent and compare it with simple baselines."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from ris_agent import QLearningRISAgent, train_agent
from ris_environment import PRIORITY_WEIGHT, RISEnvironment


def evaluate_policy(env, policy, episodes: int, seed_offset: int = 100_000) -> dict:
    rows = []
    priority_names = list(PRIORITY_WEIGHT)
    for episode in range(episodes):
        # Same seed schedule for each policy gives comparable scenario starts.
        env.simulator.rng = np.random.default_rng(seed_offset + episode)
        observation = env.reset(priority=priority_names[episode % len(priority_names)])
        delivered = waited = reconfigurations = 0
        snr_values = []
        latency_values = []
        for _ in range(env.max_steps):
            if policy == "agent":
                action = agent_action = env.agent.choose_action(observation, env.action_mask())
            elif policy == "myopic":
                action = env.greedy_baseline_action()
            elif policy == "fixed":
                action = 0 if env.action_mask()[0] else env.greedy_baseline_action()
            else:
                raise ValueError(f"Unknown policy {policy}")
            observation, _, done, info = env.step(action)
            delivered += int(info["delivered"])
            waited += int(info["waited"])
            reconfigurations += int(info["changed_ris"])
            if info["delivered"]:
                snr_values.append(info["snr_db"])
                latency_values.append(info["latency_ms"])
            if done:
                break
        rows.append({
            "delivery_rate": delivered / env.max_steps,
            "wait_rate": waited / env.max_steps,
            "mean_delivered_snr_db": float(np.mean(snr_values)) if snr_values else None,
            "mean_delivered_latency_ms": float(np.mean(latency_values)) if latency_values else None,
            "ris_reconfigurations": reconfigurations,
        })
    keys = rows[0].keys()
    return {key: float(np.mean([row[key] for row in rows if row[key] is not None]))
            if any(row[key] is not None for row in rows) else None for key in keys}


def main():
    parser = argparse.ArgumentParser(description="Software-only virtual channel/RIS experiment")
    parser.add_argument("--episodes", type=int, default=1200, help="Q-learning training episodes")
    parser.add_argument("--eval-episodes", type=int, default=80, help="Evaluation episodes per policy")
    parser.add_argument("--steps", type=int, default=80, help="Steps per episode")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="data/ris_simulation_results.csv")
    parser.add_argument("--model", default="models/ris_q_table.npz")
    args = parser.parse_args()
    if min(args.episodes, args.eval_episodes, args.steps) <= 0:
        parser.error("episode counts and steps must be positive")

    training_env = RISEnvironment(seed=args.seed, max_steps=args.steps)
    agent = QLearningRISAgent(seed=args.seed)
    rewards = train_agent(agent, training_env, episodes=args.episodes)
    agent.decay_exploration()
    model_path = Path(args.model)
    agent.save(model_path)

    results = []
    for name in ("agent", "myopic", "fixed"):
        env = RISEnvironment(seed=args.seed + 1, max_steps=args.steps)
        env.agent = agent
        summary = evaluate_policy(env, name, args.eval_episodes, seed_offset=args.seed + 10_000)
        summary["policy"] = name
        results.append(summary)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    print("SOFTWARE-ONLY CHANNEL + RIS SIMULATION")
    print("All candidates, fading, measurements, and link outcomes are simulated.")
    print(f"Training episodes: {args.episodes}; evaluation episodes/policy: {args.eval_episodes}")
    print(f"Mean final-100 training reward: {np.mean(rewards[-min(100, len(rewards)):]):.3f}")
    print("\nPolicy comparison (per message attempt):")
    for row in results:
        print(f"{row['policy']:>8} | delivery={row['delivery_rate']:.3f} | "
              f"wait={row['wait_rate']:.3f} | delivered SNR={_format(row['mean_delivered_snr_db'])} dB | "
              f"delivered latency={_format(row['mean_delivered_latency_ms'])} ms | "
              f"RIS changes/episode={row['ris_reconfigurations']:.1f}")
    print(f"\nQ-table: {model_path}")
    print(f"Results CSV: {output_path}")
    print("This experiment does not establish real-world frequency or link availability.")


def _format(value):
    return "n/a" if value is None else f"{value:.2f}"


if __name__ == "__main__":
    main()
