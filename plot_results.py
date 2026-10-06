"""Create plots from the final multi-seed simulation summary CSV."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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

def main():
    summary = pd.read_csv(OUT / "ris_summary.csv")
    plot_metric(summary, "delivery_rate", "Delivery ratio", "RIS_RESULTS.png")
    plot_metric(summary, "mean_aoi_ms", "Mean AoI (ms)", "RIS_RESULTS_AOI.png")
    plot_metric(summary, "mean_latency_ms", "Mean latency (ms)", "RIS_RESULTS_LATENCY.png")
    plot_metric(summary, "priority_weighted_delivery", "Priority-weighted delivery", "RIS_RESULTS_PRIORITY.png")
    print("Plots generated from outputs/ris_summary.csv")

if __name__ == "__main__":
    main()
