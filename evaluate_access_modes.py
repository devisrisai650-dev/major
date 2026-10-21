"""Controlled PHY ablation: OMA vs CNOMA vs RIS-CNOMA.

This experiment uses the same synthetic channel seed and environmental scenario
for all modes. It is an oracle-style physical-layer ablation, not a DRL policy
comparison or a field-performance estimate.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from channel_simulator import ChannelSimulator
from cnoma import CNOMASimulator
from evaluate_ris_agent import SCENARIOS


def run_ablation(seeds: list[int], steps: int, output: Path) -> list[dict]:
    if not seeds or steps < 1:
        raise ValueError("at least one seed and one step are required")

    rows: list[dict] = []
    noma = CNOMASimulator()
    for scenario_name, scenario in SCENARIOS.items():
        for seed in seeds:
            channel = ChannelSimulator(seed=seed)
            channel.set_environment(
                rain_mm=scenario["rain_mm"],
                flow_velocity_mps=scenario["flow_velocity_mps"],
                node_outage_probability=scenario["node_outage_probability"],
                node_recovery_probability=scenario["node_recovery_probability"],
            )
            measurements = channel.reset()
            totals = {
                "oma_no_ris": {"delivered": 0, "snr": []},
                "cnoma_no_ris": {"delivered": 0, "snr": []},
                "ris_cnoma_oracle": {"delivered": 0, "snr": []},
            }

            for _ in range(steps):
                snr = measurements["snr_db"]
                available = measurements["available"]

                # OMA: one user per resource, no multi-user interference.
                oma_candidates = [
                    (float(snr[c, 0]), c)
                    for c in range(channel.n_channels)
                    if available[c, 0]
                ]
                if oma_candidates:
                    best_snr, _ = max(oma_candidates)
                    totals["oma_no_ris"]["snr"].append(best_snr)
                    totals["oma_no_ris"]["delivered"] += int(
                        best_snr >= noma.sinr_threshold_db
                    )

                # CNOMA without RIS: hold RIS configuration at zero and choose
                # the best channel pair/power profile with perfect current CSI.
                best_result = None
                best_snr = None
                for c in range(channel.n_channels):
                    second = (c + 1) % channel.n_channels
                    if not (available[c, 0] and available[second, 0]):
                        continue
                    for power in range(len(noma.POWER_PROFILES)):
                        result = noma.evaluate(
                            float(snr[c, 0]), float(snr[second, 0]), power,
                            critical_user=1,
                        )
                        candidate = (bool(result.user1_decoded), result.user1_sinr_db)
                        if best_result is None or candidate > best_result:
                            best_result = candidate
                            best_snr = float(snr[c, 0])
                if best_result is not None:
                    totals["cnoma_no_ris"]["snr"].append(best_snr)
                    totals["cnoma_no_ris"]["delivered"] += int(best_result[0])

                # RIS-CNOMA: same PHY rule, but search the RIS codebook too.
                best_result = None
                best_snr = None
                for c in range(channel.n_channels):
                    second = (c + 1) % channel.n_channels
                    for ris in range(channel.n_ris_configs):
                        if not (available[c, ris] and available[second, ris]):
                            continue
                        for power in range(len(noma.POWER_PROFILES)):
                            result = noma.evaluate(
                                float(snr[c, ris]), float(snr[second, ris]), power,
                                critical_user=1,
                            )
                            candidate = (bool(result.user1_decoded), result.user1_sinr_db)
                            if best_result is None or candidate > best_result:
                                best_result = candidate
                                best_snr = float(snr[c, ris])
                if best_result is not None:
                    totals["ris_cnoma_oracle"]["snr"].append(best_snr)
                    totals["ris_cnoma_oracle"]["delivered"] += int(best_result[0])

                channel.advance()
                measurements = channel.measure()

            for mode, values in totals.items():
                attempted = len(values["snr"])
                rows.append({
                    "scenario": scenario_name,
                    "seed": seed,
                    "mode": mode,
                    "steps": steps,
                    "attempted_steps": attempted,
                    "delivery_rate": values["delivered"] / steps,
                    "mean_selected_snr_db": (
                        float(np.mean(values["snr"])) if attempted else None
                    ),
                    "node_outage_probability": scenario["node_outage_probability"],
                    "simulation_only": True,
                    "selection": "perfect_current_CSI_oracle",
                })

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _bootstrap_mean_ci(values, rng, samples=10000):
    """Percentile CI over independent seed-level observations."""
    values = np.asarray([value for value in values if value is not None], dtype=float)
    if values.size == 0:
        return None, None
    draws = rng.choice(values, size=(samples, values.size), replace=True).mean(axis=1)
    low, high = np.quantile(draws, [0.025, 0.975])
    return float(low), float(high)


def summarize_ablation(rows: list[dict], output: Path, seed: int = 2026) -> list[dict]:
    """Write seed-cluster CIs and paired seed-level delivery comparisons."""
    rng = np.random.default_rng(seed)
    grouped = {}
    for row in rows:
        grouped.setdefault((row["scenario"], row["mode"]), []).append(row)

    summary = []
    for (scenario, mode), group in sorted(grouped.items()):
        delivery = [float(row["delivery_rate"]) for row in group]
        snr = [row["mean_selected_snr_db"] for row in group]
        delivery_low, delivery_high = _bootstrap_mean_ci(delivery, rng)
        snr_low, snr_high = _bootstrap_mean_ci(snr, rng)
        summary.append({
            "record_type": "mode_summary",
            "scenario": scenario,
            "mode": mode,
            "comparison": "",
            "seed_count": len(group),
            "mean_delivery_rate": float(np.mean(delivery)),
            "delivery_rate_ci_low": delivery_low,
            "delivery_rate_ci_high": delivery_high,
            "mean_selected_snr_db": float(np.mean([v for v in snr if v is not None])) if any(v is not None for v in snr) else None,
            "snr_ci_low": snr_low,
            "snr_ci_high": snr_high,
            "mean_paired_delivery_difference": None,
            "paired_ci_low": None,
            "paired_ci_high": None,
            "interpretation": "Seed-cluster bootstrap interval; software simulation only.",
            "simulation_only": True,
        })

    modes = ("oma_no_ris", "cnoma_no_ris", "ris_cnoma_oracle")
    for scenario in sorted({row["scenario"] for row in rows}):
        by_mode = {
            mode: {int(row["seed"]): row for row in rows
                   if row["scenario"] == scenario and row["mode"] == mode}
            for mode in modes
        }
        for index, mode_a in enumerate(modes):
            for mode_b in modes[index + 1:]:
                common_seeds = sorted(set(by_mode[mode_a]) & set(by_mode[mode_b]))
                if not common_seeds:
                    continue
                differences = np.asarray([
                    float(by_mode[mode_a][seed]["delivery_rate"])
                    - float(by_mode[mode_b][seed]["delivery_rate"])
                    for seed in common_seeds
                ])
                low, high = _bootstrap_mean_ci(differences, rng)
                mean_difference = float(np.mean(differences))
                if low <= 0.0 <= high:
                    interpretation = "No benefit established: paired 95% CI includes zero; simulation only."
                else:
                    interpretation = "Paired 95% CI excludes zero; simulation-only difference, not field evidence."
                summary.append({
                    "record_type": "paired_comparison",
                    "scenario": scenario,
                    "mode": "",
                    "comparison": f"{mode_a} minus {mode_b}",
                    "seed_count": len(common_seeds),
                    "mean_delivery_rate": None,
                    "delivery_rate_ci_low": None,
                    "delivery_rate_ci_high": None,
                    "mean_selected_snr_db": None,
                    "snr_ci_low": None,
                    "snr_ci_high": None,
                    "mean_paired_delivery_difference": mean_difference,
                    "paired_ci_low": low,
                    "paired_ci_high": high,
                    "interpretation": interpretation,
                    "simulation_only": True,
                })

    summary_path = output.with_name(f"{output.stem}_summary.csv")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    print(f"Wrote seed-level confidence intervals and paired comparisons to {summary_path}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--seed", type=int, default=30000)
    parser.add_argument("--output", default="outputs/access_mode_ablation.csv")
    args = parser.parse_args()
    if args.seeds < 1 or args.steps < 1:
        parser.error("--seeds and --steps must be positive")

    output = Path(args.output)
    rows = run_ablation(
        [args.seed + index for index in range(args.seeds)],
        args.steps,
        output,
    )
    summarize_ablation(rows, output)
    print(f"Wrote {len(rows)} software-only PHY-ablation rows to {output}")
    for scenario in SCENARIOS:
        for mode in ("oma_no_ris", "cnoma_no_ris", "ris_cnoma_oracle"):
            subset = [
                row["delivery_rate"] for row in rows
                if row["scenario"] == scenario and row["mode"] == mode
            ]
            print(f"{scenario:>8} {mode:>18}: delivery={np.mean(subset):.3f}")


if __name__ == "__main__":
    main()
