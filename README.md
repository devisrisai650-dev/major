# FloodAI — RIS-CNOMA Flood Communication and Conservative Flood Monitoring Simulation

FloodAI is a reproducible research prototype that combines regional environmental inputs, conservative flood-assessment gating, semantic message selection, a virtual channel/RIS simulator, and multi-seed evaluation.

## Safety and provenance boundary

- Flood assessment is **NOT_ASSESSED** unless verified official station-specific warning thresholds and fresh QC-passed gauge evidence are available.
- Weather and modeled river discharge are labeled by source and data type.
- CSV gauge data is historical replay, not a live gauge feed.
- Channel, SNR, latency, RIS effects, packet delivery and AoI are **software simulations**.
- The Rician K predictor is trained on synthetic data and is not field calibrated.
- The project does not establish radio-link availability or issue operational flood warnings.

## Architecture

`weather/hydrology/gauge replay -> QC -> conservative assessment -> semantic priority -> XGBoost K prediction -> physics-informed channel -> RIS + CNOMA + SIC -> Q-learning controller -> delivery/AoI -> API/dashboard -> Docker/Kubernetes -> Prometheus/Grafana`

## Reproducible run order

Use the project virtual environment on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe train_channel_model.py --scenario baseline
.\.venv\Scripts\python.exe runtime.py --train-seeds 10 --train-episodes 250 --eval-seeds 5 --eval-episodes-per-seed 1 --steps 40
.\.venv\Scripts\python.exe plot_results.py
.\.venv\Scripts\python.exe main.py --region region_001 --seed 1234
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

The default RIS inference path does not update the Q-table. Learning is opt-in through the `learn` flag.

## Weather provider

Weather data is fetched from Visual Crossing. Set `VISUAL_CROSSING_API_KEY` in the process environment before starting the API or CLI:

```sh
export VISUAL_CROSSING_API_KEY=YOUR_API_KEY
```

In PowerShell, use `$env:VISUAL_CROSSING_API_KEY = "YOUR_API_KEY"` instead.

Docker Compose forwards this variable to the API container. For Kubernetes, create the expected Secret before applying the deployment:

```sh
kubectl -n floodai create secret generic visual-crossing-api \
	--from-literal=api-key="$VISUAL_CROSSING_API_KEY"
```

## Evaluation

The simulator compares:

- RIS-CNOMA Q-learning agent under partial/noisy/delayed observations
- random policy
- fixed-RIS policy (RIS configuration zero; waits if it is infeasible)
- initial-greedy locked-action policy (locks its first greedy action; waits if infeasible)
- myopic policy under noisy/delayed observations
- perfect-CSI oracle reference

The oracle is **not** the proposed system. It is an ideal reference that has perfect current channel information, so it helps quantify the performance gap caused by partial observability.

The evaluation uses at least 10 independent training seeds and disjoint evaluation seeds. Episode-level results are written to `outputs/ris_episode_results.csv`; aggregate means and seed-cluster bootstrap 95% confidence intervals are written to `outputs/ris_summary.csv`. Confidence intervals resample independent evaluation-seed clusters rather than treating repeated training-seed results on the same evaluation seed as independent. Priority-wise latency/AoI results are written to `outputs/ris_priority_summary.csv`, the learned-value 0.0 versus default-weight ablation is written to `outputs/ris_weight_ablation.csv`, per-training-seed episode rewards and epsilon values are written to `outputs/ris_training_curves.csv`, and run metadata is written to `outputs/experiment_metadata.json`. The training schedule decays epsilon to its configured floor by 80% of the requested episode count; `plot_results.py` generates reward and epsilon plots from the saved training CSV.

Metrics include delivery ratio, critical-message delivery, priority-weighted delivered messages per step, mean latency and SNR across attempted transmissions (including failed deliveries), Age of Information (AoI), CNOMA SIC success across attempted transmissions, RIS reconfigurations and reward. Because the evaluation currently uses only five independent evaluation seeds by default, confidence intervals may be wide and should be interpreted cautiously.

Results must be interpreted as simulated results. Whether the learned policy beats a baseline is determined from the generated CSVs, not from manually entered values.

## Channel model

`train_channel_model.py` generates a synthetic dataset and trains `models/xgboost_rician_model_v2.json`. The target is Rician K-factor in dB without a target floor. The script records the clipped-target fraction and documents the synthetic condition bands. Named generation scenarios are `baseline`, `urban_flood`, and `coastal_flood`; select one with `--scenario`.

If the required measured channel features are unavailable to the live pipeline, the predictor returns an explicit unavailable result instead of inventing inputs. The model path can be overridden with the `FLOODAI_CHANNEL_MODEL_PATH` environment variable.

## RIS-CNOMA communication model

The communication subsystem includes a two-user software CNOMA model. Each per-user input is post-noise SNR in dB from the channel simulator; the model uses normalized noise (1), so it does not add a second noise floor. Rain attenuation is applied once upstream when SNR is formed. The three power profiles are (weak-user share, strong-user share); shares are mapped to whichever logical user has the weaker/stronger channel, rather than fixed to user index. SIC succeeds when the strong-channel user can decode the weak user's stream at the configured SINR threshold. Packet delivery uses one threshold-outage rule (the critical stream must decode); the separate sigmoid channel score is retained only as a latency proxy, not a second delivery lottery. The feasibility tensor is named `cnoma_delivery_feasibility` because it is a deterministic threshold result, not a calibrated probability. This remains a software abstraction for reproducible research, not a modem implementation.

The channel simulator includes correlated fading, Rician components, rain attenuation, a Doppler term driven by simulated flow velocity, and a virtual RIS phase codebook. Environmental values perturb the simulation; they are not measurements of the radio channel.

The API/dashboard exposes a separate **communication alert** with NORMAL, DEGRADED, CRITICAL or OUTAGE states. This must never be interpreted as a flood warning. Flood status remains conservatively gated by the existing official-threshold and QC rules.

### New research scenarios

- light, moderate and severe environmental/channel conditions
- rain attenuation
- Doppler variation
- CNOMA SIC success/failure
- partial observation versus perfect-CSI oracle


## Cloud-native deployment

The deployment layer packages the existing software-only pipeline with Docker and Kubernetes. FastAPI remains the application boundary; XGBoost and Q-learning remain the existing research components. Prometheus collects API/pipeline metrics and Grafana provides operational dashboards. Kubernetes provides health checks, replica management and CPU-based autoscaling. These technologies do not make the simulated wireless channel a physical radio system.

### Docker Compose

```powershell
docker compose up --build
```

- Dashboard/API: http://localhost:8000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

### Kubernetes

See `k8s/README.md`. With Docker Desktop Kubernetes enabled:

```powershell
docker build -t floodai-api:latest .
kubectl apply -f k8s/
kubectl -n floodai get pods
```

The HPA requires a Kubernetes metrics server. Production deployment also needs registry-backed images, TLS, authentication, secrets and persistent monitoring storage.

## API

Start:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

Then open the local dashboard at the server root. `POST /api/run` accepts a region, communication-attempt count, seed and optional learning flag.

## Limitations and future real-world work

A real deployment would require authoritative local warning thresholds, validated gauge ingestion, sensor QC and outage handling, field-calibrated channel data, measured radio hardware, regulatory/frequency planning, security, and operational validation with local disaster-management authorities. None of those are claimed by this software-only prototype.


## Local launch

On Windows with Docker Desktop running, use `run_floodai.ps1` to start the Compose services, wait for the API health check, and open the local dashboard at `http://localhost:8000/`. The launcher does not replace the scientific provenance boundaries: environmental assessment remains conservative and the communication/RIS layer remains software simulation.

## Validation checklist

Before treating a run as a reproducible project result:

1. Run `pytest -q` and `ruff check .`.
2. Train the synthetic channel model with an explicit named scenario.
3. Run the multi-seed RIS evaluation with disjoint training and evaluation seeds.
4. Inspect `outputs/ris_summary.csv`, `outputs/ris_priority_summary.csv`, `outputs/ris_weight_ablation.csv`, `outputs/ris_training_curves.csv`, and `outputs/experiment_metadata.json`.
5. Generate plots only from the CSV outputs.
6. Keep generated Q-tables, plots, and experiment CSVs separate from source/configuration commits unless a specific experiment artifact needs archival.
7. Never describe simulated channel, RIS, delivery, latency, AoI, or synthetic-model results as field measurements.
