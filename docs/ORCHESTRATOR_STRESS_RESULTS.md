# Orchestrator stress evaluation: reference run

**Evidence:** FloodAI Research Evaluation workflow run `38232397499`, commit `622df0edc34e1985f56b747ae4670c365097f308`, generated on 2026-10-12. Artifact: `floodai-ris-cnoma-evaluation-38232397499`.

This report summarizes the generated `outputs/orchestrator_comparison.csv`. It is a software simulation, not field evidence. There are 100 paired message episodes per scenario (one DRL-only episode and one orchestrated episode per matched seed/message). The 95% intervals below are percentile bootstrap intervals over the 100 paired per-message differences, with 20,000 resamples for this reference analysis.

| Scenario | DRL delivery | Orchestrated delivery | Delivery difference (orchestrated − DRL) | 95% paired-bootstrap CI | Fallback activated | Safe-wait activated |
|---|---:|---:|---:|---:|---:|---:|
| Light | 100% | 100% | 0 pp | [0, 0] pp | 0% | 0% |
| Moderate | 100% | 100% | 0 pp | [0, 0] pp | 0% | 0% |
| Severe | 100% | 100% | 0 pp | [0, 0] pp | 3% | 4% |
| Outage stress | 74% | 73% | −1 pp | [−3, 0] pp | 15% | 34% |

| Scenario | DRL mean attempt latency | Orchestrated mean attempt latency | Difference (orchestrated − DRL) | 95% paired-bootstrap CI |
|---|---:|---:|---:|---:|
| Light | 20.338 ms | 20.338 ms | 0.000 ms | [0.000, 0.000] ms |
| Moderate | 20.901 ms | 20.901 ms | 0.000 ms | [0.000, 0.000] ms |
| Severe | 33.121 ms | 33.241 ms | +0.120 ms | [+0.000, +0.336] ms |
| Outage stress | 52.097 ms | 52.385 ms | +0.289 ms | [+0.006, +0.634] ms |

## Interpretation

- The fallback and safe-wait branches do activate in stress conditions, so those branches are reachable in the simulator.
- In light and moderate conditions, both policies deliver all messages in this run; these scenarios do not show a benefit from orchestration.
- In severe conditions, activation is rare and delivery is unchanged.
- In the outage-stress scenario, orchestration delivered one fewer message out of 100 paired episodes and had higher mean attempt latency. The delivery interval touches zero, so this single run is not evidence of a definitive reliability regression; the latency interval is positive in this bootstrap analysis.
- The correct conclusion is **not** that orchestration improves reliability. The current fallback is a no-RIS CNOMA action choice, not a distinct OMA/direct-link implementation. Further policy design and repeated evaluation are needed before claiming a reliability benefit.

## Reproduction

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe evaluate_orchestrator.py --seeds 5 --messages 20 --steps 40 --output outputs/orchestrator_comparison.csv
```

The updated evaluator also writes a paired summary to `outputs/orchestrator_comparison_paired_summary.csv` by default. Its bootstrap confidence interval is reproducible for the same CSV and uses a fixed seed; it is not a substitute for more independent scenarios or field validation.

## Non-goals and safety boundary

This evaluation does not validate flood-risk thresholds, prove radio-link availability, calibrate the synthetic Rician K-factor predictor, or establish real-world network reliability. Keep flood assessment `NOT_ASSESSED` without the required official thresholds and fresh QC-passed gauge evidence. Historical gauge CSVs remain replay data. No live gauge integration or dashboard changes are made by this evaluation work.
