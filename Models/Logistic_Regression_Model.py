import pandas as pd

from pathlib import Path

from sklearn.preprocessing import StandardScaler
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
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression


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
print("EMERGENCY AMBULANCE SYSTEM - SEVERITY MODEL")
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
#   Location should not influence the initial clinical
#   severity model.
#
# Clinical_Score:
#   Synthetic rule-based reference score. It summarizes
#   clinical severity and would make the model learn the
#   predefined scoring system instead of the raw features.
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
    target_distribution
    .round(2)
)


# ============================================================
# 6. IDENTIFY FEATURE TYPES
# ============================================================

categorical_features = X.select_dtypes(
    include=["object", "category"]
).columns.tolist()

numeric_features = X.select_dtypes(
    include=["int64", "float64", "int32", "float32"]
).columns.tolist()


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
# 7. TRAIN / TEST SPLIT
# ============================================================
#
# Stratification preserves the severity distribution in both
# training and testing sets.
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
# 8. PREPROCESSING
# ============================================================
#
# Numeric features:
#   Passed through unchanged for Logistic Regression.
#
# Categorical features:
#   One-hot encoded.
#
# handle_unknown="ignore" prevents errors if the test set
# contains a category not seen during training.
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
# 9. BASELINE MODEL
# ============================================================
#
# DummyClassifier predicts according to the class distribution.
#
# This establishes the minimum performance our real model
# should beat.
# ============================================================

dummy_model = Pipeline(
    steps=[
        (
            "preprocessor",
            preprocessor
        ),

        (
            "classifier",
            DummyClassifier(
                strategy="most_frequent"
            )
        )
    ]
)


print("\n" + "=" * 70)
print("BASELINE MODEL")
print("=" * 70)

print("\nTraining DummyClassifier...")

dummy_model.fit(
    X_train,
    y_train
)

dummy_predictions = dummy_model.predict(
    X_test
)


dummy_accuracy = accuracy_score(
    y_test,
    dummy_predictions
)

dummy_balanced_accuracy = balanced_accuracy_score(
    y_test,
    dummy_predictions
)

print(
    f"Accuracy:          {dummy_accuracy:.4f}"
)

print(
    f"Balanced Accuracy: {dummy_balanced_accuracy:.4f}"
)


# ============================================================
# 10. LOGISTIC REGRESSION
# ============================================================
#
# This is our first actual ML model.
#
# We are intentionally starting with a simple interpretable
# multiclass classifier.
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
                max_iter=100000,
                random_state=RANDOM_STATE
            )
        )
    ]
)


print("\n" + "=" * 70)
print("LOGISTIC REGRESSION")
print("=" * 70)

print("\nTraining model...")

model.fit(
    X_train,
    y_train
)


# ============================================================
# 11. PREDICTIONS
# ============================================================

print(
    "Generating predictions..."
)

y_pred = model.predict(
    X_test
)


# ============================================================
# 12. EVALUATION
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
# 13. CLASSIFICATION REPORT
# ============================================================

print("\n" + "=" * 70)
print("CLASSIFICATION REPORT")
print("=" * 70)

print(
    classification_report(
        y_test,
        y_pred,
        digits=4
    )
)


# ============================================================
# 14. CONFUSION MATRIX
# ============================================================

print("\n" + "=" * 70)
print("CONFUSION MATRIX")
print("=" * 70)

labels = [
    "Non-Urgent",
    "Low",
    "Moderate",
    "Emergency",
    "Critical"
]

cm = confusion_matrix(
    y_test,
    y_pred,
    labels=labels
)

cm_df = pd.DataFrame(
    cm,
    index=labels,
    columns=labels
)

print(
    cm_df
)


# ============================================================
# 15. SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(
    f"Baseline accuracy:  {dummy_accuracy:.4f}"
)

print(
    f"Model accuracy:     {accuracy:.4f}"
)

print(
    f"Baseline balanced:  {dummy_balanced_accuracy:.4f}"
)

print(
    f"Model balanced:     {balanced_accuracy:.4f}"
)

print("\n✓ Severity baseline complete.")