# FloodAI Scenario Lab

The Scenario Lab is a **synthetic demonstration mode** alongside (not a replacement for) the existing live-weather / historical-gauge replay pipeline.

## Start the lab

Start the API as usual:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
```

Open the dashboard at `http://127.0.0.1:8000/`, scroll to **FloodAI Scenario Lab**, and choose a configured region (Kakinada, Vijayawada, or Machilipatnam), profile, rainfall input, water-level rise input, communication condition, start time, duration, playback speed, and random seed.

The requested demonstration defaults are severe flood, 80 mm/h illustrative rainfall, 0.25 m/h illustrative water-level rise, partial communication outage, normal playback, and seed 2026. You can change the region and start time for another presentation. Duration is expressed as hourly samples; allowed values are 2–168 hours. Use the same configuration and seed to reproduce the same scenario ID and time series.

## API

- `GET /api/scenarios/options`: regions and supported selections.
- `POST /api/scenarios/generate`: creates a seeded time series without invoking live services.
- `POST /api/scenarios/run`: runs one selected synthetic sample through the existing simulated semantic-transmission / RIS-CNOMA / orchestrator path.

Example generation request:

```json
{
  "region_id": "region_001",
  "scenario": "severe",
  "rainfall_mm_h": 80,
  "water_level_rise_m_h": 0.25,
  "communication_condition": "partial",
  "playback": "normal",
  "seed": 2026,
  "steps": 24,
  "start_time": "2026-10-12T00:00:00+05:30",
  "initial_water_level_m": 1.0
}
```

The API returns each synthetic hourly sample, scenario configuration, a SHA-256 configuration hash, seed, scenario ID, and source provenance. The selected sample is translated into the existing channel simulator's environmental context. Partial and total outage settings only change the simulated node outage/recovery probabilities; they do not represent a real network.

## Safety boundary

- All generated rainfall, water levels, flow, debris, obstruction and node availability are synthetic.
- Region selection supplies a label/location for the demonstration; it does not fetch region-specific flood observations or establish regional flood risk.
- The generator never calls weather/gauge services and never edits historical records.
- The flood assessment is hard-gated to `NOT_ASSESSED`, with no score. Synthetic scenarios cannot satisfy the official-threshold or fresh quality-controlled gauge requirements.
- Radio behavior and orchestrator decisions remain software simulations. `NOT_ASSESSED` is neither a warning nor an all-clear. Use official local authorities for safety decisions.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_flood_scenario_generator.py tests/test_scenario_api.py -q
```
