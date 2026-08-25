import pandas as pd

from pathlib import Path

from sklearn.model_selection import (
    train_test_split,
    GridSearchCV,
    StratifiedKFold
)

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

from sklearn.preprocessing import (
    OneHotEncoder,
    StandardScaler
)

from sklearn.linear_model import LogisticRegression

from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix
)


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
print("LOGISTIC REGRESSION - HYPERPARAMETER TUNING")
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
# 4. FEATURE TYPES
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
# 7. LOGISTIC REGRESSION PIPELINE
# ============================================================

pipeline = Pipeline(
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


# ============================================================
# 8. HYPERPARAMETER SEARCH SPACE
# ============================================================

parameter_grid = {

    "classifier__C": [
        0.01,
        0.1,
        1,
        10,
        100
    ],

    "classifier__class_weight": [
        None,
        "balanced"
    ],

    "classifier__solver": [
        "lbfgs",
        "newton-cg"
    ]
}


# ============================================================
# 9. CROSS-VALIDATION
# ============================================================


cv = StratifiedKFold(
    n_splits=5,
    shuffle=True,
    random_state=RANDOM_STATE
)


# ============================================================
# 10. GRID SEARCH
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
# 11. TRAIN / TUNE
# ============================================================

print("\n" + "=" * 70)
print("STARTING GRID SEARCH")
print("=" * 70)

print(
    "\nTesting "
    f"{len(parameter_grid['classifier__C']) * 2 * 2}"
    " parameter combinations..."
)

grid_search.fit(
    X_train,
    y_train
)


# ============================================================
# 12. BEST PARAMETERS
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
# 13. TEST SET EVALUATION
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
# 14. CLASSIFICATION REPORT
# ============================================================

labels = [
    "Non-Urgent",
    "Low",
    "Moderate",
    "Emergency",
    "Critical"
]

print("\n" + "=" * 70)
print("CLASSIFICATION REPORT")
print("=" * 70)

print(
    classification_report(
        y_test,
        y_pred,
        labels=labels,
        digits=4
    )
)


# ============================================================
# 15. CONFUSION MATRIX
# ============================================================

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
# 16. TOP GRID SEARCH RESULTS
# ============================================================

results = pd.DataFrame(
    grid_search.cv_results_
)

results = (
    results[
        [
            "param_classifier__C",
            "param_classifier__class_weight",
            "param_classifier__solver",
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
# 17. SUMMARY
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
    "\n LR tuning complete."
)