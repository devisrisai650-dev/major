# ============================================================
# FLOOD AI - CHANNEL PREDICTION MODEL TRAINING
# ============================================================
#
# Purpose:
#   Train an XGBoost model to predict the Rician K-factor
#   from flood/environmental conditions.
#
# Inputs:
#   1. Water depth
#   2. LOS obstruction
#   3. Debris density
#   4. Flow velocity
#   5. Reflection dominance
#
# Output:
#   Predicted Rician K-factor
#
# Files generated:
#
#   models/
#       xgboost_rician_model.json
#
#   data/
#       channel_training_data.csv
#
# ============================================================


from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

from xgboost import XGBRegressor


# ============================================================
# 1. PROJECT DIRECTORIES
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

MODEL_DIR = BASE_DIR / "models"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)


DATASET_PATH = (
    DATA_DIR /
    "channel_training_data.csv"
)

MODEL_PATH = (
    MODEL_DIR /
    "xgboost_rician_model.json"
)


# ============================================================
# 2. CONFIGURATION
# ============================================================

RANDOM_SEED = 42

NUMBER_OF_SAMPLES = 10000


# ============================================================
# 3. RANDOM NUMBER GENERATOR
# ============================================================

rng = np.random.default_rng(
    RANDOM_SEED
)


# ============================================================
# 4. GENERATE ENVIRONMENTAL FEATURES
# ============================================================

print("\n============================================")
print("       FLOOD AI CHANNEL MODEL TRAINING")
print("============================================")

print(
    f"\nGenerating "
    f"{NUMBER_OF_SAMPLES} synthetic samples..."
)


# ------------------------------------------------------------
# Water depth
# Range: 0 - 2 metres
# ------------------------------------------------------------

water_depth = rng.uniform(
    0.0,
    2.0,
    NUMBER_OF_SAMPLES
)


# ------------------------------------------------------------
# LOS obstruction
# Range: 0 - 1
#
# 0 = clear line of sight
# 1 = heavily obstructed
# ------------------------------------------------------------

los_obstruction = rng.uniform(
    0.0,
    1.0,
    NUMBER_OF_SAMPLES
)


# ------------------------------------------------------------
# Debris density
# Range: 0 - 1
#
# 0 = very low debris
# 1 = severe debris
# ------------------------------------------------------------

debris_density = rng.uniform(
    0.0,
    1.0,
    NUMBER_OF_SAMPLES
)


# ------------------------------------------------------------
# Flow velocity
# Range: 0 - 2 m/s
# ------------------------------------------------------------

flow_velocity = rng.uniform(
    0.0,
    2.0,
    NUMBER_OF_SAMPLES
)


# ------------------------------------------------------------
# Reflection dominance ratio
# Range: 0.5 - 2.5
# ------------------------------------------------------------

reflection_dominance = rng.uniform(
    0.5,
    2.5,
    NUMBER_OF_SAMPLES
)


# ============================================================
# 5. PHYSICS-INSPIRED RICIAN K-FACTOR
# ============================================================
#
# The Rician K-factor represents the relative strength of the
# dominant LOS component compared with the scattered component.
#
# In this synthetic simulation:
#
#   Higher LOS obstruction
#       -> lower K-factor
#
#   Higher debris
#       -> lower K-factor
#
#   Higher flow velocity
#       -> more dynamic scattering
#       -> lower K-factor
#
#   Higher reflection dominance
#       -> stronger reflected component
#       -> lower effective LOS dominance
#
#   Water depth
#       -> used as an environmental disturbance factor
#
# This is a synthetic physics-inspired target generation
# mechanism for simulation. It is NOT field-calibrated data.
# ============================================================


# Base channel quality
base_k = 12.0


# Water-depth effect
water_effect = (
    2.0 *
    water_depth
)


# LOS obstruction effect
los_effect = (
    8.0 *
    los_obstruction
)


# Debris effect
debris_effect = (
    5.0 *
    debris_density
)


# Flow velocity effect
flow_effect = (
    2.5 *
    flow_velocity
)


# Reflection effect
reflection_effect = (
    1.5 *
    (reflection_dominance - 0.5)
)


# Combine environmental effects
rician_k = (
    base_k
    - water_effect
    - los_effect
    - debris_effect
    - flow_effect
    - reflection_effect
)


# ============================================================
# 6. ADD REALISTIC NONLINEARITY
# ============================================================
#
# Real wireless channels are not perfectly linear.
#
# We therefore introduce nonlinear interactions between
# environmental parameters.
# ============================================================


interaction_effect = (
    2.0
    * los_obstruction
    * debris_density
)


dynamic_effect = (
    1.5
    * flow_velocity
    * debris_density
)


reflection_interaction = (
    0.8
    * los_obstruction
    * reflection_dominance
)


rician_k = (
    rician_k
    - interaction_effect
    - dynamic_effect
    - reflection_interaction
)


# ============================================================
# 7. ADD SMALL RANDOM NOISE
# ============================================================

noise = rng.normal(
    loc=0.0,
    scale=0.25,
    size=NUMBER_OF_SAMPLES
)


rician_k = (
    rician_k
    + noise
)


# ============================================================
# 8. KEEP K-FACTOR PHYSICALLY NON-NEGATIVE
# ============================================================

rician_k = np.clip(
    rician_k,
    0.05,
    None
)


# ============================================================
# 9. CREATE DATAFRAME
# ============================================================

dataset = pd.DataFrame({

    "water_depth":
        water_depth,

    "los_obstruction":
        los_obstruction,

    "debris_density":
        debris_density,

    "flow_velocity":
        flow_velocity,

    "reflection_dominance":
        reflection_dominance,

    "rician_k":
        rician_k

})


# ============================================================
# 10. SAVE DATASET
# ============================================================

dataset.to_csv(
    DATASET_PATH,
    index=False
)


print(
    f"\nDataset saved to:"
)

print(
    DATASET_PATH
)


# ============================================================
# 11. DISPLAY DATASET INFORMATION
# ============================================================

print("\n============================================")
print("             DATASET INFORMATION")
print("============================================")


print(
    f"Samples : "
    f"{len(dataset)}"
)

print(
    f"Features: "
    f"5"
)

print(
    f"Target  : "
    f"Rician K-factor"
)


print("\nFirst 5 samples:")

print(
    dataset.head()
)


# ============================================================
# 12. DEFINE FEATURES AND TARGET
# ============================================================

FEATURE_COLUMNS = [

    "water_depth",

    "los_obstruction",

    "debris_density",

    "flow_velocity",

    "reflection_dominance"

]


TARGET_COLUMN = (
    "rician_k"
)


X = dataset[
    FEATURE_COLUMNS
]

y = dataset[
    TARGET_COLUMN
]


# ============================================================
# 13. TRAIN / TEST SPLIT
# ============================================================

X_train, X_test, y_train, y_test = (
    train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=RANDOM_SEED
    )
)


print("\n============================================")
print("              DATA SPLIT")
print("============================================")


print(
    f"Training samples : "
    f"{len(X_train)}"
)

print(
    f"Testing samples  : "
    f"{len(X_test)}"
)


# ============================================================
# 14. CREATE XGBOOST MODEL
# ============================================================

print("\n============================================")
print("          TRAINING XGBOOST MODEL")
print("============================================")


model = XGBRegressor(

    n_estimators=300,

    max_depth=6,

    learning_rate=0.05,

    subsample=0.8,

    colsample_bytree=0.8,

    objective="reg:squarederror",

    random_state=RANDOM_SEED,

    n_jobs=-1
)


# ============================================================
# 15. TRAIN MODEL
# ============================================================

model.fit(
    X_train,
    y_train
)


print(
    "\nXGBoost training completed."
)


# ============================================================
# 16. PREDICTIONS
# ============================================================

y_pred = model.predict(
    X_test
)


# ============================================================
# 17. CALCULATE PERFORMANCE METRICS
# ============================================================

mae = mean_absolute_error(
    y_test,
    y_pred
)


rmse = np.sqrt(
    mean_squared_error(
        y_test,
        y_pred
    )
)


r2 = r2_score(
    y_test,
    y_pred
)


# ============================================================
# 18. DISPLAY PERFORMANCE
# ============================================================

print("\n============================================")
print("          MODEL PERFORMANCE")
print("============================================")


print(
    f"MAE  : {mae:.6f}"
)

print(
    f"RMSE : {rmse:.6f}"
)

print(
    f"R²   : {r2:.6f}"
)


# ============================================================
# 19. FEATURE IMPORTANCE
# ============================================================

print("\n============================================")
print("            FEATURE IMPORTANCE")
print("============================================")


feature_importance = pd.DataFrame({

    "feature":
        FEATURE_COLUMNS,

    "importance":
        model.feature_importances_

})


feature_importance = (
    feature_importance
    .sort_values(
        by="importance",
        ascending=False
    )
)


for _, row in (
    feature_importance.iterrows()
):

    print(
        f"{row['feature']:<25}"
        f": {row['importance']:.6f}"
    )


# ============================================================
# 20. SAVE XGBOOST MODEL
# ============================================================

model.save_model(
    str(MODEL_PATH)
)


print("\n============================================")
print("             MODEL SAVED")
print("============================================")


print(
    "\nModel saved to:"
)

print(
    MODEL_PATH
)


# ============================================================
# 21. VERIFY MODEL FILE
# ============================================================

if MODEL_PATH.exists():

    print(
        "\n✓ xgboost_rician_model.json "
        "created successfully."
    )

else:

    print(
        "\n✗ Model file was not created."
    )


# ============================================================
# 22. TEST A SAMPLE PREDICTION
# ============================================================

print("\n============================================")
print("          SAMPLE PREDICTION")
print("============================================")


sample = pd.DataFrame({

    "water_depth": [1.2],

    "los_obstruction": [0.35],

    "debris_density": [0.25],

    "flow_velocity": [1.0],

    "reflection_dominance": [1.4]

})


sample_prediction = model.predict(
    sample
)


print(
    "\nSample environmental conditions:"
)


print(
    sample.to_string(
        index=False
    )
)


print(
    f"\nPredicted Rician K-factor: "
    f"{sample_prediction[0]:.4f}"
)


print("\n============================================")
print("              TRAINING COMPLETE")
print("============================================")

print(
    "\nYou can now run:"
)

print(
    "python main.py"
)

print(
    "\nThe main application should now "
    "load the trained channel model."
)