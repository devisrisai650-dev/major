"""Local REST API for the FloodAI data-to-semantic-to-virtual-RIS pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse

from services.region_manager import get_region, load_regions
from services.weather_service import get_weather_data
from services.flood_api import get_discharge_analysis
from services.water_level import get_water_level_analysis
from services.flood_state import analyze_flood_state
from services.semantic_priority import (
    build_semantic_priorities,
    select_transmission_parameters,
    generate_semantic_message,
)
from semantic_transmission import transmit_semantic_message


app = FastAPI(
    title="FloodAI Local API",
    description=(
        "Regional weather/hydrology, semantic message selection, and a "
        "software-only channel/RIS simulation. Flood decisions are NOT_ASSESSED "
        "until validated local thresholds and current gauge data are configured."
    ),
    version="0.1.0",
)

# The API is intended for a local development webpage, not public deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(Path(__file__).resolve().parent / "web" / "index.html")


class RunRequest(BaseModel):
    region_id: str = Field(min_length=1)
    communication_attempts: int = Field(default=5, ge=1, le=20)
    seed: int | None = None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "FloodAI Local API", "communication_mode": "software_simulation"}


@app.get("/api/regions")
def regions() -> list[dict[str, Any]]:
    return load_regions()


@app.get("/api/regions/{region_id}")
def region_detail(region_id: str) -> dict[str, Any]:
    try:
        region = get_region(region_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    water = get_water_level_analysis(region)
    return {"region": region, "water_level_source": water}


@app.post("/api/run")
def run_pipeline(request: RunRequest) -> dict[str, Any]:
    """Run environmental analysis, semantic selection, and virtual transmission."""
    try:
        region = get_region(request.region_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        weather = get_weather_data(
            region["latitude"], region["longitude"], region.get("timezone", "Asia/Kolkata")
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Weather service unavailable: {exc}") from exc

    discharge = get_discharge_analysis(region["latitude"], region["longitude"])
    water = get_water_level_analysis(region)
    analysis = analyze_flood_state(weather, discharge, water)
    priorities = build_semantic_priorities(weather, analysis)
    selected = select_transmission_parameters(priorities)
    message = generate_semantic_message(region["name"], analysis, selected)

    try:
        transmission = transmit_semantic_message(
            packet=message,
            priorities=priorities,
            policy_path=Path(__file__).resolve().parent / "models" / "ris_q_table.npz",
            max_attempts=request.communication_attempts,
            seed=request.seed if request.seed is not None else 2026,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Simulated communication failed: {exc}") from exc

    return {
        "region": region,
        "weather": weather,
        "river_discharge": discharge,
        "water_level": water,
        "flood_assessment": analysis["flood_assessment"],
        "flood_indicators": {
            "rainfall": analysis["rainfall"],
            "river": analysis["river"],
            "water_level": analysis["water_level"],
        },
        "semantic_priorities": priorities,
        "selected_parameters": selected,
        "semantic_message": message,
        "communication": transmission,
        "disclaimer": {
            "flood_assessment": "NOT_ASSESSED is not an all-clear or a flood warning.",
            "communication": "Channel measurements, RIS effects, and delivery outcomes are simulated.",
        },
    }
