# Changelog and Open Items

## Quality consolidation

- Added partial, noisy and delayed virtual channel observations plus a perfect-CSI oracle.
- Made the learned-value weight configurable.
- Added random, fixed, best-fixed, noisy-myopic and oracle baselines.
- Added multi-seed episode CSVs and bootstrap 95% confidence intervals.
- Added Age of Information and priority-weighted delivery.
- Added conservative flood-assessment threshold provenance gating.
- Added synthetic Rician K-factor model v2 in dB without a target floor.
- Added API provenance and controlled errors.
- Added tests for semantic priority, QC, inference immutability, persistence, observation modes and API errors.
- Kept channel, RIS, SNR, latency and packet outcomes explicitly simulation-only.

## Open items

1. Obtain authoritative station-specific warning thresholds before enabling operational flood assessment.
2. Add a validated live gauge provider with authentication, outage handling and QC.
3. Replace synthetic channel training data with measured/calibrated data.
4. Validate the virtual channel model against hardware measurements.
5. Complete security and operational validation before deployment.
