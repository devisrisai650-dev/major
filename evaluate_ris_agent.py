"""Reproducible multi-seed evaluation for the software-only virtual RIS backend."""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
import numpy as np
from ris_agent import QLearningRISAgent, train_agent
from ris_environment import PRIORITY_WEIGHT, RISEnvironment

SCENARIOS = {
    "light": {"noise": 0.75, "delay": 0},
    "moderate": {"noise": 1.5, "delay": 1},
    "severe": {"noise": 2.25, "delay": 2},
}
POLICIES = ("agent", "random", "fixed", "best_fixed", "myopic_noisy", "oracle")

def bootstrap_ci(values, seed=2026, samples=2000):
    values = np.asarray([v for v in values if v is not None], dtype=float)
    if values.size == 0:
        return (None, None)
    rng = np.random.default_rng(seed)
    means = np.mean(rng.choice(values, (samples, values.size), replace=True), axis=1)
    return tuple(np.percentile(means, [2.5, 97.5]))

def choose_action(env, observation, policy, rng, fixed_action=None):
    mask = env.action_mask()
    valid = np.flatnonzero(mask)
    if policy == "agent":
        return env.agent.choose_action(observation, mask, explore=False)
    if policy in {"myopic_noisy", "oracle"}:
        return env.greedy_baseline_action(observation)
    if policy == "random":
        return int(rng.choice(valid))
    if policy == "fixed":
        return 0 if mask[0] else int(valid[0])
    if policy == "best_fixed":
        if fixed_action is not None and mask[fixed_action]:
            return fixed_action
        return int(valid[0])
    raise ValueError(f"Unknown policy {policy}")

def run_episode(env, policy, episode_seed, priority, scenario, agent=None):
    env.reseed(episode_seed)
    env.observation_mode = "oracle" if policy == "oracle" else "partial"
    env.snr_noise_std_db = SCENARIOS[scenario]["noise"]
    env.observation_delay = SCENARIOS[scenario]["delay"]
    observation = env.reset(priority=priority)
    rng = np.random.default_rng(episode_seed + 991)
    fixed_action = None
    if policy == "best_fixed":
        candidate = env.greedy_baseline_action(observation)
        fixed_action = candidate
    delivered = critical_delivered = 0
    weighted_delivered = 0.0
    latency = []
    snr = []
    aoi = 0.0
    aoi_samples = []
    reconfigs = 0
    rewards = []
    for _ in range(env.max_steps):
        action = choose_action(env, observation, policy, rng, fixed_action)
        observation, reward, done, info = env.step(action)
        rewards.append(reward)
        reconfigs += int(info["changed_ris"])
        if info["delivered"]:
            delivered += 1
            weighted_delivered += PRIORITY_WEIGHT[priority]
            if priority == "CRITICAL":
                critical_delivered += 1
            latency.append(info["latency_ms"])
            snr.append(info["snr_db"])
            aoi = float(info["latency_ms"])
        else:
            aoi += float(info["latency_ms"] or 100.0)
        aoi_samples.append(aoi)
        if done:
            break
    return {
        "seed": episode_seed, "policy": policy, "scenario": scenario,
        "priority": priority, "steps": env.max_steps,
        "delivery_rate": delivered / env.max_steps,
        "critical_delivery_rate": critical_delivered / env.max_steps if priority == "CRITICAL" else np.nan,
        "priority_weighted_delivery": weighted_delivered / (env.max_steps * PRIORITY_WEIGHT[priority]),
        "mean_latency_ms": float(np.mean(latency)) if latency else np.nan,
        "mean_aoi_ms": float(np.mean(aoi_samples)),
        "mean_snr_db": float(np.mean(snr)) if snr else np.nan,
        "ris_reconfigurations": reconfigs,
        "mean_reward": float(np.mean(rewards)),
        "observation_mode": env.observation_mode,
        "observation_noise_std_db": env.snr_noise_std_db,
        "observation_delay_steps": env.observation_delay,
        "simulation_only": True,
    }

def train_and_evaluate(train_seeds, eval_seeds, episodes, steps, output_dir, learned_weight):
    output_dir.mkdir(parents=True, exist_ok=True)
    episode_rows = []
    for train_seed in train_seeds:
        env = RISEnvironment(seed=train_seed, max_steps=steps, observation_mode="partial")
        agent = QLearningRISAgent(seed=train_seed, learned_value_weight=learned_weight)
        train_agent(agent, env, episodes=episodes, max_steps=steps)
        if train_seed == train_seeds[0]:
            agent.save(output_dir.parent / "models" / "ris_q_table.npz")
        for eval_seed in eval_seeds:
            for scenario in SCENARIOS:
                for priority in PRIORITY_WEIGHT:
                    for policy in POLICIES:
                        eval_env = RISEnvironment(
                            seed=eval_seed, max_steps=steps, observation_mode="partial"
                        )
                        eval_env.agent = agent
                        row = run_episode(
                            eval_env, policy, eval_seed, priority, scenario, agent
                        )
                        row["train_seed"] = train_seed
                        row["learned_value_weight"] = learned_weight
                        episode_rows.append(row)
    fields = list(episode_rows[0])
    with (output_dir / "ris_episode_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(episode_rows)

    summary = []
    metric_names = [
        "delivery_rate", "critical_delivery_rate", "priority_weighted_delivery",
        "mean_latency_ms", "mean_aoi_ms", "mean_snr_db", "ris_reconfigurations", "mean_reward"
    ]
    for policy in POLICIES:
        for scenario in SCENARIOS:
            subset = [r for r in episode_rows if r["policy"] == policy and r["scenario"] == scenario]
            row = {"policy": policy, "scenario": scenario}
            for metric in metric_names:
                vals = [r[metric] for r in subset if np.isfinite(r[metric])]
                row[f"{metric}_mean"] = float(np.mean(vals)) if vals else np.nan
                low, high = bootstrap_ci(vals)
                row[f"{metric}_ci95_low"] = low
                row[f"{metric}_ci95_high"] = high
            summary.append(row)
    fields = list(summary[0])
    with (output_dir / "ris_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)
    return episode_rows, summary

def main():
    parser = argparse.ArgumentParser(description="Multi-seed software-only RIS evaluation")
    parser.add_argument("--train-seeds", type=int, default=10)
    parser.add_argument("--train-episodes", type=int, default=250)
    parser.add_argument("--eval-seeds", type=int, default=5)
    parser.add_argument("--eval-episodes-per-seed", type=int, default=5)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--learned-weight", type=float, default=0.05)
    parser.add_argument("--output-dir", default="outputs")
    args = parser.parse_args()
    if min(args.train_seeds, args.train_episodes, args.eval_seeds, args.eval_episodes_per_seed, args.steps) < 1:
        parser.error("all counts must be positive")
    train_seeds = [args.seed + i for i in range(args.train_seeds)]
    eval_start = args.seed + 10000
    eval_seeds = [eval_start + i for i in range(args.eval_seeds)]
    rows, summary = train_and_evaluate(
        train_seeds, eval_seeds, args.train_episodes,
        args.steps, Path(args.output_dir), args.learned_weight
    )
    print("SOFTWARE-ONLY MULTI-SEED RIS EVALUATION")
    print("All channel, RIS, delivery, latency and SNR values are simulated.")
    print(f"Independent training seeds: {len(train_seeds)}")
    print(f"Disjoint evaluation seeds: {len(eval_seeds)}")
    print(f"Episode rows: {len(rows)}")
    print("Results written to outputs/ris_episode_results.csv and outputs/ris_summary.csv")
    for row in summary:
        if row["scenario"] == "moderate":
            print(
                f"{row['policy']:>14} | delivery={row['delivery_rate_mean']:.3f} "
                f"[{row['delivery_rate_ci95_low']:.3f}, {row['delivery_rate_ci95_high']:.3f}]"
            )

if __name__ == "__main__":
    main()
