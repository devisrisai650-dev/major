"""Create a single PNG with two RIS simulation result graphs.

Run from this directory:
    python plot_ris_cnoma_flood_results.py

Requires matplotlib. Reads the existing CSV; it does not rerun the simulation.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "data" / "ris_simulation_results.csv"
PNG_PATH = HERE / "RIS_CNOMA_FLOOD_RESULTS.png"

METHODS = [
    ("agent", "Agent", "#159D8C"),
    ("myopic", "Myopic", "#4C78A8"),
    ("fixed", "Fixed", "#9299A2"),
]


def read_rows() -> list[dict[str, str]]:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Results CSV not found: {CSV_PATH}")
    with CSV_PATH.open("r", newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def get_value(rows, policy: str, field: str) -> float:
    for row in rows:
        if row["policy"] == policy:
            return float(row[field])
    raise KeyError(f"No row for policy={policy!r}")


def main() -> None:
    rows = read_rows()
    x = np.arange(len(METHODS))
    labels = [label for _, label, _ in METHODS]
    delivery_rates = [get_value(rows, policy, "delivery_rate") * 100 for policy, _, _ in METHODS]
    snr_values = [get_value(rows, policy, "mean_delivered_snr_db") for policy, _, _ in METHODS]
    colors = [color for _, _, color in METHODS]
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    fig.subplots_adjust(bottom=0.16, wspace=0.3)

    axes[0].bar(x, delivery_rates, color=colors)
    axes[1].bar(x, snr_values, color=colors)

    axes[0].set_title("Packet delivery rate", fontweight="bold")
    axes[0].set_ylabel("Delivery rate (%)")
    axes[0].set_ylim(0, 100)

    axes[1].set_title("Delivered signal quality", fontweight="bold")
    axes[1].set_ylabel("Mean delivered SNR (dB)")

    for ax in axes:
        ax.set_xticks(x, labels)
        ax.set_xlabel("Policy")
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)

    fig.savefig(PNG_PATH, dpi=220, bbox_inches="tight", facecolor="white")
    print(f"Saved graph: {PNG_PATH}")


if __name__ == "__main__":
    main()