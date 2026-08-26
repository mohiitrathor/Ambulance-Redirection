import pandas as pd
import joblib

from pathlib import Path


# ============================================================
# SETTINGS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent

MODEL_PATH = (
    BASE_DIR
    / "Models"
    / "Final Model"
    / "logistic_regression_final.joblib"
)


# ============================================================
# 1. LOAD MODEL
# ============================================================

print("=" * 70)
print("EMERGENCY AMBULANCE SYSTEM - SEVERITY PREDICTION")
print("=" * 70)

print("\nLoading trained model...")

model = joblib.load(
    MODEL_PATH
)

print("Model loaded successfully.")


# ============================================================
# 2. COLLECT PATIENT INFORMATION
# ============================================================

print("\n" + "=" * 70)
print("PATIENT INFORMATION")
print("=" * 70)

print("\nEnter patient information below.\n")


def get_int(prompt, minimum=None, maximum=None):

    while True:

        try:

            value = int(input(prompt))

            if minimum is not None and value < minimum:
                print(
                    f"Value must be >= {minimum}."
                )
                continue

            if maximum is not None and value > maximum:
                print(
                    f"Value must be <= {maximum}."
                )
                continue

            return value

        except ValueError:

            print("Please enter a valid integer.")


def get_float(prompt, minimum=None, maximum=None):

    while True:

        try:

            value = float(input(prompt))

            if minimum is not None and value < minimum:
                print(
                    f"Value must be >= {minimum}."
                )
                continue

            if maximum is not None and value > maximum:
                print(
                    f"Value must be <= {maximum}."
                )
                continue

            return value

        except ValueError:

            print("Please enter a valid number.")


def get_choice(prompt, choices):

    while True:

        value = input(
            f"{prompt} ({', '.join(choices)}): "
        ).strip()

        if value in choices:
            return value

        print(
            "Invalid choice. Please select one of the listed values."
        )


# ============================================================
# BASIC INFORMATION
# ============================================================

age = get_int(
    "Age: ",
    1,
    95
)

sex = get_choice(
    "Sex",
    [
        "Male",
        "Female"
    ]
)

condition = get_choice(
    "Primary condition",
    [
        "Cardiac",
        "Respiratory",
        "Trauma",
        "Neurological",
        "Infection",
        "Gastrointestinal",
        "Other"
    ]
)


# ============================================================
# VITAL SIGNS
# ============================================================

heart_rate = get_int(
    "Heart Rate (bpm): ",
    40,
    180
)

spo2 = get_float(
    "SpO2 (%): ",
    70,
    100
)

systolic_bp = get_int(
    "Systolic BP (mmHg): ",
    60,
    200
)

diastolic_bp = get_int(
    "Diastolic BP (mmHg): ",
    35,
    130
)

respiratory_rate = get_int(
    "Respiratory Rate (/min): ",
    6,
    45
)

temperature = get_float(
    "Temperature (°C): ",
    34,
    42
)

gcs = get_int(
    "GCS: ",
    3,
    15
)

pain_score = get_int(
    "Pain Score (0-10): ",
    0,
    10
)

blood_glucose = get_int(
    "Blood Glucose (mg/dL): ",
    40,
    400
)


# ============================================================
# CLINICAL FEATURES
# ============================================================

oxygen_requirement = get_choice(
    "Oxygen Requirement",
    [
        "None",
        "Nasal Cannula",
        "Oxygen Mask",
        "Ventilator"
    ]
)

respiratory_distress = get_int(
    "Respiratory Distress (0 = No, 1 = Yes): ",
    0,
    1
)

chest_pain = get_int(
    "Chest Pain (0 = No, 1 = Yes): ",
    0,
    1
)

consciousness = get_choice(
    "Consciousness",
    [
        "Alert",
        "Confused",
        "Drowsy",
        "Unconscious"
    ]
)

bleeding = get_int(
    "Bleeding (0 = No, 1 = Yes): ",
    0,
    1
)

seizure = get_int(
    "Seizure (0 = No, 1 = Yes): ",
    0,
    1
)


# ============================================================
# INJURY / MEDICAL HISTORY
# ============================================================

injury_type = get_choice(
    "Injury Type",
    [
        "None",
        "Fracture",
        "Head Injury",
        "Burn",
        "Laceration",
        "Internal Injury"
    ]
)

diabetes = get_int(
    "Diabetes (0 = No, 1 = Yes): ",
    0,
    1
)

hypertension = get_int(
    "Hypertension (0 = No, 1 = Yes): ",
    0,
    1
)

heart_disease = get_int(
    "Heart Disease (0 = No, 1 = Yes): ",
    0,
    1
)

respiratory_disease = get_int(
    "Respiratory Disease (0 = No, 1 = Yes): ",
    0,
    1
)

arrival_mode = get_choice(
    "Arrival Mode",
    [
        "Walk-in",
        "Ambulance",
        "Referral"
    ]
)


# ============================================================
# 3. CREATE INPUT DATAFRAME
# ============================================================

patient = pd.DataFrame([{

    "Age": age,

    "Sex": sex,

    "Condition": condition,

    "Heart_Rate": heart_rate,

    "SpO2": spo2,

    "Systolic_BP": systolic_bp,

    "Diastolic_BP": diastolic_bp,

    "Respiratory_Rate": respiratory_rate,

    "Temperature": temperature,

    "GCS": gcs,

    "Pain_Score": pain_score,

    "Blood_Glucose": blood_glucose,

    "Oxygen_Requirement": oxygen_requirement,

    "Respiratory_Distress": respiratory_distress,

    "Chest_Pain": chest_pain,

    "Consciousness": consciousness,

    "Bleeding": bleeding,

    "Seizure": seizure,

    "Injury_Type": injury_type,

    "Diabetes": diabetes,

    "Hypertension": hypertension,

    "Heart_Disease": heart_disease,

    "Respiratory_Disease": respiratory_disease,

    "Arrival_Mode": arrival_mode
}])


# ============================================================
# 4. PREDICTION
# ============================================================

print("\n" + "=" * 70)
print("GENERATING PREDICTION")
print("=" * 70)

prediction = model.predict(
    patient
)[0]

probabilities = model.predict_proba(
    patient
)[0]

classes = model.classes_

confidence = probabilities.max()


# ============================================================
# 5. DISPLAY RESULT
# ============================================================

print("\n" + "=" * 70)
print("SEVERITY PREDICTION")
print("=" * 70)

print(
    f"\nPredicted Severity: {prediction}"
)

print(
    f"Confidence:         {confidence * 100:.2f}%"
)


# ============================================================
# 6. CLASS PROBABILITIES
# ============================================================

print("\n" + "=" * 70)
print("CLASS PROBABILITIES")
print("=" * 70)

for class_name, probability in sorted(
    zip(classes, probabilities),
    key=lambda x: x[1],
    reverse=True
):

    print(
        f"{class_name:<15}: {probability * 100:6.2f}%"
    )


# ============================================================
# 7. AMBULANCE PRIORITY
# ============================================================

priority_mapping = {

    "Critical": "P1",

    "Emergency": "P2",

    "Moderate": "P3",

    "Low": "P4",

    "Non-Urgent": "P5"
}

priority = priority_mapping[
    prediction
]

print("\n" + "=" * 70)
print("AMBULANCE PRIORITY")
print("=" * 70)

print(
    f"\nPriority: {priority}"
)

print("\nPrediction complete.")