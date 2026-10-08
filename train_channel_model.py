"""Train the synthetic Rician K-factor model with named reproducible scenarios."""
from __future__ import annotations

import argparse
from pathlib import Path
import json

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
MODELS = BASE / "models"
FEATURES = [
    "water_depth", "los_obstruction", "debris_density",
    "flow_velocity", "reflection_dominance",
]
SCENARIOS = {
    "baseline": {
        "water_depth": (0.0, 2.0),
        "los_obstruction": (0.0, 1.0),
        "debris_density": (0.0, 1.0),
        "flow_velocity": (0.0, 2.0),
        "reflection_dominance": (0.5, 2.5),
    },
    "urban_flood": {
        "water_depth": (0.0, 2.0),
        "los_obstruction": (0.2, 1.0),
        "debris_density": (0.1, 1.0),
        "flow_velocity": (0.0, 2.0),
        "reflection_dominance": (0.6, 2.5),
    },
    "coastal_flood": {
        "water_depth": (0.2, 2.0),
        "los_obstruction": (0.0, 0.8),
        "debris_density": (0.0, 0.8),
        "flow_velocity": (0.0, 2.0),
        "reflection_dominance": (0.5, 2.5),
    },
}
SEED = 42
N = 10000


def main():
    parser = argparse.ArgumentParser(description="Train synthetic Rician K-factor model")
    parser.add_argument("--scenario", choices=SCENARIOS, default="baseline")
    args = parser.parse_args()

    rng = np.random.default_rng(SEED)
    bounds = SCENARIOS[args.scenario]
    samples = {
        feature: rng.uniform(low, high, N)
        for feature, (low, high) in bounds.items()
    }
    water = samples["water_depth"]
    los = samples["los_obstruction"]
    debris = samples["debris_density"]
    flow = samples["flow_velocity"]
    reflection = samples["reflection_dominance"]
    k_linear = (
        15.0
        * np.exp(-1.35 * water - 2.1 * los - 1.4 * debris - 0.7 * flow)
        * (1.0 + 0.18 * (reflection - 1.0))
        + 0.05
    )
    k_linear *= np.exp(rng.normal(0, 0.055, N))
    k_db = 10.0 * np.log10(k_linear)
    frame = pd.DataFrame({**samples, "rician_k_db": k_db})
    DATA.mkdir(exist_ok=True)
    MODELS.mkdir(exist_ok=True)
    path = DATA / "channel_training_data_v2.csv"
    frame.to_csv(path, index=False)
    X_train, X_test, y_train, y_test = train_test_split(
        frame[FEATURES], frame["rician_k_db"], test_size=0.2, random_state=SEED
    )
    model = XGBRegressor(
        n_estimators=350, max_depth=6, learning_rate=0.05,
        subsample=0.85, colsample_bytree=0.85, objective="reg:squarederror",
        random_state=SEED, n_jobs=-1,
    )
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    metrics = {
        "dataset": "synthetic",
        "target": "Rician K-factor (dB)",
        "scenario": args.scenario,
        "samples": N,
        "mae_db": float(mean_absolute_error(y_test, pred)),
        "rmse_db": float(np.sqrt(mean_squared_error(y_test, pred))),
        "r2": float(r2_score(y_test, pred)),
        "clipped_target_fraction": 0.0,
        "field_calibrated": False,
        "features": FEATURES,
        "seed": SEED,
        "documented_bands_db": {
            "GOOD": "K >= 10 dB",
            "MODERATE": "5 <= K < 10 dB",
            "POOR": "2 <= K < 5 dB",
            "SEVERE": "K < 2 dB",
        },
    }
    model_path = MODELS / "xgboost_rician_model_v2.json"
    model.save_model(str(model_path))
    (MODELS / "xgboost_rician_model_v2_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    print("Synthetic channel model v2 trained.")
    print(f"Scenario: {args.scenario}")
    print(f"Model: {model_path}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
