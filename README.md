# FloodAI — Software-Only Flood Monitoring and Semantic Communication Simulation

FloodAI is a reproducible research prototype that combines regional environmental inputs, conservative flood-assessment gating, semantic message selection, a virtual channel/RIS simulator, and multi-seed evaluation.

## Safety and provenance boundary

- Flood assessment is **NOT_ASSESSED** unless verified official station-specific warning thresholds and fresh QC-passed gauge evidence are available.
- Weather and modeled river discharge are labeled by source and data type.
- CSV gauge data is historical replay, not a live gauge feed.
- Channel, SNR, latency, RIS effects, packet delivery and AoI are **software simulations**.
- The Rician K predictor is trained on synthetic data and is not field calibrated.
- The project does not establish radio-link availability or issue operational flood warnings.

## Architecture

`weather/hydrology/gauge replay -> QC -> conservative assessment -> semantic priority -> virtual channel/RIS -> evaluation -> API/dashboard -> Docker/Kubernetes -> Prometheus/Grafana`

## Reproducible run order

Use the project virtual environment on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe train_channel_model.py
.\.venv\Scripts\python.exe runtime.py --train-seeds 10 --train-episodes 250 --eval-seeds 5 --steps 40
.\.venv\Scripts\python.exe plot_results.py
.\.venv\Scripts\python.exe main.py --region region_001 --seed 1234
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

The default RIS inference path does not update the Q-table. Learning is opt-in through the `learn` flag.

## Evaluation

The simulator compares:

- agent
- random
- fixed
- best-fixed
- myopic under noisy/delayed observations
- perfect-CSI oracle

The evaluation uses at least 10 independent training seeds and disjoint evaluation seeds. Episode-level results are written to `outputs/ris_episode_results.csv`; aggregate means and bootstrap 95% confidence intervals are written to `outputs/ris_summary.csv`. Priority-wise latency/AoI results are written to `outputs/ris_priority_summary.csv`, the learned-value 0.0 versus default-weight ablation is written to `outputs/ris_weight_ablation.csv`, and run metadata is written to `outputs/experiment_metadata.json`.

Metrics include delivery ratio, critical-message delivery, priority-weighted delivery, latency, Age of Information (AoI), SNR, RIS reconfigurations and reward.

Results must be interpreted as simulated results. Whether the learned policy beats a baseline is determined from the generated CSVs, not from manually entered values.

## Channel model

`train_channel_model.py` generates a synthetic dataset and trains `models/xgboost_rician_model_v2.json`. The target is Rician K-factor in dB without a target floor. The script records the clipped-target fraction and documents the synthetic condition bands. Named generation scenarios are `baseline`, `urban_flood`, and `coastal_flood`; select one with `--scenario`.

If the required measured channel features are unavailable to the live pipeline, the predictor returns an explicit unavailable result instead of inventing inputs. The model path can be overridden with the `FLOODAI_CHANNEL_MODEL_PATH` environment variable.

## Cloud-native deployment\n\nThe deployment layer packages the existing software-only pipeline with Docker and Kubernetes. FastAPI remains the application boundary; XGBoost and Q-learning remain the existing research components. Prometheus collects API/pipeline metrics and Grafana provides operational dashboards. Kubernetes provides health checks, replica management and CPU-based autoscaling. These technologies do not make the simulated wireless channel a physical radio system.\n\n### Docker Compose\n\n```powershell\ndocker compose up --build\n```\n\n- Dashboard/API: http://localhost:8000\n- Prometheus: http://localhost:9090\n- Grafana: http://localhost:3000\n\n### Kubernetes\n\nSee `k8s/README.md`. With Docker Desktop Kubernetes enabled:\n\n```powershell\ndocker build -t floodai-api:latest .\nkubectl apply -f k8s/\nkubectl -n floodai get pods\n```\n\nThe HPA requires a Kubernetes metrics server. Production deployment also needs registry-backed images, TLS, authentication, secrets and persistent monitoring storage.\n\n## API

Start:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

Then open the local dashboard at the server root. `POST /api/run` accepts a region, communication-attempt count, seed and optional learning flag.

## Limitations and future real-world work

A real deployment would require authoritative local warning thresholds, validated gauge ingestion, sensor QC and outage handling, field-calibrated channel data, measured radio hardware, regulatory/frequency planning, security, and operational validation with local disaster-management authorities. None of those are claimed by this software-only prototype.
