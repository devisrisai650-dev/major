# Internal synthetic scenario generator

The seeded scenario generator is retained for developer tests and reproducible research. It is **not exposed through the user-facing API** and is not shown in the dashboard.

## User dashboard

The dashboard contains only:
- Region / area selection
- Time-of-day selection
- Flood assessment and data/environmental alerts
- Weather and environmental conditions

The browser calls `POST /api/dashboard`. That response is allow-listed to the fields needed by the dashboard. It does not return synthetic time-series rows, semantic messages, internal channel predictions, RIS-CNOMA attempts, orchestrator decisions, or radio performance metrics. The synthetic scenario router is intentionally not mounted in `api.py`.

## Internal code and tests

- `services/flood_scenario_generator.py` creates seeded synthetic time series for reproducible experiments.
- `services/scenario_api.py` contains developer-facing functions for scenario creation and simulated execution, but its router is not registered on the public FastAPI app.
- `tests/test_flood_scenario_generator.py` and `tests/test_scenario_api.py` exercise the generator and internal functions without exposing their generated rows to the dashboard.

Run the relevant tests locally:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_flood_scenario_generator.py tests/test_scenario_api.py tests/test_dashboard_api.py -q
```

## Time selection and evidence

The selected hour is used to choose an hourly Open-Meteo observation or forecast for the weather card. The UI labels the selected record as an observation or forecast. Flood assessment continues to use current inputs and stays `NOT_ASSESSED` until verified official station-specific thresholds and fresh quality-controlled gauge evidence are configured. A forecast, synthetic scenario, or simulated radio result must never be presented as an operational flood warning or an all-clear.
