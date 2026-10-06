"""Generate and train the synthetic Rician-K predictor used by FloodAI.
The target is Rician K in dB. The dataset is synthetic and not field calibrated.
"""
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
DATA.mkdir(exist_ok=True)
MODELS.mkdir(exist_ok=True)
FEATURES = ["water_depth", "los_obstruction", "debris_density", "flow_velocity", "reflection_dominance"]
SEED = 42
N = 10000

def main():
    rng = np.random.default_rng(SEED)
    water = rng.uniform(0, 2, N)
    los = rng.uniform(0, 1, N)
    debris = rng.uniform(0, 1, N)
    flow = rng.uniform(0, 2, N)
    reflection = rng.uniform(0.5, 2.5, N)
    # Synthetic positive linear-domain K relationship; convert to dB without a floor.
    k_linear = (
        15.0
        * np.exp(-1.35 * water - 2.1 * los - 1.4 * debris - 0.7 * flow)
        * (1.0 + 0.18 * (reflection - 1.0))
        + 0.05
    )
    k_linear *= np.exp(rng.normal(0, 0.055, N))
    k_db = 10.0 * np.log10(k_linear)
    frame = pd.DataFrame({
        "water_depth": water, "los_obstruction": los,
        "debris_density": debris, "flow_velocity": flow,
        "reflection_dominance": reflection, "rician_k_db": k_db,
    })
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
    print(f"Model: {model_path}")
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    main()
