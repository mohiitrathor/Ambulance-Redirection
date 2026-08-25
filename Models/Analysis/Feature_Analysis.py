import pandas as pd
import numpy as np

from pathlib import Path

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import (
    StandardScaler,
    OneHotEncoder
)
from sklearn.pipeline import Pipeline
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

OUTPUT_DIR = (
    BASE_DIR
    / "Models"
    / "Reports"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# 1. LOAD DATA
# ============================================================

print("=" * 70)
print("EMERGENCY AMBULANCE SYSTEM - FEATURE ANALYSIS")
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
# 4. IDENTIFY FEATURE TYPES
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


print("\n" + "=" * 70)
print("FEATURE INFORMATION")
print("=" * 70)

print(
    f"Total features:       {X.shape[1]}"
)

print(
    f"Numeric features:     {len(numeric_features)}"
)

print(
    f"Categorical features: {len(categorical_features)}"
)


# ============================================================
# 5. TRAIN / TEST SPLIT
# ============================================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=RANDOM_STATE,
    stratify=y
)


# ============================================================
# 6. PREPROCESSING
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
# 7. TUNED LOGISTIC REGRESSION
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
# 8. TRAIN MODEL
# ============================================================

print("\n" + "=" * 70)
print("TRAINING TUNED LOGISTIC REGRESSION")
print("=" * 70)

print("\nTraining model...")

model.fit(
    X_train,
    y_train
)

print("Training complete.")


# ============================================================
# 9. EXTRACT TRANSFORMED FEATURE NAMES
# ============================================================

print("\nExtracting transformed feature names...")

fitted_preprocessor = model.named_steps[
    "preprocessor"
]

classifier = model.named_steps[
    "classifier"
]

feature_names = (
    fitted_preprocessor
    .get_feature_names_out()
)


# ============================================================
# 10. EXTRACT COEFFICIENTS
# ============================================================

coefficients = classifier.coef_

classes = classifier.classes_


print(
    f"Transformed features: {len(feature_names)}"
)

print(
    f"Classes: {list(classes)}"
)


# ============================================================
# 11. CREATE COEFFICIENT DATAFRAME
# ============================================================

coefficient_df = pd.DataFrame(
    coefficients.T,
    index=feature_names,
    columns=classes
)

coefficient_df.index.name = "Feature"


# ============================================================
# 12. ABSOLUTE IMPORTANCE
# ============================================================
#
# Mean absolute coefficient across all classes.
#
# Larger values indicate that the feature has a stronger
# influence on the model's class predictions.
# ============================================================

coefficient_df["Mean_Absolute_Coefficient"] = (
    coefficient_df
    .abs()
    .mean(axis=1)
)

coefficient_df = (
    coefficient_df
    .sort_values(
        "Mean_Absolute_Coefficient",
        ascending=False
    )
)


# ============================================================
# 13. DISPLAY TOP FEATURES
# ============================================================

print("\n" + "=" * 70)
print("TOP 20 FEATURES BY MEAN ABSOLUTE COEFFICIENT")
print("=" * 70)

print(
    coefficient_df[
        ["Mean_Absolute_Coefficient"]
    ]
    .head(20)
    .round(4)
)


# ============================================================
# 14. CLASS-SPECIFIC TOP FEATURES
# ============================================================

print("\n" + "=" * 70)
print("TOP FEATURES BY SEVERITY CLASS")
print("=" * 70)

class_feature_results = {}

for current_class in classes:

    class_coefficients = (
        coefficient_df[
            current_class
        ]
        .sort_values(
            ascending=False
        )
    )

    positive = (
        class_coefficients
        .head(10)
    )

    negative = (
        class_coefficients
        .sort_values()
        .head(10)
    )

    class_feature_results[
        current_class
    ] = {
        "positive": positive,
        "negative": negative
    }

    print(
        f"\n--- {current_class} ---"
    )

    print("\nStrongest positive features:")

    print(
        positive.round(4)
    )

    print("\nStrongest negative features:")

    print(
        negative.round(4)
    )


# ============================================================
# 15. SAVE COMPLETE COEFFICIENT DATA
# ============================================================

coefficient_path = (
    OUTPUT_DIR
    / "logistic_regression_coefficients.csv"
)

coefficient_df.to_csv(
    coefficient_path
)


# ============================================================
# 16. CREATE TEXT REPORT
# ============================================================

report_path = (
    OUTPUT_DIR
    / "feature_analysis.txt"
)

with open(
    report_path,
    "w",
    encoding="utf-8"
) as report:

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "LOGISTIC REGRESSION FEATURE ANALYSIS\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        "Model:\n"
    )

    report.write(
        "Tuned Logistic Regression\n\n"
    )

    report.write(
        "Parameters:\n"
    )

    report.write(
        "C = 1\n"
    )

    report.write(
        "class_weight = balanced\n"
    )

    report.write(
        "solver = lbfgs\n\n"
    )

    report.write(
        f"Original features: {X.shape[1]}\n"
    )

    report.write(
        f"Transformed features: {len(feature_names)}\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "TOP 20 FEATURES BY MEAN ABSOLUTE COEFFICIENT\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        coefficient_df[
            ["Mean_Absolute_Coefficient"]
        ]
        .head(20)
        .round(4)
        .to_string()
    )

    report.write(
        "\n\n"
    )

    for current_class in classes:

        report.write(
            "=" * 70 + "\n"
        )

        report.write(
            f"{current_class.upper()}\n"
        )

        report.write(
            "=" * 70 + "\n\n"
        )

        report.write(
            "Strongest positive features:\n\n"
        )

        report.write(
            class_feature_results[
                current_class
            ]["positive"]
            .round(4)
            .to_string()
        )

        report.write(
            "\n\n"
        )

        report.write(
            "Strongest negative features:\n\n"
        )

        report.write(
            class_feature_results[
                current_class
            ]["negative"]
            .round(4)
            .to_string()
        )

        report.write(
            "\n\n"
        )


# ============================================================
# 17. COMPLETE
# ============================================================

print("\n" + "=" * 70)
print("FEATURE ANALYSIS COMPLETE")
print("=" * 70)

print(
    f"\nCoefficient data saved to:\n"
    f"{coefficient_path}"
)

print(
    f"\nFeature analysis report saved at\n"
    f"{report_path}"
)