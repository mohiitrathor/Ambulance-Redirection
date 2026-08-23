import numpy as np
import pandas as pd
from pathlib import Path


# ============================================================
# SETTINGS
# ============================================================

np.random.seed(42)

N_PATIENTS = 100_000
N_AMBULANCES = 1_000
N_HOSPITALS = 300

SCENARIOS_PER_INCIDENT = 5

CITY_LAT_MIN = 26.75
CITY_LAT_MAX = 27.00

CITY_LON_MIN = 75.65
CITY_LON_MAX = 76.00


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "Dataset"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clip_normal(mean, std, low, high, size):

    return np.clip(
        np.random.normal(
            mean,
            std,
            size
        ),
        low,
        high
    )


def choose(values, probabilities, size):

    return np.random.choice(
        values,
        size=size,
        p=probabilities
    )


# ============================================================
# 1. INCIDENT ID
# ============================================================

incident_id = np.arange(
    1,
    N_PATIENTS + 1
)


# ============================================================
# 2. BASIC PATIENT INFORMATION
# ============================================================

age = np.random.randint(
    1,
    96,
    N_PATIENTS
)

sex = choose(
    [
        "Male",
        "Female"
    ],
    [
        0.52,
        0.48
    ],
    N_PATIENTS
)


# ============================================================
# 3. PRIMARY CONDITION
# ============================================================

condition_names = np.array([
    "Cardiac",
    "Respiratory",
    "Trauma",
    "Neurological",
    "Infection",
    "Gastrointestinal",
    "Other"
])

condition = choose(
    condition_names,
    [
        0.18,
        0.18,
        0.20,
        0.12,
        0.14,
        0.08,
        0.10
    ],
    N_PATIENTS
)


# ============================================================
# 4. GENERATE LATENT SEVERITY
# ============================================================
#
# Severity is generated FROM CONDITION.
#
# 0 = Non-Urgent
# 1 = Low
# 2 = Moderate
# 3 = Emergency
# 4 = Critical
#
# This creates a synthetic population where different
# emergency conditions have different severity distributions.
#
# IMPORTANT:
# Severity is generated independently BEFORE the clinical
# measurements. The clinical measurements are then generated
# based on this latent severity.
# ============================================================

severity_levels = np.array([
    0,
    1,
    2,
    3,
    4
])

severity_labels = np.array([
    "Non-Urgent",
    "Low",
    "Moderate",
    "Emergency",
    "Critical"
])


# ------------------------------------------------------------
# Severity probability distributions
#
# Order:
# [Non-Urgent, Low, Moderate, Emergency, Critical]
# ------------------------------------------------------------

severity_probabilities = {

    "Cardiac": np.array([
        0.03,
        0.10,
        0.27,
        0.38,
        0.22
    ]),

    "Respiratory": np.array([
        0.04,
        0.10,
        0.26,
        0.38,
        0.22
    ]),

    "Trauma": np.array([
        0.04,
        0.12,
        0.28,
        0.36,
        0.20
    ]),

    "Neurological": np.array([
        0.04,
        0.11,
        0.27,
        0.36,
        0.22
    ]),

    "Infection": np.array([
        0.07,
        0.18,
        0.32,
        0.29,
        0.14
    ]),

    "Gastrointestinal": np.array([
        0.10,
        0.23,
        0.36,
        0.23,
        0.08
    ]),

    "Other": np.array([
        0.12,
        0.24,
        0.34,
        0.22,
        0.08
    ])
}


# ------------------------------------------------------------
# Generate severity efficiently
# ------------------------------------------------------------

latent_severity = np.empty(
    N_PATIENTS,
    dtype=int
)

for current_condition in condition_names:

    mask = (
        condition == current_condition
    )

    count = mask.sum()

    if count == 0:
        continue

    probabilities = severity_probabilities[
        current_condition
    ]

    latent_severity[mask] = np.random.choice(
        severity_levels,
        size=count,
        p=probabilities
    )


# Convert numeric severity to labels

severity = severity_labels[
    latent_severity
]


# ============================================================
# 5. CONDITION MASKS
# ============================================================

cardiac = condition == "Cardiac"

respiratory = condition == "Respiratory"

trauma = condition == "Trauma"

neurological = condition == "Neurological"

infection = condition == "Infection"

gastrointestinal = condition == "Gastrointestinal"


# ============================================================
# 6. HEART RATE
# ============================================================

heart_rate_mean = (
    75
    + latent_severity * 9
    + cardiac * 14
    + respiratory * 7
    + infection * 7
    + trauma * 5
)

heart_rate = clip_normal(
    heart_rate_mean,
    13,
    40,
    180,
    N_PATIENTS
).round().astype(int)


# ============================================================
# 7. SpO2
# ============================================================

spo2_mean = (
    98
    - latent_severity * 2.3
    - respiratory * 5
    - infection * 1.5
)

spo2 = clip_normal(
    spo2_mean,
    2.7,
    70,
    100,
    N_PATIENTS
).round(1)


# ============================================================
# 8. SYSTOLIC BLOOD PRESSURE
# ============================================================

systolic_mean = (
    125
    - latent_severity * 5.5
    - trauma * 5
    - infection * 4
    - cardiac * 2
)

systolic_bp = clip_normal(
    systolic_mean,
    15,
    60,
    200,
    N_PATIENTS
).round().astype(int)


# ============================================================
# 9. DIASTOLIC BLOOD PRESSURE
# ============================================================

diastolic_bp = clip_normal(
    systolic_bp * 0.62,
    8,
    35,
    130,
    N_PATIENTS
).round().astype(int)


# ============================================================
# 10. RESPIRATORY RATE
# ============================================================

respiratory_rate_mean = (
    16
    + latent_severity * 1.8
    + respiratory * 7
    + infection * 3
)

respiratory_rate = clip_normal(
    respiratory_rate_mean,
    3.5,
    6,
    45,
    N_PATIENTS
).round().astype(int)


# ============================================================
# 11. TEMPERATURE
# ============================================================

temperature_mean = (
    36.8
    + infection * 1.1
    + latent_severity * 0.1
)

temperature = clip_normal(
    temperature_mean,
    0.7,
    34,
    42,
    N_PATIENTS
).round(1)


# ============================================================
# 12. GCS
# ============================================================

gcs_mean = (
    15
    - latent_severity * 1.7
    - neurological * 3
    - trauma * 1.2
)

gcs = clip_normal(
    gcs_mean,
    1.8,
    3,
    15,
    N_PATIENTS
).round().astype(int)


# ============================================================
# 13. PAIN SCORE
# ============================================================

pain_mean = (
    2
    + latent_severity * 1.3
    + cardiac * 2
    + trauma * 2
    + gastrointestinal * 1.5
)

pain_score = clip_normal(
    pain_mean,
    2,
    0,
    10,
    N_PATIENTS
).round().astype(int)


# ============================================================
# 14. BLOOD GLUCOSE
# ============================================================

blood_glucose = clip_normal(
    100 + latent_severity * 7,
    25,
    40,
    400,
    N_PATIENTS
).round().astype(int)


# ============================================================
# 15. RESPIRATORY DISTRESS
# ============================================================

respiratory_distress_probability = (
    0.02
    + latent_severity * 0.075
    + respiratory * 0.20
)

respiratory_distress_probability = np.clip(
    respiratory_distress_probability,
    0,
    0.90
)

respiratory_distress = (
    np.random.random(N_PATIENTS)
    < respiratory_distress_probability
).astype(int)


# ============================================================
# 16. CHEST PAIN
# ============================================================

chest_pain_probability = (
    0.05
    + cardiac * 0.45
    + latent_severity * 0.03
)

chest_pain_probability = np.clip(
    chest_pain_probability,
    0,
    0.85
)

chest_pain = (
    np.random.random(N_PATIENTS)
    < chest_pain_probability
).astype(int)


# ============================================================
# 17. BLEEDING
# ============================================================

bleeding_probability = (
    0.02
    + trauma * 0.35
    + latent_severity * 0.04
)

bleeding_probability = np.clip(
    bleeding_probability,
    0,
    0.80
)

bleeding = (
    np.random.random(N_PATIENTS)
    < bleeding_probability
).astype(int)


# ============================================================
# 18. SEIZURE
# ============================================================

seizure_probability = (
    0.01
    + neurological * 0.25
    + latent_severity * 0.02
)

seizure_probability = np.clip(
    seizure_probability,
    0,
    0.70
)

seizure = (
    np.random.random(N_PATIENTS)
    < seizure_probability
).astype(int)


# ============================================================
# 19. MEDICAL HISTORY
# ============================================================

diabetes_probability = (
    0.10
    + (age > 45) * 0.12
    + infection * 0.03
)

diabetes_probability = np.clip(
    diabetes_probability,
    0,
    0.50
)

diabetes = (
    np.random.random(N_PATIENTS)
    < diabetes_probability
).astype(int)


hypertension_probability = (
    0.12
    + (age > 45) * 0.20
    + cardiac * 0.10
)

hypertension_probability = np.clip(
    hypertension_probability,
    0,
    0.65
)

hypertension = (
    np.random.random(N_PATIENTS)
    < hypertension_probability
).astype(int)


heart_disease_probability = (
    0.03
    + cardiac * 0.30
    + (age > 55) * 0.08
)

heart_disease_probability = np.clip(
    heart_disease_probability,
    0,
    0.60
)

heart_disease = (
    np.random.random(N_PATIENTS)
    < heart_disease_probability
).astype(int)


respiratory_disease_probability = (
    0.04
    + respiratory * 0.30
    + (age > 50) * 0.05
)

respiratory_disease_probability = np.clip(
    respiratory_disease_probability,
    0,
    0.55
)

respiratory_disease = (
    np.random.random(N_PATIENTS)
    < respiratory_disease_probability
).astype(int)


# ============================================================
# 20. INJURY TYPE
# ============================================================
#
# "No Injury" is intentionally used instead of "None".
# This prevents pandas from interpreting it as NaN when
# reading the generated CSV.
# ============================================================

injury_type = np.full(
    N_PATIENTS,
    "No Injury",
    dtype=object
)

trauma_indices = np.where(
    trauma
)[0]

if len(trauma_indices) > 0:

    injury_type[trauma_indices] = np.random.choice(
        [
            "Fracture",
            "Head Injury",
            "Burn",
            "Laceration",
            "Internal Injury"
        ],
        size=len(trauma_indices),
        p=[
            0.30,
            0.25,
            0.10,
            0.20,
            0.15
        ]
    )


# ============================================================
# 21. CONSCIOUSNESS
# ============================================================

consciousness = np.empty(
    N_PATIENTS,
    dtype=object
)

consciousness[gcs >= 14] = "Alert"

consciousness[
    (gcs >= 10) &
    (gcs < 14)
] = "Confused"

consciousness[
    (gcs >= 7) &
    (gcs < 10)
] = "Drowsy"

consciousness[gcs < 7] = "Unconscious"


# ============================================================
# 22. OXYGEN REQUIREMENT
# ============================================================
#
# "No Oxygen" is intentionally used instead of "None".
# This prevents pandas from interpreting it as NaN.
# ============================================================

oxygen_requirement = np.empty(
    N_PATIENTS,
    dtype=object
)

high_spo2 = spo2 >= 95

medium_spo2 = (
    (spo2 >= 90) &
    (spo2 < 95)
)

low_spo2 = (
    (spo2 >= 80) &
    (spo2 < 90)
)

very_low_spo2 = spo2 < 80


high_indices = np.where(
    high_spo2
)[0]

oxygen_requirement[high_indices] = np.random.choice(
    [
        "No Oxygen",
        "Nasal Cannula"
    ],
    size=len(high_indices),
    p=[
        0.95,
        0.05
    ]
)


medium_indices = np.where(
    medium_spo2
)[0]

oxygen_requirement[medium_indices] = np.random.choice(
    [
        "No Oxygen",
        "Nasal Cannula",
        "Oxygen Mask"
    ],
    size=len(medium_indices),
    p=[
        0.15,
        0.60,
        0.25
    ]
)


low_indices = np.where(
    low_spo2
)[0]

oxygen_requirement[low_indices] = np.random.choice(
    [
        "Nasal Cannula",
        "Oxygen Mask",
        "Ventilator"
    ],
    size=len(low_indices),
    p=[
        0.15,
        0.65,
        0.20
    ]
)


very_low_indices = np.where(
    very_low_spo2
)[0]

oxygen_requirement[very_low_indices] = np.random.choice(
    [
        "Oxygen Mask",
        "Ventilator"
    ],
    size=len(very_low_indices),
    p=[
        0.35,
        0.65
    ]
)


# ============================================================
# 23. ARRIVAL MODE
# ============================================================

arrival_mode = choose(
    [
        "Walk-in",
        "Ambulance",
        "Referral"
    ],
    [
        0.55,
        0.35,
        0.10
    ],
    N_PATIENTS
)


# ============================================================
# 24. PATIENT LOCATION
# ============================================================

patient_lat = np.random.uniform(
    CITY_LAT_MIN,
    CITY_LAT_MAX,
    N_PATIENTS
)

patient_lon = np.random.uniform(
    CITY_LON_MIN,
    CITY_LON_MAX,
    N_PATIENTS
)


# ============================================================
# 25. CLINICAL REFERENCE SCORE
# ============================================================
#
# IMPORTANT:
#
# Severity is NOT generated from Clinical_Score.
#
# Clinical_Score is a synthetic rule-based reference score
# derived from observable clinical features.
#
# It should NOT be used as an input feature for the primary
# ML severity model because it already summarizes severity-
# related clinical information.
# ============================================================

clinical_score = (
    (spo2 < 90) * 3

    + ((spo2 >= 90) &
       (spo2 < 94)) * 1

    + ((heart_rate < 50) |
       (heart_rate > 130)) * 2

    + (systolic_bp < 90) * 3

    + (systolic_bp > 180) * 1

    + ((respiratory_rate < 10) |
       (respiratory_rate > 30)) * 2

    + respiratory_distress * 3

    + (gcs <= 8) * 4

    + ((gcs > 8) &
       (gcs <= 12)) * 2

    + seizure * 2

    + bleeding * 2

    + (pain_score >= 8) * 1

    + (oxygen_requirement == "Ventilator") * 5

    + (oxygen_requirement == "Oxygen Mask") * 2
)


# ============================================================
# 26. AMBULANCE PRIORITY
# ============================================================
#
# Priority is deterministically derived from Severity.
#
# P1 = Critical
# P2 = Emergency
# P3 = Moderate
# P4 = Low
# P5 = Non-Urgent
#
# This is used by the dispatch system and must NOT be used
# as an input feature for the severity ML model.
# ============================================================

ambulance_priority = np.empty(
    N_PATIENTS,
    dtype=object
)

ambulance_priority[
    latent_severity == 4
] = "P1"

ambulance_priority[
    latent_severity == 3
] = "P2"

ambulance_priority[
    latent_severity == 2
] = "P3"

ambulance_priority[
    latent_severity == 1
] = "P4"

ambulance_priority[
    latent_severity == 0
] = "P5"


# ============================================================
# 27. PATIENT DATASET
# ============================================================

patients = pd.DataFrame({

    "Incident_ID": incident_id,

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

    "Arrival_Mode": arrival_mode,

    "Patient_Lat": patient_lat,

    "Patient_Lon": patient_lon,

    "Clinical_Score": clinical_score,

    "Severity": severity,

    "Ambulance_Priority": ambulance_priority
})


# ============================================================
# 28. AMBULANCES
# ============================================================

ambulance_ids = [
    f"AMB_{i:04d}"
    for i in range(1, N_AMBULANCES + 1)
]

ambulance_type = choose(
    [
        "Basic Life Support",
        "Advanced Life Support",
        "Critical Care"
    ],
    [
        0.45,
        0.40,
        0.15
    ],
    N_AMBULANCES
)

ambulance_lat = np.random.uniform(
    CITY_LAT_MIN,
    CITY_LAT_MAX,
    N_AMBULANCES
)

ambulance_lon = np.random.uniform(
    CITY_LON_MIN,
    CITY_LON_MAX,
    N_AMBULANCES
)

availability = choose(
    [
        "Available",
        "Busy",
        "Maintenance"
    ],
    [
        0.70,
        0.25,
        0.05
    ],
    N_AMBULANCES
)

ambulances = pd.DataFrame({

    "Ambulance_ID": ambulance_ids,

    "Ambulance_Type": ambulance_type,

    "Latitude": ambulance_lat,

    "Longitude": ambulance_lon,

    "Availability": availability
})


# ============================================================
# 29. HOSPITALS
# ============================================================

hospital_ids = [
    f"HOSP_{i:03d}"
    for i in range(1, N_HOSPITALS + 1)
]

hospital_lat = np.random.uniform(
    CITY_LAT_MIN,
    CITY_LAT_MAX,
    N_HOSPITALS
)

hospital_lon = np.random.uniform(
    CITY_LON_MIN,
    CITY_LON_MAX,
    N_HOSPITALS
)

hospital_type = choose(
    [
        "General",
        "Trauma Center",
        "Cardiac Center",
        "Specialty Hospital"
    ],
    [
        0.50,
        0.25,
        0.15,
        0.10
    ],
    N_HOSPITALS
)

hospital_capacity = np.random.randint(
    50,
    500,
    N_HOSPITALS
)

current_load = np.array([
    np.random.randint(
        10,
        capacity + 1
    )
    for capacity in hospital_capacity
])

icu_capacity = np.random.randint(
    5,
    50,
    N_HOSPITALS
)

current_icu_load = np.array([
    np.random.randint(
        0,
        capacity + 1
    )
    for capacity in icu_capacity
])

hospitals = pd.DataFrame({

    "Hospital_ID": hospital_ids,

    "Hospital_Type": hospital_type,

    "Latitude": hospital_lat,

    "Longitude": hospital_lon,

    "Hospital_Capacity": hospital_capacity,

    "Current_Load": current_load,

    "ICU_Capacity": icu_capacity,

    "Current_ICU_Load": current_icu_load
})


# ============================================================
# 30. DISPATCH SCENARIOS
# ============================================================

scenario_rows = []

available_ambulances = ambulances[
    ambulances["Availability"] == "Available"
]


for incident in patients.itertuples():

    selected_ambulances = available_ambulances.sample(
        min(
            SCENARIOS_PER_INCIDENT,
            len(available_ambulances)
        ),
        replace=False
    )

    for ambulance in selected_ambulances.itertuples():

        # ----------------------------------------------------
        # Distance
        # ----------------------------------------------------

        lat_difference = (
            incident.Patient_Lat -
            ambulance.Latitude
        )

        lon_difference = (
            incident.Patient_Lon -
            ambulance.Longitude
        )

        distance = (
            np.sqrt(
                lat_difference ** 2 +
                lon_difference ** 2
            ) * 111
        )


        # ----------------------------------------------------
        # Traffic
        # ----------------------------------------------------

        traffic_level = choose(
            [
                "Low",
                "Moderate",
                "High",
                "Severe"
            ],
            [
                0.30,
                0.35,
                0.25,
                0.10
            ],
            1
        )[0]

        traffic_multiplier = {

            "Low": 1.00,

            "Moderate": 1.25,

            "High": 1.60,

            "Severe": 2.10

        }[traffic_level]


        # ----------------------------------------------------
        # Road condition
        # ----------------------------------------------------

        road_condition = choose(
            [
                "Good",
                "Average",
                "Poor"
            ],
            [
                0.60,
                0.30,
                0.10
            ],
            1
        )[0]

        road_multiplier = {

            "Good": 1.00,

            "Average": 1.15,

            "Poor": 1.35

        }[road_condition]


        # ----------------------------------------------------
        # Base speed
        # ----------------------------------------------------

        base_speed = np.random.uniform(
            30,
            55
        )


        # ----------------------------------------------------
        # Effective speed
        # ----------------------------------------------------

        effective_speed = (
            base_speed
            / traffic_multiplier
            / road_multiplier
        )


        # ----------------------------------------------------
        # ETA
        # ----------------------------------------------------

        eta_minutes = (
            distance /
            effective_speed
        ) * 60

        eta_minutes += np.random.normal(
            0,
            1.5
        )

        eta_minutes = max(
            eta_minutes,
            1
        )


        # ----------------------------------------------------
        # Capability
        # ----------------------------------------------------

        if incident.Severity == "Critical":

            capability_match = (
                ambulance.Ambulance_Type
                in [
                    "Advanced Life Support",
                    "Critical Care"
                ]
            )

        elif incident.Severity == "Emergency":

            capability_match = (
                ambulance.Ambulance_Type
                != "Basic Life Support"
            )

        else:

            capability_match = True


        # ----------------------------------------------------
        # Dispatch score
        # ----------------------------------------------------

        if capability_match:

            dispatch_score = eta_minutes

        else:

            dispatch_score = (
                eta_minutes + 20
            )


        scenario_rows.append({

            "Incident_ID": incident.Incident_ID,

            "Ambulance_ID": ambulance.Ambulance_ID,

            "Patient_Severity": incident.Severity,

            "Ambulance_Type": ambulance.Ambulance_Type,

            "Distance_KM": round(
                distance,
                2
            ),

            "Traffic_Level": traffic_level,

            "Road_Condition": road_condition,

            "Base_Speed_KMH": round(
                base_speed,
                2
            ),

            "Predicted_ETA_Minutes": round(
                eta_minutes,
                2
            ),

            "Capability_Match": capability_match,

            "Dispatch_Score": round(
                dispatch_score,
                2
            )
        })


# ============================================================
# 31. DISPATCH DATAFRAME
# ============================================================

dispatch = pd.DataFrame(
    scenario_rows
)


# ============================================================
# 32. SELECT BEST AMBULANCE
# ============================================================

dispatch["Selected"] = False

best_indices = (
    dispatch
    .groupby("Incident_ID")["Dispatch_Score"]
    .idxmin()
)

dispatch.loc[
    best_indices,
    "Selected"
] = True


# ============================================================
# 33. FINAL VALIDATION
# ============================================================

print("\n" + "=" * 70)
print("FINAL DATA VALIDATION")
print("=" * 70)


datasets = {
    "Patients": patients,
    "Ambulances": ambulances,
    "Hospitals": hospitals,
    "Dispatch": dispatch
}


# ------------------------------------------------------------
# Missing values
# ------------------------------------------------------------

print("\nMissing values:")

for name, dataframe in datasets.items():

    missing = (
        dataframe
        .isnull()
        .sum()
        .sum()
    )

    print(
        f"{name}: {missing}"
    )


# ------------------------------------------------------------
# Duplicate rows
# ------------------------------------------------------------

print("\nDuplicate rows:")

for name, dataframe in datasets.items():

    duplicates = (
        dataframe
        .duplicated()
        .sum()
    )

    print(
        f"{name}: {duplicates}"
    )


# ------------------------------------------------------------
# Expected dataset sizes
# ------------------------------------------------------------

assert len(patients) == N_PATIENTS

assert len(ambulances) == N_AMBULANCES

assert len(hospitals) == N_HOSPITALS

assert len(dispatch) == (
    N_PATIENTS *
    SCENARIOS_PER_INCIDENT
)


# ------------------------------------------------------------
# Expected severity labels
# ------------------------------------------------------------

assert set(
    patients["Severity"].unique()
).issubset(
    set(severity_labels)
)


# ------------------------------------------------------------
# Priority validation
# ------------------------------------------------------------

priority_mapping = {
    "Critical": "P1",
    "Emergency": "P2",
    "Moderate": "P3",
    "Low": "P4",
    "Non-Urgent": "P5"
}

expected_priority = (
    patients["Severity"]
    .map(priority_mapping)
)

assert (
    patients["Ambulance_Priority"]
    == expected_priority
).all()


# ------------------------------------------------------------
# Injury validation
# ------------------------------------------------------------

assert (
    patients["Injury_Type"]
    .isnull()
    .sum()
    == 0
)


# ------------------------------------------------------------
# Oxygen validation
# ------------------------------------------------------------

assert (
    patients["Oxygen_Requirement"]
    .isnull()
    .sum()
    == 0
)


# ------------------------------------------------------------
# Selected ambulance validation
# ------------------------------------------------------------

selected_per_incident = (
    dispatch
    .groupby("Incident_ID")["Selected"]
    .sum()
)

assert (
    selected_per_incident == 1
).all()


# ------------------------------------------------------------
# Duplicate validation
# ------------------------------------------------------------

for dataframe in datasets.values():

    assert (
        dataframe
        .duplicated()
        .sum()
        == 0
    )


# ------------------------------------------------------------
# Missing-value validation
# ------------------------------------------------------------

for dataframe in datasets.values():

    assert (
        dataframe
        .isnull()
        .sum()
        .sum()
        == 0
    )


print("\n✓ Dataset sizes are valid.")

print("✓ No missing values.")

print("✓ No duplicate rows.")

print("✓ Severity labels are valid.")

print("✓ Ambulance priorities match severity.")

print("✓ Injury values are valid.")

print("✓ Oxygen values are valid.")

print("✓ Exactly one ambulance is selected per incident.")

print("✓ All validation checks passed.")


# ============================================================
# 34. SAVE DATASETS
# ============================================================

patients.to_csv(
    DATA_DIR / "patient_incidents.csv",
    index=False
)

ambulances.to_csv(
    DATA_DIR / "ambulances.csv",
    index=False
)

hospitals.to_csv(
    DATA_DIR / "hospitals.csv",
    index=False
)

dispatch.to_csv(
    DATA_DIR / "dispatch_scenarios.csv",
    index=False
)


# ============================================================
# 35. SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("SYNTHETIC EMS DATASET GENERATED")
print("=" * 70)

print("\nDataset sizes:")

print(
    "Patients:",
    patients.shape
)

print(
    "Ambulances:",
    ambulances.shape
)

print(
    "Hospitals:",
    hospitals.shape
)

print(
    "Dispatch scenarios:",
    dispatch.shape
)


# ============================================================
# OVERALL SEVERITY
# ============================================================

print("\n" + "=" * 70)
print("OVERALL SEVERITY DISTRIBUTION")
print("=" * 70)

print(
    patients["Severity"]
    .value_counts()
)


# ============================================================
# CONDITION × SEVERITY
# ============================================================

print("\n" + "=" * 70)
print("CONDITION × SEVERITY (%)")
print("=" * 70)

condition_severity_table = pd.crosstab(
    patients["Condition"],
    patients["Severity"],
    normalize="index"
) * 100

print(
    condition_severity_table
    .round(2)
)


# ============================================================
# IMPORTANT CLINICAL RELATIONSHIPS
# ============================================================

print("\n" + "=" * 70)
print("AVERAGE VITALS BY SEVERITY")
print("=" * 70)

print(
    patients.groupby("Severity")[
        [
            "Heart_Rate",
            "SpO2",
            "Systolic_BP",
            "Respiratory_Rate",
            "GCS",
            "Pain_Score"
        ]
    ]
    .mean()
    .round(2)
)


# ============================================================
# DISPATCH VALIDATION SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("DISPATCH VALIDATION")
print("=" * 70)

print(
    "Total scenarios:",
    len(dispatch)
)

print(
    "Selected:",
    dispatch["Selected"].sum()
)

print(
    "Unselected:",
    (~dispatch["Selected"]).sum()
)


# ============================================================
# FILES
# ============================================================

print("\n" + "=" * 70)
print("FILES CREATED")
print("=" * 70)

print(
    DATA_DIR / "patient_incidents.csv"
)

print(
    DATA_DIR / "ambulances.csv"
)

print(
    DATA_DIR / "hospitals.csv"
)

print(
    DATA_DIR / "dispatch_scenarios.csv"
)

print("\n✓ Generation complete.")