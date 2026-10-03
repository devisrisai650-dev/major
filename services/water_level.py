from pathlib import Path
from datetime import datetime
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "water_level"
TIME_COL = "Data Acquisition Time"
LEVEL_COL = "River Water Level Telemetry Hourly (meter)"

def get_water_level_analysis(region):
    path = DATA_DIR / region["water_level_file"]
    station = region["water_level_station"]
    result = {"available": False, "station": station, "river": region["river"],
              "current_level_m": None, "previous_level_m": None,
              "change_m": None, "rate_of_change_m_per_hour": None,
              "current_time": None, "latest_observed_m": None, "is_recent": False, "age_hours": None, "reason": None}
    if not path.exists():
        result["reason"] = f"Configured station file not found: {path.name}"
        return result
    try:
        df = pd.read_csv(path)
        required = {"Station", TIME_COL, LEVEL_COL}
        if not required.issubset(df.columns):
            result["reason"] = "Station file is missing required columns"
            return result
        df = df[df["Station"].astype(str).str.strip().eq(station)].copy()
        if df.empty:
            result["reason"] = "Configured station has no rows in its file"
            return result
        df[TIME_COL] = pd.to_datetime(df[TIME_COL], dayfirst=True, errors="coerce")
        df[LEVEL_COL] = pd.to_numeric(df[LEVEL_COL], errors="coerce")
        df = df.dropna(subset=[TIME_COL, LEVEL_COL]).sort_values(TIME_COL)
        if df.empty:
            result["reason"] = "Station has no valid level/time observations"
            return result
        latest = df.iloc[-1]
        observed_at = latest[TIME_COL].to_pydatetime()
        age_hours = max(0.0, (datetime.now() - observed_at).total_seconds() / 3600)
        is_recent = age_hours <= 6
        result.update({"available": is_recent,
                       "current_level_m": float(latest[LEVEL_COL]) if is_recent else None,
                       "latest_observed_m": float(latest[LEVEL_COL]),
                       "current_time": latest[TIME_COL].isoformat(),
                       "age_hours": age_hours,
                       "is_recent": is_recent})
        if not is_recent:
            result["reason"] = f"Latest configured-file observation is stale ({age_hours:.1f} hours old); excluded from live assessment"
        if len(df) >= 2 and is_recent:
            prev = df.iloc[-2]
            dt = (latest[TIME_COL] - prev[TIME_COL]).total_seconds() / 3600
            if dt > 0:
                change = float(latest[LEVEL_COL] - prev[LEVEL_COL])
                result.update({"previous_level_m": float(prev[LEVEL_COL]),
                               "change_m": change, "rate_of_change_m_per_hour": change / dt})
        return result
    except Exception as exc:
        result["reason"] = f"Could not read station data: {exc}"
        return result

def load_station_data(region):
    frame = pd.read_csv(DATA_DIR / region["water_level_file"])
    return frame[frame["Station"].astype(str).str.strip() == region["water_level_station"]].copy()
