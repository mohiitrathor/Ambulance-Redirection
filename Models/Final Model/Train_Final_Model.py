import pandas as pd
import joblib

from pathlib import Path

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.linear_model import LogisticRegression


# ============================================================
# SETTINGS
# ============================================================

RANDOM_STATE = 42

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATA_PATH = (
    BASE_DIR
    / "Dataset"
    / "patient_incidents.csv"
)

MODEL_DIR = (
    BASE_DIR
    / "Models"
    / "Final_Model"
)

MODEL_PATH = (
    MODEL_DIR
    / "logistic_regression_final.joblib"
)


# ============================================================
# 1. LOAD DATASET
# ============================================================

print("=" * 70)
print("EMERGENCY AMBULANCE SYSTEM - FINAL MODEL TRAINING")
print("=" * 70)

print("\nLoading dataset...")

df = pd.read_csv(DATA_PATH)

print(
    f"Dataset shape: {df.shape}"
)


# ============================================================
# 2. DEFINE TARGET
# ============================================================

TARGET = "Severity"

y = df[TARGET]


# ============================================================
# 3. REMOVE IRRELEVANT / LEAKAGE COLUMNS
# ============================================================

DROP_COLUMNS = [
    "Incident_ID",
    "Patient_Lat",
    "Patient_Lon",
    "Clinical_Score",
    "Ambulance_Priority",
    "Severity"
]

X = df.drop(
    columns=DROP_COLUMNS
)


# ============================================================
# 4. DISPLAY FEATURES
# ============================================================

print("\n" + "=" * 70)
print("FEATURE INFORMATION")
print("=" * 70)

print(
    f"Total features: {X.shape[1]}"
)

for feature in X.columns:
    print(f"  - {feature}")


# ============================================================
# 5. IDENTIFY FEATURE TYPES
# ============================================================

categorical_features = X.select_dtypes(
    include=["object", "category"]
).columns.tolist()

numeric_features = X.select_dtypes(
    include=[
        "int64",
        "float64",
        "int32",
        "float32"
    ]
).columns.tolist()


print("\nNumeric features:", len(numeric_features))
print("Categorical features:", len(categorical_features))


# ============================================================
# 6. TARGET DISTRIBUTION
# ============================================================

print("\n" + "=" * 70)
print("TARGET DISTRIBUTION")
print("=" * 70)

target_distribution = (
    y.value_counts()
    .to_frame("Count")
)

target_distribution["Percentage"] = (
    target_distribution["Count"]
    / len(y)
    * 100
)

print(
    target_distribution.round(2)
)


# ============================================================
# 7. PREPROCESSING
# ============================================================

preprocessor = ColumnTransformer(
    transformers=[

        (
            "categorical",
            OneHotEncoder(
                handle_unknown="ignore"
            ),
            categorical_features
        ),

        (
            "numeric",
            StandardScaler(),
            numeric_features
        )
    ]
)


# ============================================================
# 8. FINAL LOGISTIC REGRESSION
# ============================================================

model = Pipeline(
    steps=[

        (
            "preprocessor",
            preprocessor
        ),

        (
            "classifier",
            LogisticRegression(
                C=1,
                class_weight="balanced",
                solver="lbfgs",
                max_iter=100000,
                random_state=RANDOM_STATE
            )
        )
    ]
)


# ============================================================
# 9. TRAIN FINAL MODEL
# ============================================================

print("\n" + "=" * 70)
print("TRAINING FINAL LOGISTIC REGRESSION")
print("=" * 70)

print("\nTraining on complete dataset...")

model.fit(
    X,
    y
)

print("Training complete.")


# ============================================================
# 10. CREATE MODEL DIRECTORY
# ============================================================

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# 11. SAVE MODEL
# ============================================================

print("\n" + "=" * 70)
print("SAVING MODEL")
print("=" * 70)

joblib.dump(
    model,
    MODEL_PATH
)

print(
    f"\nModel saved to:\n{MODEL_PATH}"
)


# ============================================================
# 12. VERIFY SAVED MODEL
# ============================================================

print("\n" + "=" * 70)
print("MODEL VERIFICATION")
print("=" * 70)

loaded_model = joblib.load(
    MODEL_PATH
)

print(
    "\nModel successfully loaded."
)

print(
    "Model classes:"
)

print(
    loaded_model
    .named_steps["classifier"]
    .classes_
)


# ============================================================
# 13. FINAL SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("FINAL MODEL TRAINING COMPLETE")
print("=" * 70)

print(
    f"\nTraining samples: {len(X):,}"
)

print(
    f"Input features:   {X.shape[1]}"
)

print(
    "Model:             Logistic Regression"
)

print(
    "C:                 1"
)

print(
    "Class weight:      balanced"
)

print(
    "Solver:            lbfgs"
)

print(
    f"\nSaved model:\n{MODEL_PATH}"
)