"""Plot existing RIS simulation results without rerunning the simulation."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "data" / "ris_simulation_results.csv"
PNG_PATH = HERE / "outputs" / "RIS_RESULTS.png"


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
    methods = [("agent", "Agent"), ("myopic", "Myopic"), ("fixed", "Fixed")]
    x = np.arange(len(methods))
    labels = [label for _, label in methods]
    delivery_rates = [
        get_value(rows, policy, "delivery_rate") * 100 for policy, _ in methods
    ]
    snr_values = [
        get_value(rows, policy, "mean_delivered_snr_db") for policy, _ in methods
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    fig.subplots_adjust(bottom=0.16, wspace=0.3)
    axes[0].bar(x, delivery_rates)
    axes[1].bar(x, snr_values)
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
    PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PNG_PATH, dpi=220, bbox_inches="tight")
    print(f"Saved graph: {PNG_PATH}")


if __name__ == "__main__":
    main()
