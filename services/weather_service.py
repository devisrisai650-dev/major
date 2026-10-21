from datetime import datetime, timedelta, timezone as dt_timezone
import requests

BASE_URL = "https://api.open-meteo.com/v1/forecast"


def get_weather_data(latitude, longitude, timezone="Asia/Kolkata"):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "current": "temperature_2m,relative_humidity_2m,precipitation,rain,showers,wind_speed_10m,wind_direction_10m,surface_pressure",
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,rain,showers,wind_speed_10m,wind_direction_10m",
        "past_days": 1,
        "forecast_days": 2,
    }
    response = requests.get(BASE_URL, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    now = datetime.fromisoformat(data["current"]["time"])
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    rows = []
    hourly_conditions = []
    for i, stamp in enumerate(times):
        t = datetime.fromisoformat(stamp)
        row = {
            "time": stamp,
            "temperature_c": _at(hourly.get("temperature_2m"), i),
            "humidity_pct": _at(hourly.get("relative_humidity_2m"), i),
            "precipitation_mm": _at(hourly.get("precipitation"), i),
            "rain_mm": _at(hourly.get("rain"), i),
            "showers_mm": _at(hourly.get("showers"), i),
            "wind_speed_kmh": _at(hourly.get("wind_speed_10m"), i),
            "wind_direction_deg": _at(hourly.get("wind_direction_10m"), i),
            "source_type": "past_model_estimate" if t < now else "forecast",
        }
        hourly_conditions.append(row)
        if t <= now:
            rows.append({
                "time": stamp,
                "rain_mm": row["rain_mm"],
                "precipitation_mm": row["precipitation_mm"],
                "showers_mm": row["showers_mm"],
            })
    rain_windows = {}
    for hours in (1, 3, 6, 24):
        cutoff = now - timedelta(hours=hours)
        window = [
            row for row in rows
            if cutoff < datetime.fromisoformat(row["time"]) <= now
        ]
        values = [
            row["precipitation_mm"] for row in window
            if row["precipitation_mm"] is not None
        ]
        rain_windows[f"last_{hours}h_precipitation_mm"] = (
            sum(values) if len(values) == hours else None
        )
        rain_windows[f"last_{hours}h_observations"] = len(values)
    current = data.get("current", {})
    return {
        "current": {
            "time": current.get("time"),
            "source_type": "current_model_estimate",
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "precipitation_mm": current.get("precipitation"),
            "rain_mm": current.get("rain"),
            "showers_mm": current.get("showers"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "wind_direction_deg": current.get("wind_direction_10m"),
            "surface_pressure_hpa": current.get("surface_pressure"),
        },
        "hourly_observations": rows,
        "hourly_conditions": hourly_conditions,
        "rainfall_windows": rain_windows,
        "source": "Open-Meteo",
        "current_source_type": "current_model_estimate",
        "retrieved_at_utc": datetime.now(dt_timezone.utc).isoformat(),
        "provenance_note": "Open-Meteo current and hourly values are model-based estimates/forecasts, not verified ground-station observations.",
    }


def _at(values, index):
    return values[index] if values is not None and index < len(values) else None


def get_current_weather(latitude, longitude, timezone="Asia/Kolkata"):
    return get_weather_data(latitude, longitude, timezone)["current"]


def get_hourly_rainfall(latitude, longitude, timezone="Asia/Kolkata"):
    return get_weather_data(latitude, longitude, timezone)["hourly_observations"]
