import pandas as pd
import numpy as np

from pathlib import Path

from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import make_scorer, balanced_accuracy_score, f1_score


# ============================================================
# SETTINGS
# ============================================================

RANDOM_STATE = 42

N_SPLITS = 5

BASE_DIR = Path(__file__).resolve().parent.parent.parent

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


# ============================================================
# 1. LOAD DATA
# ============================================================

print("=" * 70)
print("EMERGENCY AMBULANCE SYSTEM - CROSS-VALIDATION ANALYSIS")
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
# 5. PREPROCESSING
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
# 6. TUNED LOGISTIC REGRESSION
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
# 7. STRATIFIED K-FOLD
# ============================================================
#
# Stratification preserves the severity distribution in
# every fold.
# ============================================================

cv = StratifiedKFold(
    n_splits=N_SPLITS,
    shuffle=True,
    random_state=RANDOM_STATE
)


print("\n" + "=" * 70)
print("CROSS-VALIDATION CONFIGURATION")
print("=" * 70)

print(
    f"\nNumber of folds: {N_SPLITS}"
)

print(
    "Shuffle: True"
)

print(
    f"Random state: {RANDOM_STATE}"
)


# ============================================================
# 8. SCORING
# ============================================================

scoring = {

    "accuracy": "accuracy",

    "balanced_accuracy": make_scorer(
        balanced_accuracy_score
    ),

    "macro_f1": make_scorer(
        f1_score,
        average="macro"
    )

}


# ============================================================
# 9. RUN CROSS-VALIDATION
# ============================================================

print("\n" + "=" * 70)
print("STARTING CROSS-VALIDATION")
print("=" * 70)

print(
    "\nTraining Logistic Regression across "
    f"{N_SPLITS} folds..."
)

results = cross_validate(
    model,
    X,
    y,
    cv=cv,
    scoring=scoring,
    return_train_score=True,
    n_jobs=-1
)

print(
    "Cross-validation complete."
)


# ============================================================
# 10. FOLD RESULTS
# ============================================================

fold_results = pd.DataFrame({

    "Fold": np.arange(
        1,
        N_SPLITS + 1
    ),

    "Accuracy": results[
        "test_accuracy"
    ],

    "Balanced_Accuracy": results[
        "test_balanced_accuracy"
    ],

    "Macro_F1": results[
        "test_macro_f1"
    ],

    "Train_Accuracy": results[
        "train_accuracy"
    ],

    "Train_Balanced_Accuracy": results[
        "train_balanced_accuracy"
    ],

    "Train_Macro_F1": results[
        "train_macro_f1"
    ]

})


print("\n" + "=" * 70)
print("FOLD RESULTS")
print("=" * 70)

print(
    fold_results.round(4).to_string(
        index=False
    )
)


# ============================================================
# 11. SUMMARY STATISTICS
# ============================================================

metrics = [
    "Accuracy",
    "Balanced_Accuracy",
    "Macro_F1"
]

summary_rows = []

for metric in metrics:

    values = fold_results[
        metric
    ]

    summary_rows.append({

        "Metric": metric,

        "Mean": values.mean(),

        "Std": values.std(),

        "Minimum": values.min(),

        "Maximum": values.max()

    })


summary_df = pd.DataFrame(
    summary_rows
)


print("\n" + "=" * 70)
print("CROSS-VALIDATION SUMMARY")
print("=" * 70)

print(
    summary_df.round(4).to_string(
        index=False
    )
)


# ============================================================
# 12. TRAIN / VALIDATION GAP
# ============================================================

train_test_gap = pd.DataFrame({

    "Metric": metrics,

    "Mean_Train": [
        fold_results[
            "Train_Accuracy"
        ].mean(),

        fold_results[
            "Train_Balanced_Accuracy"
        ].mean(),

        fold_results[
            "Train_Macro_F1"
        ].mean()
    ],

    "Mean_Validation": [
        fold_results[
            "Accuracy"
        ].mean(),

        fold_results[
            "Balanced_Accuracy"
        ].mean(),

        fold_results[
            "Macro_F1"
        ].mean()
    ]

})

train_test_gap["Gap"] = (
    train_test_gap["Mean_Train"]
    - train_test_gap["Mean_Validation"]
)


print("\n" + "=" * 70)
print("TRAIN / VALIDATION PERFORMANCE GAP")
print("=" * 70)

print(
    train_test_gap.round(4).to_string(
        index=False
    )
)


# ============================================================
# 13. ROBUSTNESS CHECK
# ============================================================

balanced_accuracy_std = (
    fold_results[
        "Balanced_Accuracy"
    ].std()
)

balanced_accuracy_mean = (
    fold_results[
        "Balanced_Accuracy"
    ].mean()
)

balanced_accuracy_range = (
    fold_results[
        "Balanced_Accuracy"
    ].max()
    -
    fold_results[
        "Balanced_Accuracy"
    ].min()
)


print("\n" + "=" * 70)
print("ROBUSTNESS CHECK")
print("=" * 70)

print(
    f"\nMean balanced accuracy: "
    f"{balanced_accuracy_mean:.4f}"
)

print(
    f"Standard deviation:     "
    f"{balanced_accuracy_std:.4f}"
)

print(
    f"Fold range:             "
    f"{balanced_accuracy_range:.4f}"
)


if balanced_accuracy_std < 0.01:

    stability_message = (
        "Balanced accuracy shows low variation "
        "across folds, suggesting stable performance."
    )

elif balanced_accuracy_std < 0.02:

    stability_message = (
        "Balanced accuracy shows moderate variation "
        "across folds."
    )

else:

    stability_message = (
        "Balanced accuracy shows relatively high "
        "variation across folds and should be "
        "investigated further."
    )


print(
    f"\n{stability_message}"
)


# ============================================================
# 14. WRITE REPORT
# ============================================================

report_path = (
    REPORT_DIR
    / "cross_validation_analysis.txt"
)

with open(
    report_path,
    "w",
    encoding="utf-8"
) as report:

    report.write(
        "EMERGENCY AMBULANCE SYSTEM - "
        "CROSS-VALIDATION ANALYSIS\n"
    )

    report.write("=" * 70 + "\n\n")

    report.write(
        "MODEL\n"
    )

    report.write(
        "Tuned Logistic Regression\n"
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
        "CROSS-VALIDATION\n"
    )

    report.write(
        f"Number of folds: {N_SPLITS}\n"
    )

    report.write(
        "Stratified: Yes\n"
    )

    report.write(
        f"Random state: {RANDOM_STATE}\n\n"
    )

    report.write(
        "FOLD RESULTS\n"
    )

    report.write(
        fold_results
        .round(4)
        .to_string(
            index=False
        )
    )

    report.write(
        "\n\nSUMMARY STATISTICS\n"
    )

    report.write(
        summary_df
        .round(4)
        .to_string(
            index=False
        )
    )

    report.write(
        "\n\nTRAIN / VALIDATION GAP\n"
    )

    report.write(
        train_test_gap
        .round(4)
        .to_string(
            index=False
        )
    )

    report.write(
        "\n\nROBUSTNESS\n"
    )

    report.write(
        f"Mean balanced accuracy: "
        f"{balanced_accuracy_mean:.4f}\n"
    )

    report.write(
        f"Standard deviation: "
        f"{balanced_accuracy_std:.4f}\n"
    )

    report.write(
        f"Fold range: "
        f"{balanced_accuracy_range:.4f}\n"
    )

    report.write(
        f"\n{stability_message}\n"
    )

    report.write(
        "\n\nINTERPRETATION\n"
    )

    report.write(
        "Cross-validation evaluates the tuned Logistic "
        "Regression across multiple stratified subsets "
        "of the dataset rather than relying on a single "
        "train/test split.\n\n"
    )

    report.write(
        "Balanced accuracy is emphasized because the "
        "severity classes are not equally represented. "
        "The standard deviation indicates how much "
        "performance changes between folds.\n"
    )


# ============================================================
# 15. SAVE CSV
# ============================================================

csv_path = (
    REPORT_DIR
    / "cross_validation_results.csv"
)

fold_results.to_csv(
    csv_path,
    index=False
)


# ============================================================
# 16. FINAL OUTPUT
# ============================================================

print("\n" + "=" * 70)
print("CROSS-VALIDATION ANALYSIS COMPLETE")
print("=" * 70)

print(
    f"\nReport saved to:\n{report_path}"
)

print(
    f"\nCSV saved to:\n{csv_path}"
)