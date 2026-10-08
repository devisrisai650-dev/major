"""Rician K-factor predictor with an explicit synthetic-data boundary."""
from __future__ import annotations

import math
import os
from pathlib import Path

import pandas as pd
from xgboost import XGBRegressor

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = BASE_DIR / "models" / "xgboost_rician_model_v2.json"
FEATURE_COLUMNS = [
    "water_depth", "los_obstruction", "debris_density",
    "flow_velocity", "reflection_dominance",
]
CONDITION_BANDS = [
    {"condition": "GOOD", "rule": "K >= 10 dB"},
    {"condition": "MODERATE", "rule": "5 <= K < 10 dB"},
    {"condition": "POOR", "rule": "2 <= K < 5 dB"},
    {"condition": "SEVERE", "rule": "K < 2 dB"},
]
_model = None
_loaded_model_path = None


def get_model_path():
    configured = os.getenv("FLOODAI_CHANNEL_MODEL_PATH")
    return Path(configured) if configured else DEFAULT_MODEL_PATH


def classify_channel(rician_k_db):
    if rician_k_db >= 10:
        return "GOOD"
    if rician_k_db >= 5:
        return "MODERATE"
    if rician_k_db >= 2:
        return "POOR"
    return "SEVERE"


def evaluate_condition_bands(rician_k_db=None):
    if rician_k_db is None:
        return [
            {"condition": b["condition"], "status": "NOT_EVALUATED", "rule": b["rule"]}
            for b in CONDITION_BANDS
        ]
    active = classify_channel(rician_k_db)
    return [
        {
            "condition": b["condition"],
            "status": "CURRENT_BAND" if b["condition"] == active else "NOT_CURRENT_BAND",
            "rule": b["rule"],
        }
        for b in CONDITION_BANDS
    ]


def load_channel_model():
    global _model, _loaded_model_path
    path = get_model_path()
    if _model is None or _loaded_model_path != path:
        if not path.exists():
            raise FileNotFoundError(f"Model unavailable: {path}. Run train_channel_model.py")
        _model = XGBRegressor()
        _model.load_model(str(path))
        _loaded_model_path = path
    return _model


def predict_channel(
    water_depth,
    los_obstruction,
    debris_density,
    flow_velocity,
    reflection_dominance,
    scenario="unavailable_real_measurements",
):
    values = [water_depth, los_obstruction, debris_density, flow_velocity, reflection_dominance]
    if any(value is None for value in values):
        return {
            "available": False,
            "rician_k_db": None,
            "channel_condition": None,
            "condition_bands": evaluate_condition_bands(),
            "link_availability": "UNVERIFIED",
            "model_status": "unavailable_real_measurements",
            "scenario": scenario,
            "reason": "Required measured channel features are unavailable.",
        }
    try:
        values = [float(value) for value in values]
    except (TypeError, ValueError):
        return {
            "available": False,
            "rician_k_db": None,
            "channel_condition": None,
            "condition_bands": evaluate_condition_bands(),
            "link_availability": "UNVERIFIED",
            "model_status": "invalid_inputs",
            "scenario": scenario,
            "reason": "Channel inputs must be numeric.",
        }
    if not all(math.isfinite(value) for value in values):
        return {
            "available": False,
            "rician_k_db": None,
            "channel_condition": None,
            "condition_bands": evaluate_condition_bands(),
            "link_availability": "UNVERIFIED",
            "model_status": "invalid_inputs",
            "scenario": scenario,
            "reason": "Channel inputs must be finite numbers.",
        }
    frame = pd.DataFrame([dict(zip(FEATURE_COLUMNS, values))])
    k_db = float(load_channel_model().predict(frame)[0])
    return {
        "available": True,
        "rician_k_db": k_db,
        "channel_condition": classify_channel(k_db),
        "condition_bands": evaluate_condition_bands(k_db),
        "link_availability": "UNVERIFIED",
        "model_status": "synthetic_model",
        "scenario": scenario,
        "features": dict(zip(FEATURE_COLUMNS, values)),
        "model_path": str(get_model_path()),
        "model_note": (
            "Synthetic-data-trained model. This prediction is not field calibrated "
            "and does not establish real radio-link availability."
        ),
    }
