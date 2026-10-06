import requests

BASE_URL = "https://flood-api.open-meteo.com/v1/flood"


def get_flood_data(latitude, longitude):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "river_discharge,river_discharge_mean,river_discharge_max",
        "forecast_days": 7,
        "timezone": "auto",
    }
    response = requests.get(BASE_URL, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def get_discharge_analysis(latitude, longitude):
    try:
        data = get_flood_data(latitude, longitude)
        daily = data.get("daily", {})
        values = daily.get("river_discharge", [])
        dates = daily.get("time", [])
        valid = [
            (dates[i] if i < len(dates) else None, value)
            for i, value in enumerate(values)
            if value is not None
        ]
        if valid:
            date, value = valid[0]
            return {
                "available": True,
                "discharge_m3s": float(value),
                "time": date,
                "data_type": "modeled_daily_forecast",
                "reason": None,
            }
        return {
            "available": False,
            "discharge_m3s": None,
            "time": None,
            "data_type": "modeled_daily_forecast",
            "reason": "No discharge values returned",
        }
    except (requests.RequestException, ValueError) as exc:
        return {
            "available": False,
            "discharge_m3s": None,
            "time": None,
            "data_type": "modeled_daily_forecast",
            "reason": str(exc),
        }
