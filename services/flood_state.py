"""Conservative flood-state assessment with explicit threshold/data gating."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

THRESHOLD_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "flood_thresholds.json"
)


def classify_rainfall(mm):
    if mm is None:
        return "UNKNOWN"
    if mm < 2:
        return "LOW"
    if mm < 10:
        return "MODERATE"
    if mm < 20:
        return "HIGH"
    return "VERY_HIGH"


def classify_water_level_rise(rate):
    if rate is None:
        return "UNKNOWN"
    if rate < 0.02:
        return "STABLE"
    if rate < 0.10:
        return "RISING"
    if rate < 0.20:
        return "RAPIDLY_RISING"
    return "VERY_RAPIDLY_RISING"


def classify_discharge(value):
    if value is None:
        return "UNKNOWN"
    if value < 10:
        return "LOW"
    if value < 100:
        return "MODERATE"
    if value < 500:
        return "HIGH"
    return "VERY_HIGH"


def _thresholds_verified():
    try:
        data = json.loads(THRESHOLD_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return (
        bool(data.get("verified"))
        and bool(data.get("thresholds"))
        and bool(data.get("source"))
    )


def analyze_flood_state(weather, flood_data, water_level):
    windows = weather.get("rainfall_windows", {})
    current = weather.get("current", {})
    rain = current.get("rain_mm")
    rain_6h = windows.get("last_6h_precipitation_mm")
    rain_24h = windows.get("last_24h_precipitation_mm")
    fresh_gauge = bool(water_level.get("available")) and bool(
        water_level.get("is_recent")
    )
    gauge_trend = (
        water_level.get("rate_of_change_m_per_hour") if fresh_gauge else None
    )

    missing = []
    if rain is None:
        missing.append("current local rainfall")
    if rain_6h is None:
        missing.append("complete observed 6-hour rainfall window")
    if not fresh_gauge:
        missing.append("fresh configured river-gauge reading")
    if not _thresholds_verified():
        missing.append("verified official station-specific warning thresholds")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rainfall": {
            "current_rain_mm": rain,
            "classification": classify_rainfall(rain),
            "last_1h_precipitation_mm": windows.get("last_1h_precipitation_mm"),
            "last_3h_precipitation_mm": windows.get("last_3h_precipitation_mm"),
            "last_6h_precipitation_mm": rain_6h,
            "last_24h_precipitation_mm": rain_24h,
        },
        "river": {
            "discharge_m3s": flood_data.get("discharge_m3s"),
            "available": flood_data.get("available", False),
            "data_type": flood_data.get("data_type", "unknown"),
            "time": flood_data.get("time"),
            "classification": classify_discharge(
                flood_data.get("discharge_m3s")
            ),
            "reason": flood_data.get("reason"),
        },
        "water_level": {
            "available": fresh_gauge,
            "current_m": (
                water_level.get("current_level_m") if fresh_gauge else None
            ),
            "latest_observed_m": water_level.get("latest_observed_m"),
            "previous_m": (
                water_level.get("previous_level_m") if fresh_gauge else None
            ),
            "change_m": water_level.get("change_m") if fresh_gauge else None,
            "rate_of_change_m_per_hour": gauge_trend,
            "classification": classify_water_level_rise(gauge_trend),
            "reason": water_level.get("reason"),
            "station": water_level.get("station"),
            "observation_time": water_level.get("current_time"),
            "age_hours": water_level.get("age_hours"),
        },
        "flood_assessment": {
            "status": "NOT_ASSESSED",
            "state": "NOT_ASSESSED",
            "score": None,
            "complete": False,
            "reason": (
                "Flood assessment remains NOT_ASSESSED because verified official "
                "station-specific warning thresholds and fresh QC-passed gauge "
                "evidence are not both configured. This is not a flood warning "
                "or an all-clear."
            ),
            "missing_or_unconfigured": missing,
        },
    }
