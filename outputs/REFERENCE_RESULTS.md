# Reference simulation result

This reference run was executed from the consolidated software simulator, not from a deployed radio or flood-warning system.

Configuration:
- training seeds: 1000–1009 (10 independent seeds)
- evaluation seed: 11000 (disjoint from training)
- training episodes per seed: 25
- episode length: 20 steps
- learned-value weight: 0.05
- observation model: partial/noisy/delayed except the oracle
- 720 episode rows across 6 policies, 3 observation-severity scenarios and 4 priorities
- bootstrap confidence intervals: 500 resamples in this compact reference run

Moderate-observation scenario:

| Policy | Delivery mean | 95% CI | Mean AoI (ms) |
|---|---:|---:|---:|
| Agent | 0.9263 | 0.9168–0.9350 | 26.64 |
| Random | 0.8500 | 0.8500–0.8500 | 56.08 |
| Fixed | 0.7000 | 0.7000–0.7000 | 69.18 |
| Best-fixed | 0.8500 | 0.8500–0.8500 | 45.79 |
| Myopic noisy | 0.9250 | 0.9175–0.9325 | 26.93 |
| Oracle | 0.9500 | 0.9500–0.9500 | 21.78 |

Interpretation:
- The agent mean delivery ratio is slightly above the noisy-myopic baseline in this reference run (0.9263 vs 0.9250), but the intervals overlap; therefore this run does **not** establish a statistically significant advantage.
- The oracle is an upper/reference case with perfect current information and is not a deployable measurement.
- All SNR, latency, delivery, RIS and AoI values are simulation outputs.
- These numbers are reference simulation results; rerunning the experiment may produce different values because the simulator is stochastic.
