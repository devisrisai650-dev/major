# Changelog and Open Items

## Admin dashboard, email alerts and user dashboard wording

- User dashboard: the rainfall status now shows `LOW RAINFALL INDICATOR` when live rainfall is low, and `INDICATORS UNAVAILABLE` when no live indicator can be read, instead of the previous `DATA INCOMPLETE` badge. Both messages still state that this is not an official warning or an all-clear. The backend `NOT_ASSESSED` safety gate is unchanged.
- Email: environmental indicator emails no longer contain literal `\n` text; they are sent once per region, level and calendar day instead of every ~15 minutes; a delivery that fails for every recipient is audited (`alert_email_failed`) and retried on the next monitor cycle instead of being suppressed; verification-email and SMTP-test failures now report the underlying reason.
- Admin dashboard: added the alert monitor's last run per region, alert dispatch history, and a simulation runner (learning disabled) using the existing `/api/admin/pipeline` endpoint. New endpoint: `GET /api/admin/alerts/history`; `GET /api/admin/alerts/status` now includes `monitor_last_run`.
- Tests: refreshed the stale `test_dashboard_api.py` and added `test_admin_api.py` plus alert-retry/dedupe regression tests.

## Phase 0–6 completion audit

- Preserved conservative flood safety: assessment remains NOT_ASSESSED without verified official station-specific thresholds and fresh QC-passed gauge evidence.
- Preserved historical gauge replay labeling and explicit live-provider boundary.
- Added cross-platform advisory locking around Q-table load/save while retaining atomic replacement.
- Fixed partial-observation action-mask consistency so the mask is derived from the exact observation supplied to the policy.
- Added explicit learned-value-weight ablation support for 0.0 versus the default 0.05.
- Added priority-wise latency/AoI evaluation output and a priority-latency plot.
- Added reproducible experiment metadata with training/evaluation seeds, observation scenarios, policies and output manifest.
- Made the synthetic Rician K-factor model path configurable with FLOODAI_CHANNEL_MODEL_PATH.
- Added named synthetic channel-generation scenarios: baseline, urban_flood and coastal_flood.
- Added predictor tests for missing measurements, invalid values and unavailable model paths.
- Added API regression coverage proving learning is opt-in and disabled runs do not rewrite the saved policy.
- Removed the legacy non-implemented radio result artifact so the repository no longer presents results for an unimplemented radio access method.
- Kept channel, RIS, SNR, latency, packet delivery and AoI explicitly simulation-only.

## Validation requirements before merging

1. Run pytest -q and ruff check .
2. Regenerate the v2 synthetic channel model and confirm clipped target fraction remains 0.
3. Run the multi-seed RIS evaluation with at least 10 independent training seeds and disjoint evaluation seeds.
4. Run plot_results.py and inspect the delivery, AoI, latency, priority and priority-latency plots.
5. Confirm outputs/ris_summary.csv, outputs/ris_priority_summary.csv, outputs/ris_weight_ablation.csv and outputs/experiment_metadata.json are internally consistent.
6. Confirm the application still reports NOT_ASSESSED when thresholds are unverified or gauge data is stale.
7. Do not interpret synthetic channel predictions as field-calibrated measurements or radio-link availability.

## Remaining real-world research items

1. Obtain authoritative station-specific warning thresholds before enabling operational flood assessment.
2. Add a validated live gauge provider with authentication, outage handling and QC.
3. Replace synthetic channel training data with measured/calibrated data.
4. Validate the virtual channel model against hardware measurements.
5. Complete security and operational validation before deployment.
