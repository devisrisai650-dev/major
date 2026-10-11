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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--seed", type=int, default=30000)
    parser.add_argument("--output", default="outputs/access_mode_ablation.csv")
    args = parser.parse_args()
    if args.seeds < 1 or args.steps < 1:
        parser.error("--seeds and --steps must be positive")

    rows = run_ablation(
        [args.seed + index for index in range(args.seeds)],
        args.steps,
        Path(args.output),
    )
    print(f"Wrote {len(rows)} software-only PHY-ablation rows to {args.output}")
    for scenario in SCENARIOS:
        for mode in ("oma_no_ris", "cnoma_no_ris", "ris_cnoma_oracle"):
            subset = [
                row["delivery_rate"] for row in rows
                if row["scenario"] == scenario and row["mode"] == mode
            ]
            print(f"{scenario:>8} {mode:>18}: delivery={np.mean(subset):.3f}")


if __name__ == "__main__":
    main()
