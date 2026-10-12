"""Reproducible synthetic flood scenarios for the FloodAI demonstration lab.

Synthetic environmental values are for controlled software experiments only. They
must never be interpreted as observations, forecasts, warnings, or an all-clear.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import datetime, timedelta
from typing import Any


SCENARIOS = {"normal", "rising", "severe", "emergency", "recovery"}
COMMUNICATION_CONDITIONS = {"healthy", "partial", "total"}
PLAYBACK_MODES = {"normal", "fast"}


def _bounded(name: str, value: float, low: float, high: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return result


def generate_scenario(
    *,
    region_id: str = "region_001",
    region_name: str = "Kakinada",
    scenario: str = "severe",
    rainfall_mm_h: float = 80.0,
    water_level_rise_m_h: float = 0.25,
    communication_condition: str = "partial",
    playback: str = "normal",
    seed: int = 2026,
    steps: int = 24,
    start_time: str = "2026-10-12T00:00:00+05:30",
    initial_water_level_m: float = 1.0,
) -> dict[str, Any]:
    """Generate a seeded hourly series plus explicit configuration provenance."""
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {sorted(SCENARIOS)}")
    if communication_condition not in COMMUNICATION_CONDITIONS:
        raise ValueError(
            f"communication_condition must be one of {sorted(COMMUNICATION_CONDITIONS)}"
        )
    if playback not in PLAYBACK_MODES:
        raise ValueError(f"playback must be one of {sorted(PLAYBACK_MODES)}")
    rainfall = _bounded("rainfall_mm_h", rainfall_mm_h, 0.0, 300.0)
    rise_rate = _bounded("water_level_rise_m_h", water_level_rise_m_h, 0.0, 1.0)
    initial_level = _bounded("initial_water_level_m", initial_water_level_m, 0.0, 100.0)
    if not isinstance(steps, int) or isinstance(steps, bool) or not 2 <= steps <= 168:
        raise ValueError("steps must be an integer between 2 and 168")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    if not region_id.strip() or not region_name.strip():
        raise ValueError("region_id and region_name must not be empty")
    try:
        start = datetime.fromisoformat(start_time)
    except (TypeError, ValueError) as exc:
        raise ValueError("start_time must be an ISO-8601 timestamp") from exc
    if start.tzinfo is None:
        raise ValueError("start_time must include a timezone offset")

    rng = random.Random(seed)
    rows = []
    scenario_rain_factor = {
        "normal": 0.08, "rising": 0.55, "severe": 1.0,
        "emergency": 1.15, "recovery": 0.35,
    }[scenario]
    scenario_rise_factor = {
        "normal": 0.05, "rising": 0.65, "severe": 1.0,
        "emergency": 1.2, "recovery": 0.25,
    }[scenario]
    for index in range(steps):
        progress = index / (steps - 1)
        if scenario == "recovery":
            rain_shape = 1.0 - progress
            level_shape = progress
        elif scenario == "normal":
            rain_shape = 0.6 + 0.4 * math.sin(math.pi * progress)
            level_shape = progress
        else:
            rain_shape = 0.65 + 0.35 * progress
            level_shape = progress
        rain = max(0.0, rainfall * scenario_rain_factor * rain_shape
                   + rng.uniform(-0.025, 0.025) * rainfall)
        rise = rise_rate * scenario_rise_factor
        level = max(0.0, initial_level + rise * index + rng.uniform(-0.01, 0.01))
        if scenario == "recovery":
            level = max(0.0, initial_level + rise_rate * (steps - 1) * (1.0 - level_shape))
        if scenario == "normal":
            phase = "baseline"
        elif scenario == "recovery":
            phase = "recovery"
        elif progress < 0.25:
            phase = "onset"
        elif progress < 0.8:
            phase = "escalation"
        else:
            phase = "peak"
        rows.append({
            "step": index,
            "timestamp": (start + timedelta(hours=index)).isoformat(),
            "rainfall_mm_h": round(rain, 3),
            "water_level_m": round(level, 3),
            "water_level_rise_m_h": round(rise if scenario != "recovery" else -rise, 4),
            "flow_velocity_m_s": round(min(2.0, 0.15 + 0.018 * rain + 0.2 * progress), 3),
            "debris_density": round(min(1.0, max(0.0, 0.12 + 0.006 * rain + 0.2 * progress)), 3),
            "los_obstruction": round(min(1.0, max(0.0, 0.08 + rain / 180.0 + 0.25 * progress)), 3),
            "node_available": communication_condition != "total",
            "scenario_phase": phase,
            "data_source": "synthetic_scenario",
        })

    config = {
        "region_id": region_id,
        "region_name": region_name,
        "scenario": scenario,
        "rainfall_mm_h": rainfall,
        "water_level_rise_m_h": rise_rate,
        "communication_condition": communication_condition,
        "playback": playback,
        "seed": seed,
        "steps": steps,
        "start_time": start.isoformat(),
        "initial_water_level_m": initial_level,
        "time_step_hours": 1,
    }
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    scenario_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    outage = {"healthy": 0.02, "partial": 0.28, "total": 1.0}[communication_condition]
    recovery = {"healthy": 0.35, "partial": 0.18, "total": 0.0}[communication_condition]
    return {
        "scenario_id": scenario_id,
        "mode": "synthetic_simulation",
        "region": {"id": region_id, "name": region_name},
        "configuration": config,
        "provenance": {
            "data_source": "synthetic_scenario_generator",
            "synthetic": True,
            "seed": seed,
            "configuration_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "created_at": "deterministic_from_configuration",
            "live_observations_used": False,
            "historical_data_used": False,
            "flood_assessment_status": "NOT_ASSESSED",
            "safety_note": (
                "Synthetic values are for demonstration only; they are not measurements, "
                "a flood forecast, an operational warning, or an all-clear."
            ),
        },
        "channel_context": {
            "node_outage_probability": outage,
            "node_recovery_probability": recovery,
        },
        "time_series": rows,
    }
