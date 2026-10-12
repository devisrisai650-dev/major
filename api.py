"""Local REST API for the FloodAI regional simulation pipeline."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import requests
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
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
from services.json_safe import to_json_safe
from services.auth_api import router as auth_router
from services.auth_service import get_user_from_request, init_db, require_user
from services.alert_monitor import start_alert_monitor, stop_alert_monitor

_alert_monitor_task = None

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
    readiness = {
        "thresholds_verified": not any("verified official" in item for item in missing),
        "fresh_qc_gauge": bool(gauge.get("available") and gauge.get("is_recent")),
        "current_rainfall_available": rainfall.get("current_rain_mm") is not None,
        "complete_6h_rainfall_available": rainfall.get("last_6h_precipitation_mm") is not None,
        "assessment_ready": bool(assessment.get("complete")),
    }
    # Never summarize incomplete evidence as a LOW flood signal. Indicators are
    # descriptive only until official thresholds and fresh QC gauge evidence exist.
    if not readiness["assessment_ready"]:
        signal = "INCOMPLETE"
    elif any(x in severe for x in classifications):
        signal = "HIGH"
    elif any(x in elevated for x in classifications):
        signal = "ELEVATED"
    else:
        signal = "LOW"
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
        "mean_latency_ms": transmission.get("mean_latency_ms"),
        "mean_aoi_ms": transmission.get("mean_aoi_ms"),
        "delivery_aoi_ms": transmission.get("delivery_aoi_ms"),
        "final_aoi_ms": transmission.get("final_aoi_ms"),
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
    if last.get("sic_success") is False:
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
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(auth_router)

@app.on_event("startup")
async def initialize_auth_database():
    global _alert_monitor_task
    init_db()
    _alert_monitor_task = start_alert_monitor()

@app.on_event("shutdown")
async def shutdown_alert_monitor():
    await stop_alert_monitor(_alert_monitor_task)

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


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(Path(__file__).resolve().parent / "web" / "login.html")

@app.get("/", include_in_schema=False)
def homepage(request: Request):
    user = get_user_from_request(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] == "admin":
        return RedirectResponse("/admin", status_code=303)
    return FileResponse(Path(__file__).resolve().parent / "web" / "index.html")

@app.get("/admin", include_in_schema=False)
def admin_page(request: Request):
    admin = get_user_from_request(request)
    if not admin:
        return RedirectResponse("/login", status_code=303)
    if admin["role"] != "admin":
        return RedirectResponse("/", status_code=303)
    return FileResponse(Path(__file__).resolve().parent / "web" / "admin.html")


class RunRequest(BaseModel):
    region_id: str = Field(min_length=1)
    communication_attempts: int = Field(default=5, ge=1, le=20)
    seed: int = 2026
    time_of_day: str = Field(default="12:00", pattern=r"^(?:[01]\d|2[0-3]):00$")
    learn: bool = False
    scenario_mode: str = Field(default="demo", pattern="^(demo|live)$")


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
def region_detail(region_id: str, user: dict[str, Any] = Depends(require_user)):
    try:
        region = get_region(region_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"region": region, "water_level_source": CsvReplayProvider().get_water_level(region)}


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

    # Select the requested local hour for the weather card. Flood assessment still
    # uses current observations and the verified-data gate; a forecast is not
    # silently treated as a current gauge reading.
    hourly_conditions = weather.get("hourly_conditions", [])
    current_stamp = weather.get("current", {}).get("time")
    if current_stamp and hourly_conditions:
        selected_stamp = f"{current_stamp[:10]}T{request.time_of_day}"
        selected = next(
            (row for row in hourly_conditions if row.get("time") == selected_stamp),
            None,
        )
        if selected is not None:
            weather["selected_hour"] = selected
        else:
            weather["selected_hour"] = None

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

    return to_json_safe({
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
        "orchestrator": transmission.get("orchestrator", {
            "policy": "unavailable",
            "reason": "Communication result did not include orchestrator metadata.",
            "simulation_only": True,
        }),
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
            "orchestrator_policy": transmission.get("orchestrator", {}).get("policy", "unavailable"),
        },
        "disclaimer": {
            "flood_assessment": "NOT_ASSESSED is neither a flood warning nor an all-clear.",
            "communication": "SNR, latency, RIS and packet delivery are simulated.",
        },
    })


@app.post("/api/dashboard")
def dashboard(request: RunRequest, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    """Return flood and environmental information only; do not run research simulations."""
    try:
        region = get_region(request.region_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        weather = get_weather_data(
            region["latitude"],
            region["longitude"],
            region.get("timezone", "Asia/Kolkata"),
        )
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"Weather service unavailable: {exc}") from exc

    hourly_conditions = weather.get("hourly_conditions", [])
    current_stamp = weather.get("current", {}).get("time")
    if current_stamp and hourly_conditions:
        selected_stamp = f"{current_stamp[:10]}T{request.time_of_day}"
        weather["selected_hour"] = next(
            (row for row in hourly_conditions if row.get("time") == selected_stamp),
            None,
        )

    discharge = get_discharge_analysis(region["latitude"], region["longitude"])
    water = CsvReplayProvider().get_water_level(region)
    analysis = analyze_flood_state(weather, discharge, water)
    scenario = None
    if request.scenario_mode == "demo":
        # Clearly labelled synthetic scenario: demonstration data must never be
        # presented as an official warning or mixed silently with live gauge data.
        scenario_path = Path(__file__).resolve().parent / "config" / "demo_flood_scenarios.csv"
        try:
            with scenario_path.open(newline="", encoding="utf-8") as handle:
                scenario = next(
                    row for row in csv.DictReader(handle)
                    if row["region_id"] == region["id"] and row["hour"] == request.time_of_day
                )
        except (OSError, StopIteration, KeyError) as exc:
            raise HTTPException(status_code=500, detail="Demo scenario dataset is missing a selected region/time row.") from exc

        rain = float(scenario["rainfall_mm_per_hour"])
        rain6 = float(scenario["rainfall_6h_mm"])
        rain24 = float(scenario["rainfall_24h_mm"])
        rise = float(scenario["water_level_rise_m_per_hour"])
        level = float(scenario["water_level_m"])
        demo_discharge = float(scenario["river_discharge_m3s"])
        weather["source"] = "Open-Meteo weather + synthetic flood demo rainfall"
        weather.setdefault("current", {})["rain_mm"] = rain
        if weather.get("selected_hour") is not None:
            weather["selected_hour"] = dict(weather["selected_hour"])
            weather["selected_hour"]["rain_mm"] = rain
            weather["selected_hour"]["precipitation_mm"] = rain
            weather["selected_hour"]["source_type"] = "synthetic_demo"
        weather["rainfall_windows"] = {
            "last_1h_precipitation_mm": rain,
            "last_3h_precipitation_mm": rain * 3,
            "last_6h_precipitation_mm": rain6,
            "last_24h_precipitation_mm": rain24,
        }
        analysis["rainfall"] = {
            "current_rain_mm": rain,
            "classification": "VERY_HIGH" if rain >= 20 else "HIGH" if rain >= 10 else "LOW",
            "last_1h_precipitation_mm": rain,
            "last_3h_precipitation_mm": rain * 3,
            "last_6h_precipitation_mm": rain6,
            "last_24h_precipitation_mm": rain24,
            "source": "synthetic demonstration dataset",
        }
        discharge = {
            "discharge_m3s": demo_discharge, "available": True,
            "time": request.time_of_day, "data_type": "synthetic_demo",
            "reason": "Synthetic demonstration value; not a live gauge measurement.",
        }
        analysis["river"] = {
            "discharge_m3s": demo_discharge, "available": True,
            "data_type": "synthetic_demo", "time": request.time_of_day,
            "classification": "HIGH" if demo_discharge >= 100 else "MODERATE",
            "reason": "Synthetic demonstration value; not a live gauge measurement.",
        }
        water.update({
            "available": True, "is_recent": True, "current_level_m": level,
            "latest_observed_m": level, "current_time": request.time_of_day,
            "age_hours": 0.0, "rate_of_change_m_per_hour": rise,
            "station": "SYNTHETIC_DEMO", "reason": "Synthetic scenario value; not an official gauge reading.",
        })
        analysis["water_level"] = {
            "available": True, "current_m": level, "latest_observed_m": level,
            "rate_of_change_m_per_hour": rise,
            "classification": "VERY_RAPIDLY_RISING" if rise >= 0.2 else "RAPIDLY_RISING" if rise >= 0.1 else "RISING",
            "station": "SYNTHETIC_DEMO", "observation_time": request.time_of_day,
            "age_hours": 0.0, "reason": "Synthetic demonstration value; not an official gauge reading.",
        }
        analysis["flood_assessment"] = {
            "status": "DEMO_FLOOD_SCENARIO", "state": "DEMO_FLOOD_SCENARIO",
            "score": None, "complete": False,
            "reason": "SIMULATED FLOOD DEMONSTRATION ONLY. Synthetic data is not a real flood warning or an all-clear.",
            "missing_or_unconfigured": ["synthetic demonstration; official thresholds and live QC gauge evidence are not applied"],
        }
    flood = _flood_dashboard(analysis, water, weather, discharge)
    if scenario is not None:
        flood["assessment_status"] = "DEMO_FLOOD_SCENARIO"
        flood["environmental_signal"] = "HIGH" if scenario["communication_status"] == "PARTIAL_OUTAGE" else "ELEVATED" if scenario["communication_status"] == "DEGRADED" else "LOW"
        flood["message"] = "SIMULATED FLOOD DEMONSTRATION ONLY — synthetic rainfall and gauge values are not real-world warnings."
        flood["readiness"]["assessment_ready"] = False
    indicators = {
        "rainfall": analysis.get("rainfall", {}),
        "river": analysis.get("river", {}),
        "water_level": analysis.get("water_level", {}),
    }
    assessment = analysis.get("flood_assessment", {})
    return to_json_safe({
        "scenario_mode": request.scenario_mode,
        "scenario_notice": "SYNTHETIC FLOOD DEMONSTRATION — not a real warning" if request.scenario_mode == "demo" else "Live environmental inputs; flood risk remains NOT_ASSESSED without verified official evidence.",
        "communication_scenario": scenario.get("communication_status") if scenario else None,
        "region": {"id": region.get("id"), "name": region.get("name"), "river": region.get("river")},
        "weather": {
            "source": weather.get("source", "Open-Meteo"),
            "current": weather.get("current", {}),
            "selected_hour": weather.get("selected_hour"),
        },
        "river_discharge": {
            "available": discharge.get("available", False),
            "discharge_m3s": discharge.get("discharge_m3s"),
            "time": discharge.get("time"),
            "reason": discharge.get("reason"),
        },
        "water_level": {
            "available": water.get("available", False),
            "current_level_m": water.get("current_level_m"),
            "latest_observed_m": water.get("latest_observed_m"),
            "current_time": water.get("current_time"),
            "age_hours": water.get("age_hours"),
            "station": water.get("station"),
            "reason": water.get("reason"),
        },
        "flood_assessment": {
            "status": assessment.get("status", "NOT_ASSESSED"),
            "state": assessment.get("state", "NOT_ASSESSED"),
            "complete": assessment.get("complete", False),
            "reason": assessment.get("reason"),
        },
        "flood_dashboard": {
            "assessment_status": flood.get("assessment_status", "NOT_ASSESSED"),
            "environmental_signal": flood.get("environmental_signal", "UNKNOWN"),
            "message": flood.get("message"),
            "readiness": {"assessment_ready": flood.get("readiness", {}).get("assessment_ready", False)},
        },
        "flood_indicators": {
            "rainfall": {
                "classification": indicators["rainfall"].get("classification"),
                "current_rain_mm": indicators["rainfall"].get("current_rain_mm"),
                "last_6h_precipitation_mm": indicators["rainfall"].get("last_6h_precipitation_mm"),
                "last_24h_precipitation_mm": indicators["rainfall"].get("last_24h_precipitation_mm"),
            },
            "river": {
                "classification": indicators["river"].get("classification"),
                "available": indicators["river"].get("available", False),
                "discharge_m3s": indicators["river"].get("discharge_m3s"),
            },
            "water_level": {
                "classification": indicators["water_level"].get("classification"),
                "available": indicators["water_level"].get("available", False),
                "current_m": indicators["water_level"].get("current_m"),
                "rate_of_change_m_per_hour": indicators["water_level"].get("rate_of_change_m_per_hour"),
            },
        },
    })

