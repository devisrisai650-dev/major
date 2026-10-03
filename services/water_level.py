from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "water_level"
TIME_COL = "Data Acquisition Time"
LEVEL_COL = "River Water Level Telemetry Hourly (meter)"
FRESHNESS_HOURS = 6.0
MIN_LEVEL_M = 0.0
MAX_LEVEL_M = 100.0


def _quality_checks(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    quality = {
        "input_rows": int(len(frame)),
        "invalid_timestamp_rows": 0,
        "invalid_level_rows": 0,
        "duplicate_timestamp_rows": 0,
        "range_rejected_rows": 0,
        "spike_rejected_rows": 0,
        "passed_rows": 0,
    }
    frame = frame.copy()
    frame[TIME_COL] = pd.to_datetime(
        frame[TIME_COL], dayfirst=True, errors="coerce", utc=True
    )
    frame[LEVEL_COL] = pd.to_numeric(frame[LEVEL_COL], errors="coerce")

    quality["invalid_timestamp_rows"] = int(frame[TIME_COL].isna().sum())
    quality["invalid_level_rows"] = int(frame[LEVEL_COL].isna().sum())
    frame = frame.dropna(subset=[TIME_COL, LEVEL_COL]).sort_values(TIME_COL)

    duplicate_mask = frame.duplicated(subset=[TIME_COL], keep="last")
    quality["duplicate_timestamp_rows"] = int(duplicate_mask.sum())
    frame = frame.loc[~duplicate_mask].copy()

    range_mask = ~frame[LEVEL_COL].between(MIN_LEVEL_M, MAX_LEVEL_M, inclusive="both")
    quality["range_rejected_rows"] = int(range_mask.sum())
    frame = frame.loc[~range_mask].copy()

    # Robust spike screen: compare each value with a rolling median and MAD.
    # This is a data-quality screen, not an official flood threshold.
    if len(frame) >= 5:
        values = frame[LEVEL_COL]
        rolling_median = values.rolling(5, center=True, min_periods=3).median()
        deviations = (values - rolling_median).abs()
        mad = deviations.rolling(5, center=True, min_periods=3).median()
        spike_mask = (mad > 0) & (deviations > 10 * mad)
        spike_mask = spike_mask.fillna(False)
        quality["spike_rejected_rows"] = int(spike_mask.sum())
        frame = frame.loc[~spike_mask].copy()

    quality["passed_rows"] = int(len(frame))
    return frame, quality


def get_water_level_analysis(region, as_of: datetime | None = None):
    path = DATA_DIR / region["water_level_file"]
    station = region["water_level_station"]
    result = {
        "available": False,
        "station": station,
        "river": region["river"],
        "current_level_m": None,
        "previous_level_m": None,
        "change_m": None,
        "rate_of_change_m_per_hour": None,
        "current_time": None,
        "latest_observed_m": None,
        "is_recent": False,
        "age_hours": None,
        "reason": None,
        "quality": {},
    }
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

        df, quality = _quality_checks(df)
        result["quality"] = quality
        if df.empty:
            result["reason"] = "Station has no observations after data-quality checks"
            return result

        reference = as_of or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)

        latest = df.iloc[-1]
        observed_at = latest[TIME_COL].to_pydatetime()
        age_hours = max(0.0, (reference - observed_at).total_seconds() / 3600)
        is_recent = age_hours <= FRESHNESS_HOURS

        result.update({
            "available": is_recent,
            "current_level_m": float(latest[LEVEL_COL]) if is_recent else None,
            "latest_observed_m": float(latest[LEVEL_COL]),
            "current_time": latest[TIME_COL].isoformat(),
            "age_hours": age_hours,
            "is_recent": is_recent,
        })

        if not is_recent:
            result["reason"] = (
                f"Latest QC-passed observation is stale ({age_hours:.1f} hours old); "
                "excluded from current assessment"
            )

        if len(df) >= 2 and is_recent:
            prev = df.iloc[-2]
            dt = (latest[TIME_COL] - prev[TIME_COL]).total_seconds() / 3600
            if dt > 0:
                change = float(latest[LEVEL_COL] - prev[LEVEL_COL])
                result.update({
                    "previous_level_m": float(prev[LEVEL_COL]),
                    "change_m": change,
                    "rate_of_change_m_per_hour": change / dt,
                })
            else:
                result["reason"] = "Cannot calculate rate from non-increasing timestamps"

        return result
    except Exception as exc:
        result["reason"] = f"Could not read station data: {exc}"
        return result


def load_station_data(region):
    frame = pd.read_csv(DATA_DIR / region["water_level_file"])
    return frame[frame["Station"].astype(str).str.strip() == region["water_level_station"]].copy()
