import pandas as pd

from pathlib import Path

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix
)

from xgboost import XGBClassifier


# ============================================================
# SETTINGS
# ============================================================

RANDOM_STATE = 42

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_PATH = (
    BASE_DIR
    / "Dataset"
    / "patient_incidents.csv"
)


# ============================================================
# 1. LOAD DATA
# ============================================================

print("=" * 70)
print("EMERGENCY AMBULANCE SYSTEM - XGBOOST")
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
#
# Incident_ID:
#   Identifier only.
#
# Patient_Lat / Patient_Lon:
#   Location should not determine clinical severity.
#
# Clinical_Score:
#   Synthetic rule-based reference score derived from
#   clinical features. Including it would introduce leakage.
#
# Ambulance_Priority:
#   Directly derived from Severity.
#
# Severity:
#   Target variable.
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

print("\nFeatures used by the model:")

for feature in X.columns:
    print(
        f"  - {feature}"
    )

print(
    f"\nTotal features: {X.shape[1]}"
)


# ============================================================
# 5. TARGET DISTRIBUTION
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
# 6. CONVERT TARGET TO NUMERIC LABELS
# ============================================================
#
# XGBoost requires numerical class labels.
#
# 0 = Non-Urgent
# 1 = Low
# 2 = Moderate
# 3 = Emergency
# 4 = Critical
# ============================================================

severity_mapping = {
    "Non-Urgent": 0,
    "Low": 1,
    "Moderate": 2,
    "Emergency": 3,
    "Critical": 4
}

y = y.map(
    severity_mapping
)


# ============================================================
# 7. IDENTIFY FEATURE TYPES
# ============================================================

categorical_features = (
    X.select_dtypes(
        include=[
            "object",
            "category"
        ]
    )
    .columns
    .tolist()
)

numeric_features = (
    X.select_dtypes(
        include=[
            "int64",
            "float64",
            "int32",
            "float32"
        ]
    )
    .columns
    .tolist()
)


print("\n" + "=" * 70)
print("FEATURE TYPES")
print("=" * 70)

print(
    f"Numeric features: {len(numeric_features)}"
)

print(
    f"Categorical features: {len(categorical_features)}"
)


# ============================================================
# 8. TRAIN / TEST SPLIT
# ============================================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=RANDOM_STATE,
    stratify=y
)


print("\n" + "=" * 70)
print("TRAIN / TEST SPLIT")
print("=" * 70)

print(
    f"Training samples: {len(X_train):,}"
)

print(
    f"Testing samples:  {len(X_test):,}"
)


# ============================================================
# 9. PREPROCESSING
# ============================================================
#
# XGBoost does not require feature scaling.
#
# Numerical features:
#   Passed through unchanged.
#
# Categorical features:
#   One-hot encoded.
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

            "passthrough",

            numeric_features
        )
    ]
)


# ============================================================
# 10. XGBOOST MODEL
# ============================================================

model = Pipeline(
    steps=[

        (
            "preprocessor",
            preprocessor
        ),

        (
            "classifier",

            XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,

                objective="multi:softmax",
                num_class=5,

                eval_metric="mlogloss",

                random_state=RANDOM_STATE,
                n_jobs=-1
            )
        )
    ]
)


# ============================================================
# 11. TRAIN MODEL
# ============================================================

print("\n" + "=" * 70)
print("TRAINING XGBOOST")
print("=" * 70)

print("\nTraining model...")

model.fit(
    X_train,
    y_train
)

print(
    "Training complete."
)


# ============================================================
# 12. MAKE PREDICTIONS
# ============================================================

print("\nGenerating predictions...")

y_pred = model.predict(
    X_test
)


# ============================================================
# 13. EVALUATION
# ============================================================

accuracy = accuracy_score(
    y_test,
    y_pred
)

balanced_accuracy = balanced_accuracy_score(
    y_test,
    y_pred
)


print("\n" + "=" * 70)
print("MODEL PERFORMANCE")
print("=" * 70)

print(
    f"\nAccuracy:          {accuracy:.4f}"
)

print(
    f"Balanced Accuracy: {balanced_accuracy:.4f}"
)


# ============================================================
# 14. CLASSIFICATION REPORT
# ============================================================

labels = [
    "Non-Urgent",
    "Low",
    "Moderate",
    "Emergency",
    "Critical"
]

numeric_labels = [
    0,
    1,
    2,
    3,
    4
]

print("\n" + "=" * 70)
print("CLASSIFICATION REPORT")
print("=" * 70)

print(
    classification_report(
        y_test,
        y_pred,
        labels=numeric_labels,
        target_names=labels,
        digits=4
    )
)


# ============================================================
# 15. CONFUSION MATRIX
# ============================================================

cm = confusion_matrix(
    y_test,
    y_pred,
    labels=numeric_labels
)

cm_df = pd.DataFrame(
    cm,
    index=labels,
    columns=labels
)


print("\n" + "=" * 70)
print("CONFUSION MATRIX")
print("=" * 70)

print(
    cm_df
)


# ============================================================
# 16. SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(
    f"Accuracy:          {accuracy:.4f}"
)

print(
    f"Balanced Accuracy: {balanced_accuracy:.4f}"
)

print(
    "\nXGBoost training and evaluation complete."
)