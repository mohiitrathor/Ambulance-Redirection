import pandas as pd

from pathlib import Path

from sklearn.model_selection import (
    train_test_split,
    GridSearchCV,
    StratifiedKFold
)

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
print("XGBOOST - HYPERPARAMETER TUNING")
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
# 4. CONVERT TARGET TO NUMERIC LABELS
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
# 5. FEATURE TYPES
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
# 6. TRAIN / TEST SPLIT
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

            "passthrough",

            numeric_features
        )
    ]
)


# ============================================================
# 8. XGBOOST PIPELINE
# ============================================================

pipeline = Pipeline(
    steps=[

        (
            "preprocessor",
            preprocessor
        ),

        (
            "classifier",

            XGBClassifier(
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
# 9. HYPERPARAMETER SEARCH SPACE
# ============================================================

parameter_grid = {

    "classifier__n_estimators": [
        100,
        200,
        300
    ],

    "classifier__max_depth": [
        3,
        6,
        9
    ],

    "classifier__learning_rate": [
        0.05,
        0.1
    ],

    "classifier__subsample": [
        0.8
    ],

    "classifier__colsample_bytree": [
        0.8
    ]
}


# ============================================================
# 10. CROSS-VALIDATION
# ============================================================

cv = StratifiedKFold(
    n_splits=5,
    shuffle=True,
    random_state=RANDOM_STATE
)


# ============================================================
# 11. GRID SEARCH
# ============================================================

grid_search = GridSearchCV(
    estimator=pipeline,

    param_grid=parameter_grid,

    scoring="balanced_accuracy",

    cv=cv,

    n_jobs=-1,

    verbose=1,

    return_train_score=True
)


# ============================================================
# 12. START TUNING
# ============================================================

total_combinations = (
    len(parameter_grid["classifier__n_estimators"])
    * len(parameter_grid["classifier__max_depth"])
    * len(parameter_grid["classifier__learning_rate"])
    * len(parameter_grid["classifier__subsample"])
    * len(parameter_grid["classifier__colsample_bytree"])
)

print("\n" + "=" * 70)
print("STARTING GRID SEARCH")
print("=" * 70)

print(
    f"\nTesting {total_combinations} parameter combinations..."
)

grid_search.fit(
    X_train,
    y_train
)


# ============================================================
# 13. BEST PARAMETERS
# ============================================================

print("\n" + "=" * 70)
print("BEST PARAMETERS")
print("=" * 70)

print(
    "\nBest parameters:"
)

for parameter, value in (
    grid_search.best_params_.items()
):

    print(
        f"  {parameter}: {value}"
    )

print(
    f"\nBest CV balanced accuracy: "
    f"{grid_search.best_score_:.4f}"
)


# ============================================================
# 14. FINAL TEST SET EVALUATION
# ============================================================

print("\n" + "=" * 70)
print("FINAL TEST SET EVALUATION")
print("=" * 70)

best_model = grid_search.best_estimator_

y_pred = best_model.predict(
    X_test
)


accuracy = accuracy_score(
    y_test,
    y_pred
)

balanced_accuracy = balanced_accuracy_score(
    y_test,
    y_pred
)


print(
    f"\nAccuracy:          {accuracy:.4f}"
)

print(
    f"Balanced Accuracy: {balanced_accuracy:.4f}"
)


# ============================================================
# 15. CLASSIFICATION REPORT
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
# 16. CONFUSION MATRIX
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
# 17. TOP GRID SEARCH RESULTS
# ============================================================

results = pd.DataFrame(
    grid_search.cv_results_
)

results = (
    results[
        [
            "param_classifier__n_estimators",
            "param_classifier__max_depth",
            "param_classifier__learning_rate",
            "mean_test_score",
            "std_test_score",
            "mean_train_score"
        ]
    ]
    .sort_values(
        "mean_test_score",
        ascending=False
    )
)


print("\n" + "=" * 70)
print("TOP 10 CROSS-VALIDATION RESULTS")
print("=" * 70)

print(
    results
    .head(10)
    .to_string(index=False)
)


# ============================================================
# 18. SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(
    f"Best CV balanced accuracy: "
    f"{grid_search.best_score_:.4f}"
)

print(
    f"Test accuracy:             "
    f"{accuracy:.4f}"
)

print(
    f"Test balanced accuracy:    "
    f"{balanced_accuracy:.4f}"
)

print(
    "\nXGBoost tuning complete."
)