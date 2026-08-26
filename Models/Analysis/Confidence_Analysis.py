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
    / "confidence_analysis.txt"
)

CSV_PATH = (
    REPORT_DIR
    / "confidence_by_error_pair.csv"
)


# ============================================================
# ERROR PAIRS TO ANALYZE
# ============================================================

ERROR_PAIRS = [
    ("Emergency", "Moderate"),
    ("Emergency", "Critical"),
    ("Critical", "Emergency"),
    ("Moderate", "Emergency"),
    ("Moderate", "Low"),
    ("Low", "Non-Urgent")
]


# ============================================================
# 1. LOAD DATA
# ============================================================

print("=" * 70)
print("EMERGENCY AMBULANCE SYSTEM - CONFIDENCE ANALYSIS")
print("=" * 70)

print("\nLoading dataset...")

df = pd.read_csv(
    DATA_PATH
)

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
# 4. FEATURE TYPES
# ============================================================

categorical_features = X.select_dtypes(
    include=[
        "object",
        "category"
    ]
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

print(
    "Training complete."
)


# ============================================================
# 9. PREDICTIONS + PROBABILITIES
# ============================================================

print(
    "\nGenerating predictions and probabilities..."
)

y_pred = model.predict(
    X_test
)

probabilities = model.predict_proba(
    X_test
)

classes = model.named_steps[
    "classifier"
].classes_


# ============================================================
# 10. CREATE TEST RESULT DATAFRAME
# ============================================================

results = X_test.copy()

results["Actual"] = y_test.values

results["Predicted"] = y_pred

results["Correct"] = (
    results["Actual"]
    == results["Predicted"]
)

results["Confidence"] = (
    probabilities.max(
        axis=1
    )
)


# ============================================================
# 11. ADD PROBABILITY OF ACTUAL CLASS
# ============================================================


actual_class_probabilities = []

predicted_class_probabilities = []

for index, actual_class in enumerate(
    y_test.values
):

    predicted_class = y_pred[index]

    actual_index = np.where(
        classes == actual_class
    )[0][0]

    predicted_index = np.where(
        classes == predicted_class
    )[0][0]

    actual_class_probabilities.append(
        probabilities[
            index,
            actual_index
        ]
    )

    predicted_class_probabilities.append(
        probabilities[
            index,
            predicted_index
        ]
    )


results["Actual_Class_Probability"] = (
    actual_class_probabilities
)

results["Predicted_Class_Probability"] = (
    predicted_class_probabilities
)


# ============================================================
# 12. CONFIDENCE CATEGORY
# ============================================================

def confidence_category(
    confidence
):

    if confidence < 0.60:
        return "Borderline"

    elif confidence < 0.80:
        return "Moderate"

    else:
        return "High"


results["Confidence_Category"] = (
    results["Confidence"]
    .apply(confidence_category)
)


# ============================================================
# 13. OVERALL CONFIDENCE
# ============================================================

correct = results[
    results["Correct"]
]

incorrect = results[
    ~results["Correct"]
]


print("\n" + "=" * 70)
print("OVERALL CONFIDENCE")
print("=" * 70)

print(
    f"\nCorrect predictions: "
    f"{len(correct):,}"
)

print(
    f"Incorrect predictions: "
    f"{len(incorrect):,}"
)

print(
    f"\nAverage confidence - correct: "
    f"{correct['Confidence'].mean():.4f}"
)

print(
    f"Average confidence - incorrect: "
    f"{incorrect['Confidence'].mean():.4f}"
)

print(
    f"\nMedian confidence - correct: "
    f"{correct['Confidence'].median():.4f}"
)

print(
    f"Median confidence - incorrect: "
    f"{incorrect['Confidence'].median():.4f}"
)


# ============================================================
# 14. CONFIDENCE DISTRIBUTION FOR ALL ERRORS
# ============================================================

print("\n" + "=" * 70)
print("INCORRECT PREDICTION CONFIDENCE")
print("=" * 70)

if len(incorrect) > 0:

    confidence_counts = (
        incorrect[
            "Confidence_Category"
        ]
        .value_counts()
    )

    for category in [
        "Borderline",
        "Moderate",
        "High"
    ]:

        count = confidence_counts.get(
            category,
            0
        )

        percentage = (
            count
            / len(incorrect)
            * 100
        )

        print(
            f"{category:<12}: "
            f"{count:>5,} "
            f"({percentage:>6.2f}%)"
        )


# ============================================================
# 15. ANALYZE MAJOR ERROR PAIRS
# ============================================================

pair_results = []

print("\n" + "=" * 70)
print("MAJOR ERROR PAIR CONFIDENCE")
print("=" * 70)

for actual_class, predicted_class in ERROR_PAIRS:

    pair = results[
        (results["Actual"] == actual_class)
        &
        (results["Predicted"] == predicted_class)
    ].copy()

    count = len(pair)

    if count == 0:

        print(
            f"\n{actual_class} -> "
            f"{predicted_class}: no cases"
        )

        continue

    average_confidence = (
        pair["Confidence"]
        .mean()
    )

    median_confidence = (
        pair["Confidence"]
        .median()
    )

    minimum_confidence = (
        pair["Confidence"]
        .min()
    )

    maximum_confidence = (
        pair["Confidence"]
        .max()
    )

    average_actual_probability = (
        pair[
            "Actual_Class_Probability"
        ]
        .mean()
    )

    borderline_count = (
        pair["Confidence"] < 0.60
    ).sum()

    moderate_count = (
        (pair["Confidence"] >= 0.60)
        &
        (pair["Confidence"] < 0.80)
    ).sum()

    high_count = (
        pair["Confidence"] >= 0.80
    ).sum()

    borderline_percentage = (
        borderline_count
        / count
        * 100
    )

    moderate_percentage = (
        moderate_count
        / count
        * 100
    )

    high_percentage = (
        high_count
        / count
        * 100
    )

    pair_results.append({

        "Actual": actual_class,

        "Predicted": predicted_class,

        "Count": count,

        "Average_Confidence":
            average_confidence,

        "Median_Confidence":
            median_confidence,

        "Minimum_Confidence":
            minimum_confidence,

        "Maximum_Confidence":
            maximum_confidence,

        "Average_Actual_Probability":
            average_actual_probability,

        "Borderline_Count":
            borderline_count,

        "Borderline_Percentage":
            borderline_percentage,

        "Moderate_Count":
            moderate_count,

        "Moderate_Percentage":
            moderate_percentage,

        "High_Count":
            high_count,

        "High_Percentage":
            high_percentage
    })

    print(
        f"\n{actual_class} -> "
        f"{predicted_class}"
    )

    print(
        f"  Count: "
        f"{count:,}"
    )

    print(
        f"  Average confidence: "
        f"{average_confidence:.4f}"
    )

    print(
        f"  Median confidence:  "
        f"{median_confidence:.4f}"
    )

    print(
        f"  Minimum confidence:  "
        f"{minimum_confidence:.4f}"
    )

    print(
        f"  Maximum confidence:  "
        f"{maximum_confidence:.4f}"
    )

    print(
        f"  Actual-class probability: "
        f"{average_actual_probability:.4f}"
    )

    print(
        f"  Borderline (<0.60): "
        f"{borderline_count:,} "
        f"({borderline_percentage:.2f}%)"
    )

    print(
        f"  Moderate (0.60-0.79): "
        f"{moderate_count:,} "
        f"({moderate_percentage:.2f}%)"
    )

    print(
        f"  High (>=0.80): "
        f"{high_count:,} "
        f"({high_percentage:.2f}%)"
    )


# ============================================================
# 16. SAVE PAIR RESULTS
# ============================================================

pair_df = pd.DataFrame(
    pair_results
)

pair_df.to_csv(
    CSV_PATH,
    index=False
)


# ============================================================
# 17. MOST CONFIDENT ERRORS
# ============================================================

most_confident_errors = (
    incorrect
    .sort_values(
        "Confidence",
        ascending=False
    )
    .head(20)
)


print("\n" + "=" * 70)
print("20 MOST CONFIDENT INCORRECT PREDICTIONS")
print("=" * 70)

print(
    most_confident_errors[
        [
            "Actual",
            "Predicted",
            "Confidence",
            "Actual_Class_Probability"
        ]
    ]
    .round(4)
    .to_string(index=False)
)


# ============================================================
# 18. BORDERLINE ERRORS
# ============================================================

borderline_errors = incorrect[
    incorrect["Confidence"] < 0.60
].copy()


print("\n" + "=" * 70)
print("BORDERLINE INCORRECT PREDICTIONS")
print("=" * 70)

print(
    f"\nBorderline errors: "
    f"{len(borderline_errors):,}"
)

if len(borderline_errors) > 0:

    print(
        "\nMost common borderline error pairs:"
    )

    print(
        borderline_errors
        .groupby(
            [
                "Actual",
                "Predicted"
            ]
        )
        .size()
        .sort_values(
            ascending=False
        )
        .head(15)
        .to_string()
    )


# ============================================================
# 19. HIGH-CONFIDENCE ERRORS
# ============================================================

high_confidence_errors = incorrect[
    incorrect["Confidence"] >= 0.80
].copy()


print("\n" + "=" * 70)
print("HIGH-CONFIDENCE INCORRECT PREDICTIONS")
print("=" * 70)

print(
    f"\nHigh-confidence errors: "
    f"{len(high_confidence_errors):,}"
)

if len(high_confidence_errors) > 0:

    print(
        "\nMost common high-confidence error pairs:"
    )

    print(
        high_confidence_errors
        .groupby(
            [
                "Actual",
                "Predicted"
            ]
        )
        .size()
        .sort_values(
            ascending=False
        )
        .head(15)
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
        "LOGISTIC REGRESSION CONFIDENCE ANALYSIS\n"
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
        f"Test samples: {len(results):,}\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "OVERALL CONFIDENCE\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        f"Average confidence - correct: "
        f"{correct['Confidence'].mean():.4f}\n"
    )

    report.write(
        f"Average confidence - incorrect: "
        f"{incorrect['Confidence'].mean():.4f}\n"
    )

    report.write(
        f"Median confidence - correct: "
        f"{correct['Confidence'].median():.4f}\n"
    )

    report.write(
        f"Median confidence - incorrect: "
        f"{incorrect['Confidence'].median():.4f}\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "INCORRECT PREDICTION CONFIDENCE\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    if len(incorrect) > 0:

        for category in [
            "Borderline",
            "Moderate",
            "High"
        ]:

            count = (
                incorrect[
                    "Confidence_Category"
                ]
                == category
            ).sum()

            percentage = (
                count
                / len(incorrect)
                * 100
            )

            report.write(
                f"{category}: "
                f"{count:,} "
                f"({percentage:.2f}%)\n"
            )

    report.write(
        "\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "MAJOR ERROR PAIRS\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    if len(pair_df) > 0:

        report.write(
            pair_df
            .round(4)
            .to_string(index=False)
        )

    report.write(
        "\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "MOST CONFIDENT INCORRECT PREDICTIONS\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        most_confident_errors[
            [
                "Actual",
                "Predicted",
                "Confidence",
                "Actual_Class_Probability"
            ]
        ]
        .round(4)
        .to_string(index=False)
    )

    report.write(
        "\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "BORDERLINE ERRORS\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        f"Total borderline errors: "
        f"{len(borderline_errors):,}\n\n"
    )

    if len(borderline_errors) > 0:

        report.write(
            borderline_errors
            .groupby(
                [
                    "Actual",
                    "Predicted"
                ]
            )
            .size()
            .sort_values(
                ascending=False
            )
            .head(15)
            .to_string()
        )

    report.write(
        "\n\n"
    )

    report.write(
        "=" * 70 + "\n"
    )

    report.write(
        "HIGH-CONFIDENCE ERRORS\n"
    )

    report.write(
        "=" * 70 + "\n\n"
    )

    report.write(
        f"Total high-confidence errors: "
        f"{len(high_confidence_errors):,}\n\n"
    )

    if len(high_confidence_errors) > 0:

        report.write(
            high_confidence_errors
            .groupby(
                [
                    "Actual",
                    "Predicted"
                ]
            )
            .size()
            .sort_values(
                ascending=False
            )
            .head(15)
            .to_string()
        )

    report.write(
        "\n"
    )


# ============================================================
# 21. COMPLETE
# ============================================================

print("\n" + "=" * 70)
print("CONFIDENCE ANALYSIS COMPLETE")
print("=" * 70)

print(
    f"\nReport saved to:\n"
    f"{REPORT_PATH}"
)

print(
    f"\nCSV saved to:\n"
    f"{CSV_PATH}"
)