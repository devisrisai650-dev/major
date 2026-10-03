from __future__ import annotations

from pathlib import Path
import json


_PRIORITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
_DEFAULT_RULES = {
    "rainfall_current": "MEDIUM",
    "rainfall_last_6h": "MEDIUM",
    "water_level": "HIGH",
    "water_level_rate": "HIGH",
    "river_discharge_forecast": "MEDIUM",
}


def _load_rules() -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / "config" / "semantic_priority.json"
    if not path.exists():
        return dict(_DEFAULT_RULES)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = data.get("field_priority", {})
        return {
            key: value for key, value in rules.items()
            if key in _DEFAULT_RULES and value in _PRIORITY_ORDER
        } or dict(_DEFAULT_RULES)
    except (OSError, ValueError, TypeError):
        return dict(_DEFAULT_RULES)


def build_semantic_priorities(weather, flood_state_data):
    rainfall = flood_state_data["rainfall"]
    river = flood_state_data["river"]
    water = flood_state_data["water_level"]
    rules = _load_rules()

    items = {
        "rainfall_current": (
            rainfall.get("current_rain_mm"),
            rainfall.get("current_rain_mm") is not None,
            rules["rainfall_current"],
            "mm",
            "Open-Meteo model-derived current weather",
            "model_derived",
            rainfall.get("current_time"),
        ),
        "rainfall_last_6h": (
            rainfall.get("last_6h_precipitation_mm"),
            rainfall.get("last_6h_precipitation_mm") is not None,
            rules["rainfall_last_6h"],
            "mm",
            "Open-Meteo model-derived hourly precipitation",
            "model_derived",
            rainfall.get("current_time"),
        ),
        "water_level": (
            water.get("current_m"),
            bool(water.get("available")),
            rules["water_level"],
            "m",
            f"configured gauge replay: {water.get('station')}",
            "qc_passed" if water.get("available") else "unavailable",
            water.get("current_time"),
        ),
        "water_level_rate": (
            water.get("rate_of_change_m_per_hour"),
            water.get("rate_of_change_m_per_hour") is not None,
            rules["water_level_rate"],
            "m/h",
            f"configured gauge replay: {water.get('station')}",
            "qc_passed" if water.get("rate_of_change_m_per_hour") is not None else "unavailable",
            water.get("current_time"),
        ),
        "river_discharge_forecast": (
            river.get("discharge_m3s"),
            bool(river.get("available")),
            rules["river_discharge_forecast"],
            "m3/s",
            "Open-Meteo modeled daily river-discharge forecast",
            river.get("data_type", "unavailable"),
            river.get("time"),
        ),
    }

    out = {}
    for name, (value, available, priority, unit, source, quality, timestamp) in items.items():
        score = _PRIORITY_ORDER[priority]
        out[name] = {
            "value": value,
            "available": available,
            "score": score,
            "priority": priority if available else "LOW",
            "unit": unit,
            "source": source,
            "quality": quality,
            "timestamp": timestamp,
        }
    return out


def select_transmission_parameters(priorities, minimum_priority="MEDIUM"):
    if minimum_priority not in _PRIORITY_ORDER:
        raise ValueError(f"Unknown priority: {minimum_priority}")
    threshold = _PRIORITY_ORDER[minimum_priority]
    return {
        key: item for key, item in priorities.items()
        if item["available"] and _PRIORITY_ORDER[item["priority"]] >= threshold
    }


def generate_semantic_message(region_name, flood_state_data, selected_parameters):
    parts = [
        f"REGION={region_name}",
        "FLOOD_ASSESSMENT=NOT_ASSESSED",
    ]
    for key, item in selected_parameters.items():
        value = item["value"]
        unit = item.get("unit", "")
        timestamp = item.get("timestamp") or ""
        source = item.get("source", "unknown")
        quality = item.get("quality", "unknown")
        suffix = f" {unit}" if unit else ""
        if timestamp:
            suffix += f" @ {timestamp}"
        parts.append(
            f"{key.upper()}={value}{suffix};SOURCE={source};QUALITY={quality}"
        )
    return " | ".join(parts)


def calculate_semantic_compression(total_parameters, transmitted_parameters):
    if total_parameters <= 0:
        return 0.0
    return (1 - transmitted_parameters / total_parameters) * 100
