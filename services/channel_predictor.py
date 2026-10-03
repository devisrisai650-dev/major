from pathlib import Path
import math
import pandas as pd
from xgboost import XGBRegressor

BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_PATH = BASE_DIR / "models" / "xgboost_rician_model.json"
FEATURE_COLUMNS = ["water_depth", "los_obstruction", "debris_density", "flow_velocity", "reflection_dominance"]
_model = None
CONDITION_BANDS = [
    {"condition": "GOOD", "minimum_k": 10.0, "maximum_k_exclusive": None},
    {"condition": "MODERATE", "minimum_k": 5.0, "maximum_k_exclusive": 10.0},
    {"condition": "POOR", "minimum_k": 2.0, "maximum_k_exclusive": 5.0},
    {"condition": "SEVERE", "minimum_k": None, "maximum_k_exclusive": 2.0},
]

def classify_channel(rician_k):
    if rician_k >= 10:
        return "GOOD"
    if rician_k >= 5:
        return "MODERATE"
    if rician_k >= 2:
        return "POOR"
    return "SEVERE"

def evaluate_condition_bands(rician_k=None):
    if rician_k is None:
        return [{"condition": band["condition"], "status": "NOT_EVALUATED",
                 "rule": _band_rule(band)} for band in CONDITION_BANDS]
    active = classify_channel(rician_k)
    return [{"condition": band["condition"],
             "status": "CURRENT_BAND" if band["condition"] == active else "NOT_CURRENT_BAND",
             "rule": _band_rule(band)} for band in CONDITION_BANDS]

def _band_rule(band):
    if band["condition"] == "GOOD":
        return "Rician K >= 10"
    if band["condition"] == "MODERATE":
        return "5 <= Rician K < 10"
    if band["condition"] == "POOR":
        return "2 <= Rician K < 5"
    return "Rician K < 2"

def load_channel_model():
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Channel model not found: {MODEL_PATH}. Train with python train_channel_model.py")
        _model = XGBRegressor()
        _model.load_model(str(MODEL_PATH))
    return _model

def predict_channel(water_depth, los_obstruction, debris_density, flow_velocity, reflection_dominance):
    values = [water_depth, los_obstruction, debris_density, flow_velocity, reflection_dominance]
    if any(value is None for value in values):
        return {"available": False, "rician_k": None, "channel_condition": None,
                "condition_bands": evaluate_condition_bands(),
                "link_availability": "UNVERIFIED",
                "reason": "One or more required measured channel features are unavailable."}
    try:
        values = [float(value) for value in values]
    except (TypeError, ValueError):
        return {"available": False, "rician_k": None, "channel_condition": None,
                "condition_bands": evaluate_condition_bands(),
                "link_availability": "UNVERIFIED", "reason": "Channel inputs must be numeric."}
    if not all(math.isfinite(value) for value in values):
        return {"available": False, "rician_k": None, "channel_condition": None,
                "condition_bands": evaluate_condition_bands(),
                "link_availability": "UNVERIFIED", "reason": "Channel inputs must be finite numbers."}
    frame = pd.DataFrame([dict(zip(FEATURE_COLUMNS, values))])
    k = float(load_channel_model().predict(frame)[0])
    return {"available": True, "rician_k": k, "channel_condition": classify_channel(k),
            "condition_bands": evaluate_condition_bands(k),
            "link_availability": "UNVERIFIED",
            "features": dict(zip(FEATURE_COLUMNS, values)),
            "model_note": "Condition bands are simple K-factor thresholds. Model trained on synthetic data; result is not field-calibrated and does not establish radio-link availability."}
