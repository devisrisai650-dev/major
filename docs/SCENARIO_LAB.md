# FloodAI dashboard simulation and playback

The regular user dashboard supports two explicitly separated modes.

## Simulation mode

Simulation mode is selected by default for demonstrations. It calls `POST /api/scenarios/generate` to create a deterministic, seeded hourly time series for the selected region. The default scenario is **Rising water**. Users can choose a scenario profile, select a 12/24/48/72-hour timeline, play/pause, scrub to a particular hour, reset, and run the communications simulator for the selected step.

Every generated row is synthetic. The UI labels synthetic rainfall, water level, rise rate, timestamps, and node availability; scenario provenance includes the scenario ID, seed, and the fact that no live or historical observations were used. The optional communications action calls `POST /api/scenarios/run` and is software-only radio/channel simulation.

Synthetic scenarios do not constitute flood assessment. The simulated playback always displays `NOT ASSESSED` for real flood risk. Simulation mode disables the user's flood-email preference in the UI; it must not trigger operational flood warning emails.

## Live mode

Live mode calls the normal `POST /api/dashboard` endpoint and uses the existing live environmental pipeline. It does not use the generated scenario time series. The flood assessment remains gated on fresh quality-controlled gauge observations and verified station-specific official thresholds. Missing or stale data remains `NOT_ASSESSED`; a low indicator is not an all-clear.

## API routes

- `GET /api/scenarios/options`: supported scenarios and control options.
- `POST /api/scenarios/generate`: deterministic synthetic hourly series.
- `POST /api/scenarios/run`: run one selected synthetic time step through the communications simulator.

## Local verification

Run the relevant tests from the project root:

```powershell
python -m pytest tests/test_flood_scenario_generator.py tests/test_scenario_api.py tests/test_dashboard_api.py tests/test_dashboard_simulation_playback.py -q
```
