# Architecture hardening and deployment gates

## Scope

This change keeps FloodAI a research/simulation prototype. It does not enable official flood warnings, claim field radio reliability, or configure email delivery. The alert dashboard/email behavior is a separate follow-up review.

## Environmental data and synthetic fallback

- Dashboard requests use the configured live sources when the required evidence is available.
- In auto mode, a weather-provider error, unavailable modeled discharge, or unavailable/stale historical gauge replay selects the existing config/demo_flood_scenarios.csv data for a clearly labeled demonstration.
- Synthetic fallback values are simulation inputs only. They must not be labeled as live observations or fresh gauge evidence.
- The official assessment status remains NOT_ASSESSED; complete remains false and dashboard readiness remains false.
- Synthetic gauge values do not set water_level.available or is_recent to true.
- The dashboard response includes scenario_mode=synthetic_fallback and a warning that the values are not a real-world warning.
- Explicit live mode fails closed when the weather provider is unavailable. Explicit demo mode is for demonstration only.
- The alert monitor does not consume the dashboard's synthetic fallback. The official-alert dispatch gate still requires verified official thresholds, fresh QC-passed gauge evidence, an authoritative source, and non-synthetic evidence.

## Channel-model validation

The current Rician K-factor model is trained on a synthetic generator. Its held-out MAE/RMSE/R² measure fit to a random holdout from that same generator; they are not measurements of real radio propagation. The model is explicitly marked field_calibrated=false. A deployment claim requires measured channel samples, documented measurement conditions, a separated train/validation/test protocol, and comparison against a calibrated physical or empirical baseline. Until then, channel prediction, SNR, RIS gain, latency, delivery and AoI remain software-simulation metrics.

## Performance evidence and statistical interpretation

- Use per-seed output rows as independent experimental units; repeated messages/steps within a seed are not independent samples.
- Use paired comparisons when methods share the same scenario and seed.
- Report point estimates and 95% confidence intervals from generated outputs.
- If a paired 95% confidence interval includes zero, state “no benefit established.”
- A confidence interval excluding zero supports only a simulated difference under the tested scenarios; it does not establish field performance or general reliability.
- The access-mode evaluator writes per-seed rows to outputs/access_mode_ablation.csv and seed-cluster intervals/paired comparisons to outputs/access_mode_ablation_summary.csv.
- The orchestrator paired summary remains outputs/orchestrator_comparison_paired_summary.csv. Do not claim orchestration improves reliability without evidence from that generated summary.
- Record the run's commit SHA, seeds, episodes, steps, model artifacts, and output manifest. Re-run and inspect artifacts for the current commit before using any result in a paper.

## Security and operational readiness checklist

Before any externally reachable deployment:

- [ ] Use HTTPS at the deployment edge and secure session-cookie settings appropriate to that environment.
- [ ] Keep admin credentials, SMTP credentials, and signing/session secrets in environment-managed secrets; never commit them or print them in logs.
- [ ] Verify authentication, authorization, session expiry/revocation, password handling, and rate limiting for login/registration/admin endpoints.
- [ ] Restrict CORS to the exact deployed dashboard origin; do not enable wildcard credentialed CORS.
- [ ] Set request timeouts and explicit fallback/error behavior for every external provider; do not turn missing data into zero-valued observations.
- [ ] Keep synthetic data and historical replay visibly labeled and excluded from official-alert eligibility.
- [ ] Monitor request counts/latency, provider failures, fallback activations, stale-gauge counts, authentication failures, and alert-dispatch audit outcomes.
- [ ] Define retention, access controls, backups, dependency update policy, vulnerability scanning, and incident response.
- [ ] Test external provider outages, malformed responses, stale/duplicate/out-of-range gauge records, and recovery after an outage.
- [ ] Keep email notifications disabled unless explicitly configured and separately tested. Dashboard work in this change does not alter email preferences or SMTP behavior.
- [ ] Obtain verified station-specific thresholds and a validated live gauge provider before changing the NOT_ASSESSED gate.
- [ ] Validate the channel model against measured radio data and complete hardware/field testing before making real-link claims.

## Current non-goals

No production deployment, official warning, real radio-link guarantee, live gauge certification, or email delivery guarantee is established by passing CI. A successful automated run only establishes that the configured checks and simulations completed successfully for that commit.
