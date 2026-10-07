# Architecture

1. `services/weather_service.py` and `services/flood_api.py` provide regional environmental inputs.
2. `services/water_level.py` performs historical CSV replay and quality control.
3. `services/flood_state.py` applies conservative assessment gating.
4. `services/semantic_priority.py` selects information based on application priority and provenance.
5. `semantic_transmission.py` passes the selected message to the virtual communication environment.
6. `channel_simulator.py` generates synthetic time-varying channel conditions.
7. `ris_environment.py` adds noisy/delayed observations and action masks.
8. `ris_agent.py` performs tabular Q-learning.
9. `evaluate_ris_agent.py` performs multi-seed policy comparisons.
10. `api.py` exposes the pipeline to the dashboard.

The communication layer is a software simulation and must not be interpreted as a deployed wireless link.
\n\n## Deployment and observability\n\n11. Docker packages the API and repository runtime into a reproducible container.\n12. Docker Compose runs the API, Prometheus and Grafana locally.\n13. Kubernetes manifests provide replicas, health probes, a ClusterIP service and CPU-based HPA.\n14. FastAPI exposes /metrics using Prometheus counters and histograms.\n15. Grafana dashboards visualize API request rate, pipeline execution rate, p95 API latency and pipeline errors.\n\nThe deployment and monitoring layer is operational infrastructure around the research pipeline; it does not change the simulation-only status of the communication/RIS results.\n