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
from sklearn.metrics import confusion_matrix


# ============================================================
# SETTINGS
# ============================================================

RANDOM_STATE = 42

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
    .parent
)

DATA_PATH = (
    BASE_DIR
    / "Dataset"
    / "patient_incidents.csv"
)

REPORT_DIR = (
    BASE_DIR
    / "Models"
    / "Reports"
)

REPORT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

REPORT_PATH = (
    REPORT_DIR
    / "error_analysis.txt"
)


# ============================================================
# 1. LOAD DATA
# ============================================================

print("=" * 70)
print("EMERGENCY AMBULANCE SYSTEM - ERROR ANALYSIS")
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
# 8. TRAIN
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
# 9. PREDICTIONS
# ============================================================

print("\nGenerating predictions...")

y_pred = model.predict(
    X_test
)

probabilities = model.predict_proba(
    X_test
)


# ============================================================
# 10. CREATE ANALYSIS DATAFRAME
# ============================================================

analysis_df = X_test.copy()

analysis_df["Actual"] = y_test.values

analysis_df["Predicted"] = y_pred

analysis_df["Correct"] = (
    analysis_df["Actual"]
    == analysis_df["Predicted"]
)

analysis_df["Prediction_Confidence"] = (
    probabilities.max(axis=1)
)


# ============================================================
# 11. OVERALL ERROR SUMMARY
# ============================================================

total_predictions = len(
    analysis_df
)

correct_predictions = (
    analysis_df["Correct"]
    .sum()
)

incorrect_predictions = (
    total_predictions
    - correct_predictions
)

accuracy = (
    correct_predictions
    / total_predictions
)


print("\n" + "=" * 70)
print("OVERALL ERROR SUMMARY")
print("=" * 70)

print(
    f"\nTotal test samples:  {total_predictions:,}"
)

print(
    f"Correct predictions: {correct_predictions:,}"
)

print(
    f"Incorrect predictions: {incorrect_predictions:,}"
)

print(
    f"Accuracy:             {accuracy:.4f}"
)


# ============================================================
# 12. CONFUSION MATRIX
# ============================================================

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


print("\n" + "=" * 70)
print("CONFUSION MATRIX")
print("=" * 70)

print(
    cm_df
)


# ============================================================
# 13. MOST COMMON ERROR PAIRS
# ============================================================

errors = analysis_df[
    ~analysis_df["Correct"]
].copy()

error_pairs = (
    errors
    .groupby(
        ["Actual", "Predicted"]
    )
    .size()
    .reset_index(
        name="Count"
    )
    .sort_values(
        "Count",
        ascending=False
    )
)


print("\n" + "=" * 70)
print("MOST COMMON MISCLASSIFICATION PAIRS")
print("=" * 70)

print(
    error_pairs
    .head(15)
    .to_string(index=False)
)


# ============================================================
# 14. ERROR RATE BY ACTUAL CLASS
# ============================================================

class_error_summary = []

for current_class in labels:

    class_rows = analysis_df[
        analysis_df["Actual"]
        == current_class
    ]

    total = len(
        class_rows
    )

    errors_in_class = (
        ~class_rows["Correct"]
    ).sum()

    error_rate = (
        errors_in_class / total
        if total > 0
        else 0
    )

    class_error_summary.append({

        "Severity": current_class,

        "Total": total,

        "Correct": total - errors_in_class,

        "Errors": errors_in_class,

        "Error_Rate": error_rate

    })


class_error_df = pd.DataFrame(
    class_error_summary
)


print("\n" + "=" * 70)
print("ERROR RATE BY ACTUAL SEVERITY")
print("=" * 70)

display_class_error = (
    class_error_df.copy()
)

display_class_error[
    "Error_Rate"
] *= 100

print(
    display_class_error
    .round(2)
    .to_string(index=False)
)


# ============================================================
# 15. NEIGHBORING-SEVERITY ERRORS
# ============================================================

severity_order = {
    "Non-Urgent": 0,
    "Low": 1,
    "Moderate": 2,
    "Emergency": 3,
    "Critical": 4
}

errors["Actual_Level"] = (
    errors["Actual"]
    .map(severity_order)
)

errors["Predicted_Level"] = (
    errors["Predicted"]
    .map(severity_order)
)

errors["Severity_Distance"] = (
    errors["Actual_Level"]
    - errors["Predicted_Level"]
).abs()


neighboring_errors = (
    errors["Severity_Distance"]
    == 1
).sum()

large_errors = (
    errors["Severity_Distance"]
    >= 2
).sum()


print("\n" + "=" * 70)
print("SEVERITY DISTANCE ANALYSIS")
print("=" * 70)

print(
    f"\nTotal errors: {len(errors):,}"
)

print(
    f"Neighboring-level errors: "
    f"{neighboring_errors:,}"
)

print(
    f"Errors ≥ 2 severity levels apart: "
    f"{large_errors:,}"
)

if len(errors) > 0:

    print(
        f"Neighboring-level percentage: "
        f"{neighboring_errors / len(errors) * 100:.2f}%"
    )

    print(
        f"Large-error percentage: "
        f"{large_errors / len(errors) * 100:.2f}%"
    )


# ============================================================
# 16. CRITICAL CLASS ERROR ANALYSIS
# ============================================================

critical_cases = analysis_df[
    analysis_df["Actual"]
    == "Critical"
].copy()

critical_errors = critical_cases[
    ~critical_cases["Correct"]
].copy()


print("\n" + "=" * 70)
print("CRITICAL CLASS ERROR ANALYSIS")
print("=" * 70)

print(
    f"\nCritical cases: {len(critical_cases):,}"
)

print(
    f"Correctly classified: "
    f"{critical_cases['Correct'].sum():,}"
)

print(
    f"Misclassified: "
    f"{len(critical_errors):,}"
)

if len(critical_errors) > 0:

    print("\nCritical misclassification targets:")

    print(
        critical_errors[
            "Predicted"
        ]
        .value_counts()
        .to_string()
    )


# ============================================================
# 17. EMERGENCY CLASS ERROR ANALYSIS
# ============================================================

emergency_cases = analysis_df[
    analysis_df["Actual"]
    == "Emergency"
].copy()

emergency_errors = emergency_cases[
    ~emergency_cases["Correct"]
].copy()


print("\n" + "=" * 70)
print("EMERGENCY CLASS ERROR ANALYSIS")
print("=" * 70)

print(
    f"\nEmergency cases: {len(emergency_cases):,}"
)

print(
    f"Correctly classified: "
    f"{emergency_cases['Correct'].sum():,}"
)

print(
    f"Misclassified: "
    f"{len(emergency_errors):,}"
)

if len(emergency_errors) > 0:

    print("\nEmergency misclassification targets:")

    print(
        emergency_errors[
            "Predicted"
        ]
        .value_counts()
        .to_string()
    )


# ============================================================
# 18. CONFIDENCE OF CORRECT VS INCORRECT PREDICTIONS
# ============================================================

correct_confidence = (
    analysis_df[
        analysis_df["Correct"]
    ]["Prediction_Confidence"]
    .mean()
)

incorrect_confidence = (
    analysis_df[
        ~analysis_df["Correct"]
    ]["Prediction_Confidence"]
    .mean()
)


print("\n" + "=" * 70)
print("PREDICTION CONFIDENCE")
print("=" * 70)

print(
    f"\nAverage confidence - correct: "
    f"{correct_confidence:.4f}"
)

print(
    f"Average confidence - incorrect: "
    f"{incorrect_confidence:.4f}"
)


# ============================================================
# 19. FEATURE SUMMARY FOR MISCLASSIFICATIONS
# ============================================================

numeric_analysis_features = [
    feature
    for feature in numeric_features
    if feature in analysis_df.columns
]

correct_means = (
    analysis_df[
        analysis_df["Correct"]
    ][numeric_analysis_features]
    .mean()
)

incorrect_means = (
    analysis_df[
        ~analysis_df["Correct"]
    ][numeric_analysis_features]
    .mean()
)

feature_difference = pd.DataFrame({

    "Correct_Mean": correct_means,

    "Incorrect_Mean": incorrect_means

})

feature_difference[
    "Absolute_Difference"
] = (
    feature_difference[
        "Correct_Mean"
    ]
    - feature_difference[
        "Incorrect_Mean"
    ]
).abs()

feature_difference = (
    feature_difference
    .sort_values(
        "Absolute_Difference",
        ascending=False
    )
)


print("\n" + "=" * 70)
print("NUMERIC FEATURE DIFFERENCES")
print("=" * 70)

print(
    feature_difference
    .head(15)
    .round(3)
    .to_string()
)


# ============================================================
# 20. WRITE REPORT
# ============================================================

print("\nWriting report...")

with open(
    REPORT_PATH,
    "w",
    encoding="utf-8"
) as report:

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "LOGISTIC REGRESSION ERROR ANALYSIS\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        "Model: Tuned Logistic Regression\n"
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
        f"Dataset shape: {df.shape}\n"
    )

    report.write(
        f"Test samples: {total_predictions:,}\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "OVERALL ERROR SUMMARY\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        f"Correct predictions: {correct_predictions:,}\n"
    )

    report.write(
        f"Incorrect predictions: {incorrect_predictions:,}\n"
    )

    report.write(
        f"Accuracy: {accuracy:.4f}\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "CONFUSION MATRIX\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        cm_df.to_string()
    )

    report.write(
        "\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "MOST COMMON MISCLASSIFICATION PAIRS\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        error_pairs
        .head(15)
        .to_string(index=False)
    )

    report.write(
        "\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "ERROR RATE BY ACTUAL SEVERITY\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        display_class_error
        .round(2)
        .to_string(index=False)
    )

    report.write(
        "\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "SEVERITY DISTANCE ANALYSIS\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        f"Total errors: {len(errors):,}\n"
    )

    report.write(
        f"Neighboring-level errors: "
        f"{neighboring_errors:,}\n"
    )

    report.write(
        f"Errors >= 2 levels apart: "
        f"{large_errors:,}\n"
    )

    if len(errors) > 0:

        report.write(
            f"Neighboring-level percentage: "
            f"{neighboring_errors / len(errors) * 100:.2f}%\n"
        )

        report.write(
            f"Large-error percentage: "
            f"{large_errors / len(errors) * 100:.2f}%\n"
        )

    report.write(
        "\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "CRITICAL CLASS\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        f"Total Critical cases: "
        f"{len(critical_cases):,}\n"
    )

    report.write(
        f"Correct: "
        f"{critical_cases['Correct'].sum():,}\n"
    )

    report.write(
        f"Errors: "
        f"{len(critical_errors):,}\n\n"
    )

    if len(critical_errors) > 0:

        report.write(
            critical_errors[
                "Predicted"
            ]
            .value_counts()
            .to_string()
        )

    report.write(
        "\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "EMERGENCY CLASS\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        f"Total Emergency cases: "
        f"{len(emergency_cases):,}\n"
    )

    report.write(
        f"Correct: "
        f"{emergency_cases['Correct'].sum():,}\n"
    )

    report.write(
        f"Errors: "
        f"{len(emergency_errors):,}\n\n"
    )

    if len(emergency_errors) > 0:

        report.write(
            emergency_errors[
                "Predicted"
            ]
            .value_counts()
            .to_string()
        )

    report.write(
        "\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "PREDICTION CONFIDENCE\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        f"Correct predictions: "
        f"{correct_confidence:.4f}\n"
    )

    report.write(
        f"Incorrect predictions: "
        f"{incorrect_confidence:.4f}\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "NUMERIC FEATURE DIFFERENCES\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        feature_difference
        .head(15)
        .round(3)
        .to_string()
    )

    report.write(
        "\n"
    )


# ============================================================
# 21. COMPLETE
# ============================================================

print("\n" + "=" * 70)
print("ERROR ANALYSIS COMPLETE")
print("=" * 70)

print(
    f"\nReport saved to:\n"
    f"{REPORT_PATH}"
)