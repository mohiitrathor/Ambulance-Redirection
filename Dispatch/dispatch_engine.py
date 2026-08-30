from pathlib import Path

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

DATASET_DIR = ROOT / "Dataset"

MODEL_PATH = (
    ROOT
    / "Models"
    / "Final Model"
    / "logistic_regression_final.joblib"
)

PATIENTS_PATH = DATASET_DIR / "patient_incidents.csv"
AMBULANCES_PATH = DATASET_DIR / "ambulances.csv"
SCENARIOS_PATH = DATASET_DIR / "dispatch_scenarios.csv"
HOSPITALS_PATH = DATASET_DIR / "hospitals.csv"


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


def load_data():

    patients = pd.read_csv(PATIENTS_PATH)
    ambulances = pd.read_csv(AMBULANCES_PATH)
    scenarios = pd.read_csv(SCENARIOS_PATH)
    hospitals = pd.read_csv(HOSPITALS_PATH)

    model = joblib.load(MODEL_PATH)

    return (
        patients,
        ambulances,
        scenarios,
        hospitals,
        model,
    )


def required_ambulance_level(severity):

    return {
        "Critical": 2,
        "Emergency": 2,
        "Moderate": 1,
        "Low": 1,
        "Non-Urgent": 1,
    }[severity]


def predict_severity(model, incident):

    prediction = model.predict(incident)[0]

    confidence = None
    probabilities = None

    if hasattr(model, "predict_proba"):

        probabilities = model.predict_proba(incident)[0]

        confidence = float(
            np.max(probabilities)
        )

    return (
        str(prediction),
        confidence,
        probabilities,
    )


def select_ambulance(
    predicted_severity,
    incident_id,
    ambulances,
    scenarios,
):

    candidates = scenarios[
        scenarios["Incident_ID"] == incident_id
    ].copy()

    if candidates.empty:

        raise ValueError(
            f"No dispatch scenarios found for "
            f"Incident_ID={incident_id}"
        )

    fleet = ambulances[
        [
            "Ambulance_ID",
            "Ambulance_Type",
            "Availability",
        ]
    ].copy()

    candidates = candidates.drop(
        columns=["Ambulance_Type"],
        errors="ignore",
    )

    candidates = candidates.merge(
        fleet,
        on="Ambulance_ID",
        how="inner",
    )

    candidates = candidates[
        candidates["Availability"] == "Available"
    ].copy()

    if candidates.empty:

        return (
            None,
            pd.DataFrame(),
        )

    required_level = required_ambulance_level(
        predicted_severity
    )

    candidates["Capability_Level"] = (
        candidates["Ambulance_Type"]
        .map(AMBULANCE_CAPABILITY)
        .fillna(0)
    )

    candidates["Capability_Match"] = (
        candidates["Capability_Level"]
        >= required_level
    )

    compatible = candidates[
        candidates["Capability_Match"]
    ].copy()

    fallback = compatible.empty

    if not fallback:
        candidates = compatible

    candidates = candidates.sort_values(
        by=[
            "Predicted_ETA_Minutes",
            "Distance_KM",
        ],
        ascending=[
            True,
            True,
        ],
    ).reset_index(drop=True)

    candidates["Fallback"] = fallback

    selected = candidates.iloc[0].copy()

    return (
        selected,
        candidates,
    )


def hospital_suitability(
    condition,
    hospital_type,
):

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


def select_hospital(
    predicted_severity,
    condition,
    patient_lat,
    patient_lon,
    hospitals,
):

    candidates = hospitals.copy()

    candidates["Available_Beds"] = (
        candidates["Hospital_Capacity"]
        - candidates["Current_Load"]
    ).clip(lower=0)

    candidates["Available_ICU"] = (
        candidates["ICU_Capacity"]
        - candidates["Current_ICU_Load"]
    ).clip(lower=0)

    lat_difference = (
        patient_lat
        - candidates["Latitude"]
    )

    lon_difference = (
        patient_lon
        - candidates["Longitude"]
    )

    candidates["Distance_KM"] = (
        np.sqrt(
            lat_difference ** 2
            + lon_difference ** 2
        )
        * 111
    )

    candidates["Suitability"] = (
        candidates["Hospital_Type"]
        .apply(
            lambda hospital_type:
                hospital_suitability(
                    condition,
                    hospital_type,
                )
        )
    )

    candidates = candidates[
        candidates["Available_Beds"] > 0
    ].copy()

    if predicted_severity == "Critical":

        candidates = candidates[
            candidates["Available_ICU"] > 0
        ].copy()

    if candidates.empty:

        return (
            None,
            pd.DataFrame(),
        )

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
    ).reset_index(drop=True)

    selected = candidates.iloc[0].copy()

    return (
        selected,
        candidates,
    )


def dispatch_incident(incident_id):

    (
        patients,
        ambulances,
        scenarios,
        hospitals,
        model,
    ) = load_data()

    incident_rows = patients[
        patients["Incident_ID"] == incident_id
    ].copy()

    if incident_rows.empty:

        raise ValueError(
            f"Incident_ID={incident_id} was not found"
        )

    model_columns = getattr(
        model,
        "feature_names_in_",
        None,
    )

    if model_columns is None:

        raise ValueError(
            "The saved model does not contain "
            "feature_names_in_"
        )

    missing_features = [
        column
        for column in model_columns
        if column not in incident_rows.columns
    ]

    if missing_features:

        raise ValueError(
            "Missing model features: "
            + ", ".join(missing_features)
        )

    incident = incident_rows.iloc[0]

    model_input = incident_rows[
        list(model_columns)
    ]

    (
        predicted_severity,
        confidence,
        probabilities,
    ) = predict_severity(
        model,
        model_input,
    )

    (
        selected_ambulance,
        ambulance_candidates,
    ) = select_ambulance(
        predicted_severity,
        incident_id,
        ambulances,
        scenarios,
    )

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

            "ambulance":
                None,

            "hospital":
                None,
        }

    (
        selected_hospital,
        hospital_candidates,
    ) = select_hospital(
        predicted_severity,
        str(
            incident["Condition"]
        ),
        float(
            incident["Patient_Lat"]
        ),
        float(
            incident["Patient_Lon"]
        ),
        hospitals,
    )

    result = {

        "status":
            "DISPATCH_RECOMMENDED",

        "incident_id":
            int(incident_id),

        "patient": {

            "condition":
                str(
                    incident["Condition"]
                ),

            "predicted_severity":
                predicted_severity,

            "priority":
                f"P{SEVERITY_PRIORITY[predicted_severity]}",

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
                    selected_ambulance[
                        "Traffic_Level"
                    ]
                ),

            "road_condition":
                str(
                    selected_ambulance[
                        "Road_Condition"
                    ]
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

    if selected_hospital is not None:

        result["hospital"] = {

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

    result["ambulance_candidates"] = (
        ambulance_candidates[
            [
                "Ambulance_ID",
                "Ambulance_Type",
                "Predicted_ETA_Minutes",
                "Distance_KM",
                "Traffic_Level",
                "Road_Condition",
                "Capability_Match",
                "Fallback",
            ]
        ]
        .head(10)
        .to_dict(
            orient="records"
        )
    )

    result["hospital_candidates"] = (
        hospital_candidates[
            [
                "Hospital_ID",
                "Hospital_Type",
                "Distance_KM",
                "Available_Beds",
                "Available_ICU",
                "Suitability",
            ]
        ]
        .head(10)
        .to_dict(
            orient="records"
        )
        if not hospital_candidates.empty
        else []
    )

    if probabilities is not None:

        result[
            "severity_probabilities"
        ] = {

            str(label):
                float(probability)

            for label, probability
            in zip(
                model.classes_,
                probabilities,
            )
        }

    return result


def print_dispatch(result):

    print("=" * 70)
    print(
        "AMBULANCE DISPATCH ENGINE"
    )
    print("=" * 70)

    print(
        f"Incident:           "
        f"{result['incident_id']}"
    )

    print(
        f"Status:             "
        f"{result['status']}"
    )

    patient = result["patient"]

    print(
        f"Condition:          "
        f"{patient['condition']}"
    )

    print(
        f"Predicted severity: "
        f"{patient['predicted_severity']}"
    )

    print(
        f"Priority:           "
        f"{patient['priority']}"
    )

    if patient["confidence"] is not None:

        print(
            f"ML confidence:      "
            f"{patient['confidence']:.2%}"
        )

    if result["ambulance"]:

        ambulance = result[
            "ambulance"
        ]

        print()
        print(
            "RECOMMENDED AMBULANCE"
        )
        print("-" * 70)

        print(
            f"Ambulance:          "
            f"{ambulance['ambulance_id']}"
        )

        print(
            f"Type:               "
            f"{ambulance['ambulance_type']}"
        )

        print(
            f"ETA:                "
            f"{ambulance['eta_minutes']:.2f} min"
        )

        print(
            f"Distance:           "
            f"{ambulance['distance_km']:.2f} km"
        )

        print(
            f"Traffic:            "
            f"{ambulance['traffic']}"
        )

        print(
            f"Road condition:     "
            f"{ambulance['road_condition']}"
        )

        print(
            f"Capability match:   "
            f"{ambulance['capability_match']}"
        )

        if ambulance["fallback"]:

            print(
                "WARNING:            "
                "No compatible ambulance "
                "was available"
            )

    if result["hospital"]:

        hospital = result[
            "hospital"
        ]

        print()
        print(
            "RECOMMENDED HOSPITAL"
        )
        print("-" * 70)

        print(
            f"Hospital:           "
            f"{hospital['hospital_id']}"
        )

        print(
            f"Type:               "
            f"{hospital['hospital_type']}"
        )

        print(
            f"Distance:           "
            f"{hospital['distance_km']:.2f} km"
        )

        print(
            f"Available beds:     "
            f"{hospital['available_beds']}"
        )

        print(
            f"Available ICU:      "
            f"{hospital['available_icu']}"
        )

        print(
            f"Suitability:        "
            f"{hospital['suitability']}/3"
        )

    print("=" * 70)


if __name__ == "__main__":

    TEST_INCIDENT_ID = 1

    result = dispatch_incident(
        TEST_INCIDENT_ID
    )

    print_dispatch(result)