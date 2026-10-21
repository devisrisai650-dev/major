# FloodAI Validation Report

**Validated commit:** `9001b73850eb46a273694c6d70eec2f03650f989` (PR #26 head; merged into `main` as `65917bfa6b05c4ba2285b2ed53f3b3341b20107b`)  
**Research workflow:** [Run 39617612853](https://github.com/devisrisai650-dev/major/actions/runs/39617612853) — success  
**Main CI after merge:** [Run 39619024606](https://github.com/devisrisai650-dev/major/actions/runs/39619024606) — success  
**Research artifact:** `floodai-ris-cnoma-evaluation-39617612853`  
**Interpretation:** all reported radio/channel/RIS/SNR/latency/delivery/AoI metrics are software simulations, not field measurements.

## Validation checklist

| Check | Result | Evidence / limitation |
|---|---|---|
| Pytest | PASS | GitHub CI completed successfully on the merged main commit. |
| Ruff | PASS | GitHub CI completed successfully on the merged main commit. |
| Synthetic channel model | PASS | 10,000 synthetic samples; MAE 0.2578 dB; RMSE 0.3229 dB; R² 0.9942; clipped-target fraction 0.0. This is a random holdout from the same synthetic generator, not field calibration. |
| RIS evaluation | PASS | 10 training seeds (1000–1009), 5 disjoint evaluation seeds (11000–11004), 250 training episodes per seed, 40 steps per episode. |
| Access-mode ablation | PASS | 10 seeds, 200 steps; seed-cluster 95% CIs and paired comparisons generated. |
| Orchestrator comparison | PASS | Paired summary generated for 100 episodes per scenario. |
| Plots and output files | PASS | RIS delivery, AoI, latency, priority, priority-latency, CNOMA/SIC and training plots included in the research artifact. |
| Official flood assessment gate | SAFE / NOT ASSESSED | Synthetic fallback does not count as fresh gauge evidence; no verified station-specific thresholds/live QC gauge are established. |
| Field channel validation | OPEN | Requires measured radio data and an independent validation protocol. |
| Production security / deployment review | OPEN | Checklist is documented in `docs/ARCHITECTURE_HARDENING.md`; this is not a completed security audit. |

## Synthetic channel model

From `models/xgboost_rician_model_v2_metrics.json`:

- Samples: 10,000 synthetic records.
- MAE: 0.2578116 dB.
- RMSE: 0.3229328 dB.
- R²: 0.9942132.
- Clipped target fraction: 0.0; target clipping was not applied.
- Validation protocol: 80/20 random holdout from the same synthetic generator.
- `field_calibrated`: false.

These metrics show fit to the synthetic generator only. They do not validate radio propagation in real flood conditions.

## RIS agent evaluation

The RIS summary uses 5 disjoint evaluation seeds and cluster-bootstrap 95% confidence intervals. Selected means and intervals from `outputs/ris_summary.csv`:

| Scenario | Policy | Delivery rate (mean) | 95% CI | Mean latency (ms) | Mean AoI (ms) |
|---|---|---:|---:|---:|---:|
| Light | Agent | 0.8773 | 0.8526–0.9072 | 23.81 | 28.10 |
| Light | Myopic noisy | 0.8663 | 0.8300–0.9050 | 22.19 | 27.24 |
| Light | Oracle | 0.9825 | 0.9525–1.0000 | 22.44 | 23.37 |
| Moderate | Agent | 0.4899 | 0.4281–0.5524 | 38.32 | 90.35 |
| Moderate | Myopic noisy | 0.4888 | 0.4388–0.5400 | 36.97 | 84.14 |
| Moderate | Oracle | 0.8475 | 0.8175–0.8825 | 24.36 | 30.88 |
| Severe | Agent | 0.0616 | 0.0341–0.0856 | 84.90 | 1230.51 |
| Severe | Myopic noisy | 0.0600 | 0.0313–0.0850 | 86.18 | 1237.35 |
| Severe | Oracle | 0.4375 | 0.3875–0.5150 | 26.59 | 148.89 |

These are scenario-specific simulator results. Agent and myopic-noisy point estimates are close in the moderate and severe cases; do not claim a general DRL benefit without a directly paired interval for that comparison. The oracle uses perfect current information and is only a reference upper case.

## Orchestrator paired comparison

From `outputs/orchestrator_comparison_paired_summary.csv`:

| Scenario | DRL delivery | Orchestrated delivery | Paired delivery difference (orchestrated − DRL) | 95% CI |
|---|---:|---:|---:|---:|
| Light | 1.00 | 1.00 | 0.00 | 0.00–0.00 |
| Moderate | 1.00 | 1.00 | 0.00 | 0.00–0.00 |
| Severe | 1.00 | 1.00 | 0.00 | 0.00–0.00 |
| Outage stress | 0.74 | 0.73 | −0.01 | −0.03–0.00 |

**Conclusion: no delivery benefit established.** The outage-stress point estimate is 1 percentage point lower for orchestration, and the interval reaches zero. Mean latency was 0.289 ms higher in outage stress, with a 95% interval of approximately −0.002 to 0.625 ms; this does not establish a latency improvement. All results are simulated.

## Access-mode ablation

From `outputs/access_mode_ablation_summary.csv`, with 10 paired seeds per scenario:

| Scenario | OMA, no RIS | CNOMA, no RIS | RIS-CNOMA oracle |
|---|---:|---:|---:|
| Light | 0.9940 (0.9915–0.9970) | 0.6090 (0.5750–0.6465) | 0.9575 (0.9450–0.9700) |
| Moderate | 0.9705 (0.9600–0.9795) | 0.4315 (0.4065–0.4565) | 0.8190 (0.7970–0.8415) |
| Severe | 0.7655 (0.7360–0.7940) | 0.0985 (0.0815–0.1175) | 0.3020 (0.2570–0.3425) |

Values are mean simulated delivery rates (seed-cluster 95% CI). The paired OMA-minus-RIS-CNOMA-oracle intervals excluded zero in these three scenarios, favoring OMA in this specific simulator and setup; this does not prove that OMA is generally superior in real networks. The oracle's perfect-current-CSI selection makes it an idealized comparison, not a deployable policy.

## Safety, fallback and operational status

- The dashboard may display a labeled synthetic fallback if configured live weather/discharge evidence or a fresh gauge replay is unavailable.
- Synthetic fallback is not official gauge evidence. The flood assessment remains `NOT_ASSESSED`; synthetic gauge readings do not become fresh/available observations.
- `GET /api/health/readiness` reports readiness for simulation separately from operational flood-warning readiness.
- No verified station-specific warning thresholds or validated live gauge provider were established by these software tests.
- The Rician K-factor model is not field calibrated.
- No email/SMTP delivery test or production security audit is included in this validation.

## Remaining work

1. Inspect the dashboard in the local environment with the new merged `main` code; verify the synthetic fallback label, `NOT_ASSESSED` status and no false all-clear.
2. Confirm provider outage, stale-gauge and missing-threshold behavior using the existing regression tests.
3. Before any operational warning claim, validate authoritative station-to-region mappings, official station-specific thresholds, fresh quality-controlled gauge evidence, outage handling and an explicit human/agency-approved warning policy.
4. Before radio performance claims, collect measured channel data and evaluate on a genuinely independent test set.
5. Complete the deployment security checklist in `docs/ARCHITECTURE_HARDENING.md`.

**Overall:** automated software validation passed for the merged change and the research workflow produced its expected artifact. FloodAI remains a research/simulation prototype, not an operational flood-warning service.
