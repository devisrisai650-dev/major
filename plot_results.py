"""Create plots from the final multi-seed simulation summary CSVs."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

OUT = Path(__file__).resolve().parent / "outputs"


def plot_metric(summary, metric, ylabel, filename):
    fig, ax = plt.subplots(figsize=(10, 5))
    for scenario in summary["scenario"].unique():
        data = summary[summary["scenario"] == scenario]
        ax.errorbar(
            data["policy"], data[f"{metric}_mean"],
            yerr=[
                data[f"{metric}_mean"] - data[f"{metric}_ci95_low"],
                data[f"{metric}_ci95_high"] - data[f"{metric}_mean"],
            ],
            fmt="o-", capsize=4, label=scenario,
        )
    ax.set_xlabel("Policy")
    ax.set_ylabel(ylabel)
    ax.set_title(f"FloodAI simulated {ylabel}")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / filename, dpi=180)
    plt.close(fig)


def plot_priority_latency(priority_summary):
    data = priority_summary[priority_summary["scenario"] == "moderate"].copy()
    policies = list(data["policy"].unique())
    priorities = list(data["priority"].unique())
    fig, ax = plt.subplots(figsize=(11, 5))
    x = range(len(policies))
    width = 0.18
    for index, priority in enumerate(priorities):
        subset = data[data["priority"] == priority].set_index("policy").reindex(policies)
        positions = [value + (index - (len(priorities) - 1) / 2) * width for value in x]
        ax.bar(
            positions,
            subset["mean_latency_ms_mean"],
            width=width,
            label=priority,
        )
    ax.set_xticks(list(x))
    ax.set_xticklabels(policies, rotation=20)
    ax.set_ylabel("Mean latency (ms)")
    ax.set_title("FloodAI simulated latency by message priority")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "RIS_RESULTS_PRIORITY_LATENCY.png", dpi=180)
    plt.close(fig)



def plot_cnoma_sic(summary):
    data = summary[summary["scenario"] == "moderate"]
    fig, ax = plt.subplots(figsize=(10, 5))
    for policy in data["policy"].unique():
        subset = data[data["policy"] == policy]
        ax.scatter(subset["policy"], subset["cnoma_sic_success_rate_mean"], label=policy)
    ax.set_ylabel("CNOMA SIC success rate")
    ax.set_title("FloodAI simulated CNOMA SIC success")
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "RIS_RESULTS_CNOMA_SIC.png", dpi=180)
    plt.close(fig)

def main():
    summary = pd.read_csv(OUT / "ris_summary.csv")
    plot_metric(summary, "delivery_rate", "Delivery ratio", "RIS_RESULTS.png")
    plot_metric(summary, "mean_aoi_ms", "Mean AoI (ms)", "RIS_RESULTS_AOI.png")
    plot_metric(summary, "mean_latency_ms", "Mean latency (ms)", "RIS_RESULTS_LATENCY.png")
    plot_metric(
        summary, "priority_weighted_delivery",
        "Priority-weighted delivery", "RIS_RESULTS_PRIORITY.png"
    )
    plot_cnoma_sic(summary)
    priority_path = OUT / "ris_priority_summary.csv"
    if priority_path.exists():
        plot_priority_latency(pd.read_csv(priority_path))
    print("Plots generated from outputs/ris_summary.csv")


if __name__ == "__main__":
    main()
