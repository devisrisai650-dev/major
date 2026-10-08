"""Local REST API for the FloodAI regional simulation pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from semantic_transmission import transmit_semantic_message
from services.flood_api import get_discharge_analysis
from services.flood_state import analyze_flood_state
from services.gauge_provider import CsvReplayProvider
from services.channel_predictor import predict_channel
from services.region_manager import get_region, load_regions
from services.semantic_priority import (
    build_semantic_priorities,
    calculate_semantic_compression,
    generate_semantic_message,
    select_transmission_parameters,
)
from services.weather_service import get_weather_data

def _flood_dashboard(analysis, water, weather, discharge):
    assessment = analysis["flood_assessment"]
    missing = assessment.get("missing_or_unconfigured", [])
    rainfall = analysis["rainfall"]
    river = analysis["river"]
    gauge = analysis["water_level"]
    classifications = [
        rainfall.get("classification"),
        river.get("classification"),
        gauge.get("classification"),
    ]
    severe = {"VERY_HIGH", "VERY_RAPIDLY_RISING"}
    elevated = {"HIGH", "RAPIDLY_RISING", "MODERATE"}
    signal = "HIGH" if any(x in severe for x in classifications) else "ELEVATED" if any(x in elevated for x in classifications) else "LOW"
    readiness = {
        "thresholds_verified": not any("verified official" in item for item in missing),
        "fresh_qc_gauge": bool(gauge.get("available") and gauge.get("is_recent")),
        "current_rainfall_available": rainfall.get("current_rain_mm") is not None,
        "complete_6h_rainfall_available": rainfall.get("last_6h_precipitation_mm") is not None,
        "assessment_ready": bool(assessment.get("complete")),
    }
    return {
        "assessment_status": assessment.get("status", "NOT_ASSESSED"),
        "assessment_state": assessment.get("state", "NOT_ASSESSED"),
        "assessment_ready": readiness["assessment_ready"],
        "environmental_signal": signal,
        "readiness": readiness,
        "missing_or_unconfigured": missing,
        "rainfall": rainfall,
        "river": river,
        "water_level": gauge,
        "message": assessment.get("reason"),
    }


def _communication_kpis(transmission):
    attempts = transmission.get("attempts", [])
    delivered = [x for x in attempts if x.get("delivered")]
    return {
        "attempt_count": len(attempts),
        "delivery_rate_percent": 100.0 * len(delivered) / len(attempts) if attempts else 0.0,
        "critical_delivery_percent": 100.0 if transmission.get("critical_delivered") else 0.0,
        "sic_success_percent": 100.0 * sum(bool(x.get("sic_success")) for x in attempts) / len(attempts) if attempts else 0.0,
        "node_availability_percent": 100.0 * sum(bool(x.get("node_available")) for x in attempts) / len(attempts) if attempts else 0.0,
        "mean_latency_ms": transmission.get("mean_latency_ms"),
        "mean_aoi_ms": transmission.get("delivery_aoi_ms"),
        "mean_throughput_mbps": transmission.get("mean_throughput_mbps"),
        "final_snr_db": attempts[-1].get("snr_db") if attempts else None,
        "final_user1_sinr_db": attempts[-1].get("user1_sinr_db") if attempts else None,
        "final_user2_sinr_db": attempts[-1].get("user2_sinr_db") if attempts else None,
    }


def _communication_alert(transmission):
    attempts = transmission.get("attempts", [])
    successful = [item for item in attempts if item.get("delivered")]
    last = attempts[-1] if attempts else {}
    if not attempts:
        return {"status": "OUTAGE", "reason": "No communication attempt was completed."}
    if successful:
        sinrs = [
            value for item in successful
            for value in (item.get("user1_sinr_db"), item.get("user2_sinr_db"))
            if value is not None
        ]
        min_sinr = min(sinrs) if sinrs else None
        status = "NORMAL" if min_sinr is None or min_sinr >= 10 else "DEGRADED"
        return {
            "status": status,
            "reason": "Critical semantic packet delivered by the simulated RIS-CNOMA link.",
            "min_sinr_db": min_sinr,
            "sic_success": all(bool(item.get("sic_success")) for item in successful),
        }
    reason = "Packet delivery failed after retry limit."
    if last.get("node_available") is False:
        reason = "Selected simulated communication node became unavailable."
    elif last.get("sic_success") is False:
        reason = "CNOMA SIC/decoding failed under the simulated channel."
    return {
        "status": "CRITICAL",
        "reason": reason,
        "min_sinr_db": min(
            [v for v in (last.get("user1_sinr_db"), last.get("user2_sinr_db")) if v is not None],
            default=None,
        ),
        "sic_success": bool(last.get("sic_success")),
    }


app = FastAPI(
    title="FloodAI Local API",
    description="Environmental replay + semantic communication + software-only virtual RIS simulation.",
    version="1.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

API_REQUESTS = Counter(
    "floodai_api_requests_total",
    "Total HTTP requests handled by FloodAI API.",
    ["method", "path", "status"],
)
API_LATENCY = Histogram(
    "floodai_api_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
)
PIPELINE_RUNS = Counter(
    "floodai_pipeline_runs_total",
    "Total FloodAI pipeline executions.",
    ["region_id", "learning_enabled"],
)
PIPELINE_ERRORS = Counter(
    "floodai_pipeline_errors_total",
    "Total FloodAI pipeline errors.",
    ["stage"],
)


@app.middleware("http")
async def prometheus_middleware(request, call_next):
    import time

    started = time.perf_counter()
    response = await call_next(request)
    path = request.url.path
    API_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    API_LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
    return response


@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(Path(__file__).resolve().parent / "web" / "index.html")


class RunRequest(BaseModel):
    region_id: str = Field(min_length=1)
    communication_attempts: int = Field(default=5, ge=1, le=20)
    seed: int = 2026
    learn: bool = False


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "FloodAI Local API", "simulation_only": True}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/regions")
def regions():
    return load_regions()


@app.get("/api/regions/{region_id}")
def region_detail(region_id: str):
    try:
        region = get_region(region_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"region": region, "water_level_source": CsvReplayProvider().get_water_level(region)}


@app.post("/api/run")
def run_pipeline(request: RunRequest) -> dict[str, Any]:
    PIPELINE_RUNS.labels(request.region_id, str(request.learn).lower()).inc()
    try:
        region = get_region(request.region_id)
    except ValueError as exc:
        PIPELINE_ERRORS.labels("region").inc()
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        weather = get_weather_data(
            region["latitude"],
            region["longitude"],
            region.get("timezone", "Asia/Kolkata"),
        )
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        PIPELINE_ERRORS.labels("weather").inc()
        raise HTTPException(status_code=502, detail=f"Weather service unavailable: {exc}") from exc

    discharge = get_discharge_analysis(region["latitude"], region["longitude"])
    water = CsvReplayProvider().get_water_level(region)
    analysis = analyze_flood_state(weather, discharge, water)
    priorities = build_semantic_priorities(weather, analysis)
    selected = select_transmission_parameters(priorities)
    message = generate_semantic_message(region["name"], analysis, selected)
    compression = calculate_semantic_compression(len(priorities), len(selected))
    water_depth = water.get("current_level_m") if water.get("available") else None
    rain_mm = weather.get("current", {}).get("rain_mm")
    discharge_value = discharge.get("discharge_m3s") if discharge.get("available") else None
    channel_features = {
        "water_depth": water_depth,
        "los_obstruction": (
            min(1.0, max(0.0, float(rain_mm or 0.0) / 100.0 + float(water_depth or 0.0) / 5.0))
            if water_depth is not None else None
        ),
        "debris_density": (
            min(1.0, 0.05 + float(water_depth or 0.0) / 4.0)
            if water_depth is not None else None
        ),
        "flow_velocity": (
            min(2.0, max(0.0, float(discharge_value) / 50.0))
            if discharge_value is not None else None
        ),
        "reflection_dominance": 1.0,
    }
    channel_prediction = predict_channel(**channel_features, scenario="regional_proxy_simulation")
    simulation_context = {
        "rain_mm": rain_mm,
        "flow_velocity_mps": channel_features["flow_velocity"],
        "water_depth_m": water_depth,
        "debris_density": channel_features["debris_density"],
        "los_obstruction": channel_features["los_obstruction"],
    }

    try:
        transmission = transmit_semantic_message(
            packet=message,
            priorities=priorities,
            policy_path=Path(__file__).resolve().parent / "models" / "ris_q_table.npz",
            max_attempts=request.communication_attempts,
            seed=request.seed,
            learn=request.learn,
            channel_context=simulation_context,
        )
    except FileNotFoundError as exc:
        PIPELINE_ERRORS.labels("model").inc()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        PIPELINE_ERRORS.labels("communication").inc()
        raise HTTPException(status_code=500, detail=f"Simulated communication failed: {exc}") from exc

    flood_dashboard = _flood_dashboard(analysis, water, weather, discharge)
    communication_kpis = _communication_kpis(transmission)

    return {
        "region": region,
        "weather": weather,
        "river_discharge": discharge,
        "water_level": water,
        "flood_assessment": analysis["flood_assessment"],
        "flood_dashboard": flood_dashboard,
        "flood_indicators": {
            "rainfall": analysis["rainfall"],
            "river": analysis["river"],
            "water_level": analysis["water_level"],
        },
        "semantic_priorities": priorities,
        "selected_parameters": selected,
        "semantic_message": message,
        "semantic_compression_percent": compression,
        "channel_prediction": channel_prediction,
        "communication_alert": _communication_alert(transmission),
        "communication_kpis": communication_kpis,
        "communication": transmission,
        "provenance": {
            "communication_mode": "software_simulation",
            "seed": request.seed,
            "learning_enabled": request.learn,
            "weather_source": weather.get("source"),
            "gauge_mode": water.get("mode", "historical_replay"),
            "flood_assessment_status": "NOT_ASSESSED",
            "channel_scenario": "regional_proxy_simulation",
            "cnoma_enabled": True,
        },
        "disclaimer": {
            "flood_assessment": "NOT_ASSESSED is neither a flood warning nor an all-clear.",
            "communication": "SNR, latency, RIS and packet delivery are simulated.",
        },
    }
