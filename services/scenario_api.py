"""REST endpoints for the synthetic FloodAI Scenario Lab."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from semantic_transmission import transmit_semantic_message
from services.flood_scenario_generator import (
    COMMUNICATION_CONDITIONS,
    PLAYBACK_MODES,
    SCENARIOS,
    generate_scenario,
)
from services.region_manager import get_region, load_regions
from services.json_safe import to_json_safe


router = APIRouter(prefix="/api/scenarios", tags=["scenario-lab"])


class ScenarioRequest(BaseModel):
    region_id: str = Field(default="region_001", min_length=1)
    scenario: str = Field(default="severe")
    rainfall_mm_h: float = Field(default=80.0, ge=0.0, le=300.0)
    water_level_rise_m_h: float = Field(default=0.25, ge=0.0, le=1.0)
    communication_condition: str = Field(default="partial")
    playback: str = Field(default="normal")
    seed: int = 2026
    steps: int = Field(default=24, ge=2, le=168)
    start_time: str = "2026-10-12T00:00:00+05:30"
    initial_water_level_m: float = Field(default=1.0, ge=0.0, le=100.0)


class ScenarioRunRequest(ScenarioRequest):
    step_index: int = Field(default=0, ge=0)
    communication_attempts: int = Field(default=5, ge=1, le=20)
    learn: bool = False


def _make_scenario(request: ScenarioRequest) -> dict[str, Any]:
    try:
        region = get_region(request.region_id)
        if request.scenario not in SCENARIOS:
            raise ValueError(f"scenario must be one of {sorted(SCENARIOS)}")
        if request.communication_condition not in COMMUNICATION_CONDITIONS:
            raise ValueError(
                f"communication_condition must be one of {sorted(COMMUNICATION_CONDITIONS)}"
            )
        if request.playback not in PLAYBACK_MODES:
            raise ValueError(f"playback must be one of {sorted(PLAYBACK_MODES)}")
        return generate_scenario(
            region_id=region["id"],
            region_name=region["name"],
            scenario=request.scenario,
            rainfall_mm_h=request.rainfall_mm_h,
            water_level_rise_m_h=request.water_level_rise_m_h,
            communication_condition=request.communication_condition,
            playback=request.playback,
            seed=request.seed,
            steps=request.steps,
            start_time=request.start_time,
            initial_water_level_m=request.initial_water_level_m,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/options")
def scenario_options() -> dict[str, Any]:
    """Return selectable configured regions and supported demo controls."""
    return {
        "regions": load_regions(),
        "scenarios": sorted(SCENARIOS),
        "communication_conditions": sorted(COMMUNICATION_CONDITIONS),
        "playback_modes": sorted(PLAYBACK_MODES),
        "default_configuration": {
            "scenario": "severe",
            "rainfall_mm_h": 80.0,
            "water_level_rise_m_h": 0.25,
            "communication_condition": "partial",
            "playback": "normal",
            "steps": 24,
            "seed": 2026,
        },
        "simulation_only": True,
    }


@router.post("/generate")
def generate(request: ScenarioRequest) -> dict[str, Any]:
    """Create a deterministic series for the selected region and start time."""
    return _make_scenario(request)


@router.post("/run")
def run_scenario(request: ScenarioRunRequest) -> dict[str, Any]:
    """Feed one selected synthetic time step into the existing communication loop."""
    scenario = _make_scenario(request)
    if request.step_index >= len(scenario["time_series"]):
        raise HTTPException(
            status_code=422,
            detail=f"step_index must be below {len(scenario['time_series'])}",
        )
    sample = scenario["time_series"][request.step_index]
    context = {
        **scenario["channel_context"],
        "rain_mm": sample["rainfall_mm_h"],
        "flow_velocity_mps": sample["flow_velocity_m_s"],
        "water_depth_m": sample["water_level_m"],
        "debris_density": sample["debris_density"],
        "los_obstruction": sample["los_obstruction"],
    }
    packet = (
        f"SIMULATION ONLY | {scenario['region']['name']} | "
        f"scenario={request.scenario} | phase={sample['scenario_phase']} | "
        f"synthetic rainfall={sample['rainfall_mm_h']:.1f} mm/h | "
        f"synthetic water level={sample['water_level_m']:.2f} m. "
        "This is not an operational flood warning."
    )
    priorities = {
        "synthetic_flood_scenario": {
            "value": {
                "scenario": request.scenario,
                "phase": sample["scenario_phase"],
                "rainfall_mm_h": sample["rainfall_mm_h"],
                "water_level_m": sample["water_level_m"],
            },
            "available": True,
            "priority": "CRITICAL" if request.scenario == "emergency" else "HIGH",
            "source": "synthetic_scenario",
        }
    }
    policy_path = Path(__file__).resolve().parents[1] / "models" / "ris_q_table.npz"
    try:
        transmission = transmit_semantic_message(
            packet=packet,
            priorities=priorities,
            policy_path=policy_path,
            max_attempts=request.communication_attempts,
            seed=request.seed,
            learn=request.learn,
            channel_context=context,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        # Keep the architecture/scenario output available even when a local
        # trained Q-table is missing or incompatible. Do not invent delivery
        # metrics: communication is explicitly marked unavailable.
        transmission = {
            "delivered": None,
            "critical_delivered": False,
            "attempts": [],
            "mean_latency_ms": None,
            "mean_throughput_mbps": None,
            "orchestrator": {
                "policy": "unavailable",
                "selected_policy": None,
                "reason": "Communication model could not run because the saved Q-table is unavailable or incompatible.",
            },
            "simulation_only": True,
            "error": str(exc),
            "status": "communication_unavailable",
        }

    return to_json_safe({
        "scenario": scenario,
        "selected_time_step": sample,
        "semantic_packet": packet,
        "semantic_priorities": priorities,
        "communication": transmission,
        "communication_status": (
            "completed" if "error" not in transmission else "unavailable"
        ),
        "architecture_output": {
            "scenario_generator": "completed",
            "synthetic_environment": "completed",
            "semantic_packet": "prepared",
            "channel_context": "prepared",
            "ris_cnoma_communication": (
                "completed" if "error" not in transmission else "unavailable"
            ),
            "reason": transmission.get("error"),
        },
        "orchestrator": transmission.get("orchestrator", {}),
        "flood_assessment": {
            "status": "NOT_ASSESSED",
            "state": "NOT_ASSESSED",
            "score": None,
            "complete": False,
            "assessment_type": "synthetic_simulation",
            "reason": (
                "Synthetic scenario inputs cannot establish real flood risk. Official "
                "verified thresholds and fresh QC-passed gauge evidence are required."
            ),
        },
        "provenance": {
            **scenario["provenance"],
            "communication_mode": "software_simulation",
            "selected_step_index": request.step_index,
            "learning_enabled": request.learn,
            "orchestrator_policy": transmission.get("orchestrator", {}).get("policy"),
        },
        "disclaimer": (
            "Demonstration only. Synthetic flood values and simulated radio delivery are "
            "not live measurements, a flood warning, or an all-clear. Follow official "
            "local authorities for safety decisions."
        ),
    })
