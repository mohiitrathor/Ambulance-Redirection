from pathlib import Path

import joblib
import numpy as np
import pandas as pd


# ==============================================================
# PATHS
# ==============================================================

ROOT = Path(__file__).resolve().parents[1]

DATASET_DIR = ROOT / "Dataset"

PATIENTS_PATH = DATASET_DIR / "patient_incidents.csv"
AMBULANCES_PATH = DATASET_DIR / "ambulances.csv"
SCENARIOS_PATH = DATASET_DIR / "dispatch_scenarios.csv"
HOSPITALS_PATH = DATASET_DIR / "hospitals.csv"

MODEL_PATH = (
    ROOT
    / "Models"
    / "Final Model"
    / "logistic_regression_final.joblib"
)


# ==============================================================
# CONSTANTS
# ==============================================================

SEVERITY_PRIORITY = {
    "Critical": 1,
    "Emergency": 2,
    "Moderate": 3,
    "Low": 4,
    "Non-Urgent": 5,
}

AMBULANCE_CAPABILITY = {
    "Basic Life Support": 1,
    "Advanced Life Support": 2,
    "Critical Care": 3,
}


# ==============================================================
# DATA LOADING
# ==============================================================

def load_data():

    patients = pd.read_csv(
        PATIENTS_PATH
    )

    ambulances = pd.read_csv(
        AMBULANCES_PATH
    )

    scenarios = pd.read_csv(
        SCENARIOS_PATH
    )

    hospitals = pd.read_csv(
        HOSPITALS_PATH
    )

    model = joblib.load(
        MODEL_PATH
    )

    return (
        patients,
        ambulances,
        scenarios,
        hospitals,
        model,
    )


# ==============================================================
# SEVERITY
# ==============================================================

def required_ambulance_level(
    severity,
):
    """
    Determine the minimum ambulance
    capability required for a predicted
    severity.
    """

    return {
        "Critical": 2,
        "Emergency": 2,
        "Moderate": 1,
        "Low": 1,
        "Non-Urgent": 1,
    }.get(
        str(severity),
        1,
    )


def predict_severity(
    model,
    incident,
):
    """
    Predict incident severity using the
    trained ML model.

    Returns:
        predicted_severity
        confidence
        probabilities
    """

    prediction = model.predict(
        incident
    )[0]

    confidence = None
    probabilities = None

    if hasattr(
        model,
        "predict_proba",
    ):

        probabilities = (
            model.predict_proba(
                incident
            )[0]
        )

        confidence = float(
            np.max(probabilities)
        )

    return (
        str(prediction),
        confidence,
        probabilities,
    )


# ==============================================================
# AMBULANCE SELECTION
# ==============================================================

def select_ambulance(
    predicted_severity,
    incident_id,
    ambulances,
    scenarios,
):
    """
    Select the best available ambulance
    for an incident.

    Capability matching is preferred.
    If no compatible ambulance exists,
    the fastest available ambulance is
    returned as a fallback.
    """

    candidates = scenarios[
        scenarios["Incident_ID"]
        == incident_id
    ].copy()

    if candidates.empty:

        raise ValueError(
            f"No dispatch scenarios found "
            f"for Incident_ID={incident_id}"
        )

    # Keep only the fleet columns needed
    # for availability and capability.
    fleet = ambulances[
        [
            "Ambulance_ID",
            "Ambulance_Type",
            "Availability",
        ]
    ].copy()

    # Avoid duplicate Ambulance_Type
    # columns if the scenario dataset
    # already contains one.
    candidates = candidates.drop(
        columns=[
            "Ambulance_Type",
        ],
        errors="ignore",
    )

    candidates = candidates.merge(
        fleet,
        on="Ambulance_ID",
        how="inner",
    )

    # Only currently available ambulances.
    candidates = candidates[
        candidates[
            "Availability"
        ]
        .astype(str)
        .str.upper()
        == "AVAILABLE"
    ].copy()

    if candidates.empty:

        return (
            None,
            pd.DataFrame(),
        )

    required_level = (
        required_ambulance_level(
            predicted_severity
        )
    )

    candidates[
        "Capability_Level"
    ] = (
        candidates[
            "Ambulance_Type"
        ]
        .map(
            AMBULANCE_CAPABILITY
        )
        .fillna(0)
    )

    candidates[
        "Capability_Match"
    ] = (
        candidates[
            "Capability_Level"
        ]
        >= required_level
    )

    compatible = candidates[
        candidates[
            "Capability_Match"
        ]
    ].copy()

    # ----------------------------------------------------------
    # CAPABILITY FIRST
    # ----------------------------------------------------------

    fallback = compatible.empty

    if not fallback:

        candidates = compatible

    # ----------------------------------------------------------
    # ETA FIRST, DISTANCE SECOND
    # ----------------------------------------------------------

    candidates = candidates.sort_values(
        by=[
            "Predicted_ETA_Minutes",
            "Distance_KM",
        ],
        ascending=[
            True,
            True,
        ],
    ).reset_index(
        drop=True
    )

    candidates[
        "Fallback"
    ] = fallback

    return (
        candidates.iloc[0].copy(),
        candidates,
    )


# ==============================================================
# HOSPITAL SUITABILITY
# ==============================================================

def hospital_suitability(
    condition,
    hospital_type,
):
    """
    Score hospital suitability based on
    patient condition and hospital type.

    3 = highly suitable
    2 = suitable
    1 = general/low suitability
    """

    condition = str(
        condition
    )

    hospital_type = str(
        hospital_type
    )

    if condition == "Cardiac":

        if hospital_type == "Cardiac Center":
            return 3

        if hospital_type in {
            "Specialty Hospital",
            "General",
        }:
            return 2

        return 1

    if condition == "Trauma":

        if hospital_type == "Trauma Center":
            return 3

        if hospital_type in {
            "Specialty Hospital",
            "General",
        }:
            return 2

        return 1

    if condition in {
        "Neurological",
        "Respiratory",
    }:

        if hospital_type == "Specialty Hospital":
            return 3

        if hospital_type == "General":
            return 2

        return 1

    if hospital_type == "General":
        return 3

    if hospital_type == "Specialty Hospital":
        return 2

    return 1


# ==============================================================
# HOSPITAL SELECTION
# ==============================================================

def select_hospital(
    predicted_severity,
    condition,
    patient_lat,
    patient_lon,
    hospitals,
):
    """
    Select the most suitable hospital.

    Priority:
        1. Hospital suitability
        2. Distance
        3. ICU availability
        4. Bed availability

    Critical incidents require ICU availability.
    """

    candidates = hospitals.copy()

    # ----------------------------------------------------------
    # CAPACITY
    # ----------------------------------------------------------

    candidates[
        "Available_Beds"
    ] = (
        candidates[
            "Hospital_Capacity"
        ]
        - candidates[
            "Current_Load"
        ]
    ).clip(
        lower=0
    )

    candidates[
        "Available_ICU"
    ] = (
        candidates[
            "ICU_Capacity"
        ]
        - candidates[
            "Current_ICU_Load"
        ]
    ).clip(
        lower=0
    )

    # ----------------------------------------------------------
    # DISTANCE
    #
    # Approximation for initial simulation.
    # The live system can later replace this
    # with a routing API.
    # ----------------------------------------------------------

    lat_difference = (
        float(patient_lat)
        - candidates["Latitude"]
    )

    lon_difference = (
        float(patient_lon)
        - candidates["Longitude"]
    )

    candidates[
        "Distance_KM"
    ] = (
        np.sqrt(
            lat_difference ** 2
            + lon_difference ** 2
        )
        * 111
    )

    # ----------------------------------------------------------
    # SUITABILITY
    # ----------------------------------------------------------

    candidates[
        "Suitability"
    ] = candidates[
        "Hospital_Type"
    ].apply(
        lambda hospital_type:
        hospital_suitability(
            condition,
            hospital_type,
        )
    )

    # ----------------------------------------------------------
    # BED AVAILABILITY
    # ----------------------------------------------------------

    candidates = candidates[
        candidates[
            "Available_Beds"
        ] > 0
    ].copy()

    # ----------------------------------------------------------
    # ICU REQUIREMENT
    # ----------------------------------------------------------

    if predicted_severity == "Critical":

        candidates = candidates[
            candidates[
                "Available_ICU"
            ] > 0
        ].copy()

    if candidates.empty:

        return (
            None,
            pd.DataFrame(),
        )

    # ----------------------------------------------------------
    # RANK
    # ----------------------------------------------------------

    candidates = candidates.sort_values(
        by=[
            "Suitability",
            "Distance_KM",
            "Available_ICU",
            "Available_Beds",
        ],
        ascending=[
            False,
            True,
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )

    return (
        candidates.iloc[0].copy(),
        candidates,
    )


# ==============================================================
# MAIN DISPATCH FUNCTION
# ==============================================================

def dispatch_incident(
    incident_id,
):
    """
    Run the complete initial dispatch pipeline.

    ML
      ↓
    Severity prediction
      ↓
    Ambulance selection
      ↓
    Hospital selection
      ↓
    Dispatch result
    """

    (
        patients,
        ambulances,
        scenarios,
        hospitals,
        model,
    ) = load_data()

    # ----------------------------------------------------------
    # FIND INCIDENT
    # ----------------------------------------------------------

    incident_rows = patients[
        patients[
            "Incident_ID"
        ]
        == incident_id
    ].copy()

    if incident_rows.empty:

        raise ValueError(
            f"Incident_ID={incident_id} "
            f"was not found."
        )

    incident = (
        incident_rows.iloc[0]
    )

    # ----------------------------------------------------------
    # MODEL INPUT
    # ----------------------------------------------------------

    model_columns = getattr(
        model,
        "feature_names_in_",
        None,
    )

    if model_columns is None:

        raise ValueError(
            "Saved model does not contain "
            "feature_names_in_."
        )

    missing_features = [
        column
        for column in model_columns
        if column not in incident_rows.columns
    ]

    if missing_features:

        raise ValueError(
            "Missing model features: "
            + ", ".join(
                missing_features
            )
        )

    model_input = incident_rows[
        list(model_columns)
    ]

    # ----------------------------------------------------------
    # ML PREDICTION
    # ----------------------------------------------------------

    (
        predicted_severity,
        confidence,
        probabilities,
    ) = predict_severity(
        model,
        model_input,
    )

    priority_number = (
        SEVERITY_PRIORITY.get(
            predicted_severity,
            5,
        )
    )

    # ----------------------------------------------------------
    # AMBULANCE
    # ----------------------------------------------------------

    (
        selected_ambulance,
        ambulance_candidates,
    ) = select_ambulance(
        predicted_severity,
        incident_id,
        ambulances,
        scenarios,
    )

    # ----------------------------------------------------------
    # NO AMBULANCE
    # ----------------------------------------------------------

    if selected_ambulance is None:

        return {

            "status":
                "NO_AMBULANCE_AVAILABLE",

            "incident_id":
                int(incident_id),

            "predicted_severity":
                predicted_severity,

            "confidence":
                confidence,

            "patient": {

                "condition":
                    str(
                        incident[
                            "Condition"
                        ]
                    ),

                "predicted_severity":
                    predicted_severity,

                "priority":
                    f"P{priority_number}",

                "confidence":
                    confidence,
            },

            "ambulance":
                None,

            "hospital":
                None,
        }

    # ----------------------------------------------------------
    # HOSPITAL
    # ----------------------------------------------------------

    (
        selected_hospital,
        hospital_candidates,
    ) = select_hospital(

        predicted_severity,

        str(
            incident[
                "Condition"
            ]
        ),

        float(
            incident[
                "Patient_Lat"
            ]
        ),

        float(
            incident[
                "Patient_Lon"
            ]
        ),

        hospitals,
    )

    # ----------------------------------------------------------
    # BUILD RESULT
    # ----------------------------------------------------------

    result = {

        "status":
            "DISPATCH_RECOMMENDED",

        "incident_id":
            int(incident_id),

        "patient": {

            "condition":
                str(
                    incident[
                        "Condition"
                    ]
                ),

            "predicted_severity":
                predicted_severity,

            "priority":
                f"P{priority_number}",

            "confidence":
                confidence,
        },

        "ambulance": {

            "ambulance_id":
                str(
                    selected_ambulance[
                        "Ambulance_ID"
                    ]
                ),

            "ambulance_type":
                str(
                    selected_ambulance[
                        "Ambulance_Type"
                    ]
                ),

            "eta_minutes":
                float(
                    selected_ambulance[
                        "Predicted_ETA_Minutes"
                    ]
                ),

            "distance_km":
                float(
                    selected_ambulance[
                        "Distance_KM"
                    ]
                ),

            "traffic":
                str(
                    selected_ambulance.get(
                        "Traffic_Level",
                        "NORMAL",
                    )
                ),

            "road_condition":
                str(
                    selected_ambulance.get(
                        "Road_Condition",
                        "GOOD",
                    )
                ),

            "capability_match":
                bool(
                    selected_ambulance[
                        "Capability_Match"
                    ]
                ),

            "fallback":
                bool(
                    selected_ambulance[
                        "Fallback"
                    ]
                ),
        },

        "hospital":
            None,
    }

    # ----------------------------------------------------------
    # HOSPITAL RESULT
    # ----------------------------------------------------------

    if selected_hospital is not None:

        result[
            "hospital"
        ] = {

            "hospital_id":
                str(
                    selected_hospital[
                        "Hospital_ID"
                    ]
                ),

            "hospital_type":
                str(
                    selected_hospital[
                        "Hospital_Type"
                    ]
                ),

            "distance_km":
                float(
                    selected_hospital[
                        "Distance_KM"
                    ]
                ),

            "available_beds":
                int(
                    selected_hospital[
                        "Available_Beds"
                    ]
                ),

            "available_icu":
                int(
                    selected_hospital[
                        "Available_ICU"
                    ]
                ),

            "suitability":
                int(
                    selected_hospital[
                        "Suitability"
                    ]
                ),
        }

    else:

        result["status"] = (
            "NO_SUITABLE_HOSPITAL"
        )

    return result


# ==============================================================
# PRINT DISPATCH
# ==============================================================

def print_dispatch(
    result,
):

    print()
    print("=" * 70)
    print("DISPATCH DECISION")
    print("=" * 70)

    print(
        f"Incident:       "
        f"#{result['incident_id']}"
    )

    patient = result.get(
        "patient",
        {},
    )

    print(
        f"Condition:      "
        f"{patient.get('condition', '-')}"
    )

    print(
        f"Severity:       "
        f"{patient.get('predicted_severity', '-')}"
    )

    print(
        f"Priority:       "
        f"{patient.get('priority', '-')}"
    )

    confidence = (
        patient.get(
            "confidence"
        )
    )

    if confidence is not None:

        print(
            f"Confidence:     "
            f"{confidence:.2%}"
        )

    ambulance = result.get(
        "ambulance"
    )

    if ambulance:

        print()
        print("AMBULANCE")
        print("-" * 70)

        print(
            f"ID:             "
            f"{ambulance['ambulance_id']}"
        )

        print(
            f"Type:           "
            f"{ambulance['ambulance_type']}"
        )

        print(
            f"ETA:            "
            f"{ambulance['eta_minutes']:.1f} min"
        )

        print(
            f"Distance:       "
            f"{ambulance['distance_km']:.2f} km"
        )

        print(
            f"Capability:     "
            f"{'MATCH' if ambulance['capability_match'] else 'FALLBACK'}"
        )

        print(
            f"Traffic:        "
            f"{ambulance['traffic']}"
        )

        print(
            f"Road:           "
            f"{ambulance['road_condition']}"
        )

    else:

        print()
        print(
            "AMBULANCE: NONE AVAILABLE"
        )

    hospital = result.get(
        "hospital"
    )

    if hospital:

        print()
        print("HOSPITAL")
        print("-" * 70)

        print(
            f"ID:             "
            f"{hospital['hospital_id']}"
        )

        print(
            f"Type:           "
            f"{hospital['hospital_type']}"
        )

        print(
            f"Distance:       "
            f"{hospital['distance_km']:.2f} km"
        )

        print(
            f"Available beds: "
            f"{hospital['available_beds']}"
        )

        print(
            f"Available ICU:  "
            f"{hospital['available_icu']}"
        )

        print(
            f"Suitability:    "
            f"{hospital['suitability']}/3"
        )

    else:

        print()
        print(
            "HOSPITAL: NONE SUITABLE"
        )

    print()
    print(
        f"Status:         "
        f"{result['status']}"
    )

    print("=" * 70)


# ==============================================================
# DIRECT TEST
# ==============================================================

if __name__ == "__main__":

    result = dispatch_incident(
        1
    )

    print_dispatch(
        result
    )
