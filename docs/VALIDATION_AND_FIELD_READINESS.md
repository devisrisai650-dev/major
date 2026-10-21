# FloodAI validation and real-world readiness gates

## Purpose

This checklist separates reproducible software-simulation evidence from evidence required for operational flood-warning use. A passing CI run is not a field-validation result.

## Automated software/research validation

The GitHub Actions CI workflow must pass:
- dependency installation on the supported Python version
- the full pytest suite
- Ruff lint checks

The Research Evaluation workflow runs:
- synthetic Rician K-factor model training
- multi-seed RIS-CNOMA evaluation with separate training and evaluation seeds
- paired DRL-only versus rule-based orchestrator evaluation
- controlled OMA/CNOMA/RIS-CNOMA access-mode ablation
- plot generation and artifact upload

Use the uploaded CSV/JSON artifacts as the source of numerical results. Do not manually enter metrics into the paper. Record the workflow run URL, commit SHA, configuration, seeds, and artifact name alongside any reported result. Treat a missing artifact or failed workflow as an incomplete validation run.

## Interpretation requirements

- Synthetic channel samples are not field measurements.
- Channel prediction performance is not validated for operational use until evaluated against independently collected, measured channel labels.
- RIS/CNOMA/DRL delivery, latency, AoI, SIC, and outage results are software-simulation results.
- Compare policies on matched seeds/scenarios; report uncertainty intervals and all baseline definitions.
- Do not claim the orchestrator improves reliability unless repeated paired evaluation supports that conclusion. The documented reference run showed no delivery improvement and a small delivery decrease under outage stress.
- An oracle with perfect current CSI is an upper-bound reference, not an implementable baseline.

## Operational flood-warning acceptance gates

FloodAI must remain `NOT_ASSESSED` and must not send an official warning unless all required evidence gates are satisfied by the runtime assessment:
1. An authoritative gauge/source is identified for the configured station and region.
2. Station-specific official warning thresholds are documented, reviewed, and configured with units and provenance.
3. Gauge observations are fresh under a documented station-specific freshness policy and pass quality-control checks.
4. The assessment is complete and carries explicit evidence flags for authoritative source, verified thresholds, and fresh QC-passed gauge evidence.
5. The warning event has a stable identifier, audit trail, and tested delivery/retry behavior.
6. Tests cover missing, stale, malformed, out-of-range, and contradictory inputs and prove they cannot produce an official warning.
7. A domain owner/disaster-management authority reviews the thresholds, source contracts, and operational procedure before any live use.

Weather APIs, modeled discharge, historical CSV replay, and synthetic scenarios must not be represented as live official gauge evidence. If any gate is missing, show `NOT_ASSESSED`; do not describe it as an all-clear.

## Field and deployment work still required

These items cannot be completed or truthfully validated by GitHub CI alone:
- obtain authorized, station-specific official thresholds and current QC-qualified gauge data
- document source provenance, update cadence, outage behavior, units, and quality flags
- obtain measured radio/channel data and validate the channel model against held-out field measurements
- test the software against real hardware/radio equipment if physical RIS/CNOMA performance is claimed
- conduct end-to-end field trials with qualified operators and a fail-safe operational procedure
- before production deployment: HTTPS/TLS, managed secrets, durable database/backup, monitoring/retention, incident response, access review, and disaster-recovery tests

## Release decision

A successful CI and research workflow means the checked code passed those automated checks and the artifacts were generated. It does **not** mean FloodAI is approved for real-world flood warnings. Operational use remains blocked until the field and authority gates above are evidenced and reviewed.
