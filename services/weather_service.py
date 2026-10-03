from datetime import datetime, timedelta
import requests

BASE_URL = "https://api.open-meteo.com/v1/forecast"

def get_weather_data(latitude, longitude, timezone="Asia/Kolkata"):
    params = {
        "latitude": latitude, "longitude": longitude, "timezone": timezone,
        "current": "temperature_2m,relative_humidity_2m,precipitation,rain,showers,wind_speed_10m,wind_direction_10m,surface_pressure",
        "hourly": "precipitation,rain,showers",
        "past_days": 1, "forecast_days": 2
    }
    response = requests.get(BASE_URL, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    now = datetime.fromisoformat(data["current"]["time"])
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    rows = []
    for i, stamp in enumerate(times):
        t = datetime.fromisoformat(stamp)
        if t <= now:
            rows.append({"time": stamp, "rain_mm": _at(hourly.get("rain"), i),
                         "precipitation_mm": _at(hourly.get("precipitation"), i),
                         "showers_mm": _at(hourly.get("showers"), i)})
    rain_windows = {}
    for hours in (1, 3, 6, 24):
        cutoff = now - timedelta(hours=hours)
        window = [r for r in rows if cutoff < datetime.fromisoformat(r["time"]) <= now]
        vals = [r["precipitation_mm"] for r in window if r["precipitation_mm"] is not None]
        rain_windows[f"last_{hours}h_precipitation_mm"] = sum(vals) if len(vals) == hours else None
        rain_windows[f"last_{hours}h_observations"] = len(vals)
    current = data.get("current", {})
    return {"current": {
        "time": current.get("time"),
        "temperature_c": current.get("temperature_2m"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "precipitation_mm": current.get("precipitation"),
        "rain_mm": current.get("rain"), "showers_mm": current.get("showers"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "wind_direction_deg": current.get("wind_direction_10m"),
        "surface_pressure_hpa": current.get("surface_pressure")
    }, "hourly_observations": rows, "rainfall_windows": rain_windows}

def _at(values, index):
    return values[index] if values is not None and index < len(values) else None

def get_current_weather(latitude, longitude, timezone="Asia/Kolkata"):
    return get_weather_data(latitude, longitude, timezone)["current"]

def get_hourly_rainfall(latitude, longitude, timezone="Asia/Kolkata"):
    return get_weather_data(latitude, longitude, timezone)["hourly_observations"]
