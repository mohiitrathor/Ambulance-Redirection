import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from pathlib import Path

from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    log_loss,
    brier_score_loss
)
from sklearn.calibration import calibration_curve


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

REPORT_DIR = (
    BASE_DIR
    / "Models"
    / "Reports"
)

PLOT_DIR = (
    BASE_DIR
    / "Models"
    / "Reports"
    / "calibration_plots"
)

REPORT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

PLOT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# 1. LOAD DATA
# ============================================================

print("=" * 70)
print("EMERGENCY AMBULANCE SYSTEM - CALIBRATION ANALYSIS")
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
# 8. PREDICTIONS AND PROBABILITIES
# ============================================================

print(
    "\nGenerating predictions and probabilities..."
)

y_pred = model.predict(
    X_test
)

y_proba = model.predict_proba(
    X_test
)

classes = model.named_steps[
    "classifier"
].classes_


# ============================================================
# 9. BASIC PERFORMANCE
# ============================================================

accuracy = accuracy_score(
    y_test,
    y_pred
)

balanced_accuracy = balanced_accuracy_score(
    y_test,
    y_pred
)

logloss = log_loss(
    y_test,
    y_proba,
    labels=classes
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

print(
    f"Log Loss:          {logloss:.4f}"
)


# ============================================================
# 10. OVERALL CONFIDENCE CALIBRATION
# ============================================================

predicted_class_indices = np.argmax(
    y_proba,
    axis=1
)

confidence = np.max(
    y_proba,
    axis=1
)

correct = (
    y_pred == y_test.to_numpy()
)


# ============================================================
# 11. CONFIDENCE BIN ANALYSIS
# ============================================================

confidence_bins = [
    0.0,
    0.5,
    0.6,
    0.7,
    0.8,
    0.9,
    1.0
]

confidence_labels = [
    "< 0.50",
    "0.50 - 0.59",
    "0.60 - 0.69",
    "0.70 - 0.79",
    "0.80 - 0.89",
    "0.90 - 1.00"
]

confidence_bin = pd.cut(
    confidence,
    bins=confidence_bins,
    labels=confidence_labels,
    include_lowest=True
)

confidence_df = pd.DataFrame({
    "Confidence_Bin": confidence_bin,
    "Confidence": confidence,
    "Correct": correct
})

confidence_summary = (
    confidence_df
    .groupby(
        "Confidence_Bin",
        observed=False
    )
    .agg(
        Samples=("Correct", "size"),
        Average_Confidence=(
            "Confidence",
            "mean"
        ),
        Accuracy=(
            "Correct",
            "mean"
        )
    )
)

confidence_summary["Accuracy"] *= 100

confidence_summary["Calibration_Gap"] = (
    confidence_summary["Average_Confidence"] * 100
    - confidence_summary["Accuracy"]
)


print("\n" + "=" * 70)
print("CONFIDENCE VS ACTUAL ACCURACY")
print("=" * 70)

print(
    confidence_summary
    .round(4)
)


# ============================================================
# 12. EXPECTED CALIBRATION ERROR
# ============================================================

ece = 0.0

total_samples = len(confidence_df)

for _, row in confidence_summary.iterrows():

    if pd.isna(row["Samples"]):
        continue

    bin_weight = (
        row["Samples"]
        / total_samples
    )

    confidence_value = (
        row["Average_Confidence"]
    )

    accuracy_value = (
        row["Accuracy"] / 100
    )

    ece += (
        bin_weight
        * abs(
            confidence_value
            - accuracy_value
        )
    )


print("\n" + "=" * 70)
print("CALIBRATION METRICS")
print("=" * 70)

print(
    f"\nExpected Calibration Error: {ece:.4f}"
)

print(
    f"Log Loss:                   {logloss:.4f}"
)


# ============================================================
# 13. PER-CLASS CALIBRATION
# ============================================================

print("\n" + "=" * 70)
print("PER-CLASS CALIBRATION")
print("=" * 70)

class_results = []

for class_index, class_name in enumerate(classes):

    y_binary = (
        y_test == class_name
    ).astype(int)

    class_probability = y_proba[
        :,
        class_index
    ]

    brier = brier_score_loss(
        y_binary,
        class_probability
    )

    class_logloss = log_loss(
        y_binary,
        np.column_stack([
            1 - class_probability,
            class_probability
        ])
    )

    class_results.append({

        "Class": class_name,

        "Brier_Score": brier,

        "Log_Loss": class_logloss

    })


class_results_df = pd.DataFrame(
    class_results
)

print(
    class_results_df.round(4)
)


# ============================================================
# 14. CALIBRATION CURVE
# ============================================================

plt.figure(
    figsize=(10, 8)
)

plt.plot(
    [0, 1],
    [0, 1],
    linestyle="--",
    label="Perfect Calibration"
)

for class_index, class_name in enumerate(classes):

    y_binary = (
        y_test == class_name
    ).astype(int)

    class_probability = y_proba[
        :,
        class_index
    ]

    fraction_positive, mean_probability = (
        calibration_curve(
            y_binary,
            class_probability,
            n_bins=10,
            strategy="uniform"
        )
    )

    plt.plot(
        mean_probability,
        fraction_positive,
        marker="o",
        label=class_name
    )


plt.xlabel(
    "Mean Predicted Probability"
)

plt.ylabel(
    "Fraction of Positives"
)

plt.title(
    "Logistic Regression Calibration Curves"
)

plt.legend()

plt.grid(
    alpha=0.3
)

plt.tight_layout()

calibration_plot_path = (
    PLOT_DIR
    / "calibration_curve.png"
)

plt.savefig(
    calibration_plot_path,
    dpi=150
)

plt.close()


# ============================================================
# 15. CONFIDENCE VS ACCURACY PLOT
# ============================================================

plot_data = confidence_summary.dropna()

plt.figure(
    figsize=(10, 6)
)

x = np.arange(
    len(plot_data)
)

plt.plot(
    x,
    plot_data["Average_Confidence"] * 100,
    marker="o",
    label="Average Confidence"
)

plt.plot(
    x,
    plot_data["Accuracy"],
    marker="o",
    label="Actual Accuracy"
)

plt.xticks(
    x,
    plot_data.index
)

plt.xlabel(
    "Confidence Range"
)

plt.ylabel(
    "Percentage"
)

plt.title(
    "Predicted Confidence vs Actual Accuracy"
)

plt.legend()

plt.grid(
    alpha=0.3
)

plt.tight_layout()

confidence_plot_path = (
    PLOT_DIR
    / "confidence_vs_accuracy.png"
)

plt.savefig(
    confidence_plot_path,
    dpi=150
)

plt.close()


# ============================================================
# 16. WRITE REPORT
# ============================================================

report_path = (
    REPORT_DIR
    / "calibration_analysis.txt"
)

with open(
    report_path,
    "w",
    encoding="utf-8"
) as report:

    report.write(
        "EMERGENCY AMBULANCE SYSTEM - "
        "CALIBRATION ANALYSIS\n"
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
        "DATASET\n"
    )

    report.write(
        f"Total samples: {len(df):,}\n"
    )

    report.write(
        f"Training samples: {len(X_train):,}\n"
    )

    report.write(
        f"Testing samples: {len(X_test):,}\n\n"
    )

    report.write(
        "MODEL PERFORMANCE\n"
    )

    report.write(
        f"Accuracy: {accuracy:.4f}\n"
    )

    report.write(
        f"Balanced Accuracy: "
        f"{balanced_accuracy:.4f}\n"
    )

    report.write(
        f"Log Loss: {logloss:.4f}\n"
    )

    report.write(
        f"Expected Calibration Error: "
        f"{ece:.4f}\n\n"
    )

    report.write(
        "CONFIDENCE VS ACTUAL ACCURACY\n"
    )

    report.write(
        confidence_summary
        .round(4)
        .to_string()
    )

    report.write(
        "\n\nPER-CLASS CALIBRATION\n"
    )

    report.write(
        class_results_df
        .round(4)
        .to_string(
            index=False
        )
    )

    report.write(
        "\n\nINTERPRETATION\n"
    )

    report.write(
        "Expected Calibration Error (ECE) measures "
        "the difference between predicted confidence "
        "and observed accuracy across confidence bins. "
        "Lower values indicate better calibration.\n\n"
    )

    report.write(
        "A well-calibrated model should have predicted "
        "confidence that closely matches its observed "
        "accuracy. For example, predictions made with "
        "approximately 80% confidence should be correct "
        "roughly 80% of the time.\n"
    )


# ============================================================
# 17. FINAL OUTPUT
# ============================================================

print("\n" + "=" * 70)
print("CALIBRATION ANALYSIS COMPLETE")
print("=" * 70)

print(
    f"\nReport saved to:\n{report_path}"
)

print(
    f"\nCalibration plot saved to:\n"
    f"{calibration_plot_path}"
)

print(
    f"\nConfidence plot saved to:\n"
    f"{confidence_plot_path}"
)