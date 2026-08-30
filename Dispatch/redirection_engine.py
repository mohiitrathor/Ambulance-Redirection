from pathlib import Path

import numpy as np
import pandas as pd

from dispatch_engine import load_data, hospital_suitability


ROOT = Path(__file__).resolve().parents[1]

DATASET_DIR = ROOT / "Dataset"

HOSPITALS_PATH = DATASET_DIR / "hospitals.csv"


def calculate_hospitals(
    condition,
    severity,
    patient_lat,
    patient_lon,
    hospitals,
):
    hospitals = hospitals.copy()

    hospitals["Available_Beds"] = (
        hospitals["Hospital_Capacity"]
        - hospitals["Current_Load"]
    ).clip(lower=0)

    hospitals["Available_ICU"] = (
        hospitals["ICU_Capacity"]
        - hospitals["Current_ICU_Load"]
    ).clip(lower=0)

    lat_difference = (
        patient_lat - hospitals["Latitude"]
    )

    lon_difference = (
        patient_lon - hospitals["Longitude"]
    )

    hospitals["Distance_KM"] = (
        np.sqrt(
            lat_difference ** 2
            + lon_difference ** 2
        )
        * 111
    )

    hospitals["Suitability"] = (
        hospitals["Hospital_Type"]
        .apply(
            lambda hospital_type:
                hospital_suitability(
                    condition,
                    hospital_type,
                )
        )
    )

    hospitals = hospitals[
        hospitals["Available_Beds"] > 0
    ].copy()

    if severity == "Critical":

        hospitals = hospitals[
            hospitals["Available_ICU"] > 0
        ].copy()

    return hospitals


def find_best_hospital(
    condition,
    severity,
    patient_lat,
    patient_lon,
    hospitals,
    excluded_hospital=None,
):
    candidates = calculate_hospitals(
        condition,
        severity,
        patient_lat,
        patient_lon,
        hospitals,
    )

    if excluded_hospital is not None:

        candidates = candidates[
            candidates["Hospital_ID"]
            != excluded_hospital
        ].copy()

    if candidates.empty:
        return None, candidates

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

    return (
        candidates.iloc[0],
        candidates,
    )


def simulate_hospital_change(
    hospital_id,
    hospitals,
    change="icu_unavailable",
):
    updated = hospitals.copy()

    mask = (
        updated["Hospital_ID"]
        == hospital_id
    )

    if not mask.any():

        raise ValueError(
            f"Hospital {hospital_id} "
            f"was not found."
        )

    if change == "icu_unavailable":

        updated.loc[
            mask,
            "Current_ICU_Load",
        ] = updated.loc[
            mask,
            "ICU_Capacity",
        ]

    elif change == "full":

        updated.loc[
            mask,
            "Current_Load",
        ] = updated.loc[
            mask,
            "Hospital_Capacity",
        ]

    else:

        raise ValueError(
            "Unknown hospital change."
        )

    return updated


def check_redirection(
    incident_id,
    current_hospital_id,
    change="icu_unavailable",
):
    (
        patients,
        ambulances,
        scenarios,
        hospitals,
        model,
    ) = load_data()

    incident_rows = patients[
        patients["Incident_ID"]
        == incident_id
    ].copy()

    if incident_rows.empty:

        raise ValueError(
            f"Incident_ID={incident_id} "
            f"was not found."
        )

    incident = incident_rows.iloc[0]

    model_columns = model.feature_names_in_

    model_input = incident_rows[
        list(model_columns)
    ]

    predicted_severity = str(
        model.predict(model_input)[0]
    )

    updated_hospitals = (
        simulate_hospital_change(
            current_hospital_id,
            hospitals,
            change,
        )
    )

    current_candidates = calculate_hospitals(
        str(incident["Condition"]),
        predicted_severity,
        float(incident["Patient_Lat"]),
        float(incident["Patient_Lon"]),
        updated_hospitals,
    )

    current_hospital = current_candidates[
        current_candidates["Hospital_ID"]
        == current_hospital_id
    ]

    if current_hospital.empty:

        current_available = False

    else:

        current_available = True

    if current_available:

        return {
            "redirect": False,
            "reason": "Current hospital remains suitable.",
            "new_hospital": None,
            "candidates": current_candidates,
        }

    (
        new_hospital,
        candidates,
    ) = find_best_hospital(
        condition=str(
            incident["Condition"]
        ),
        severity=predicted_severity,
        patient_lat=float(
            incident["Patient_Lat"]
        ),
        patient_lon=float(
            incident["Patient_Lon"]
        ),
        hospitals=updated_hospitals,
        excluded_hospital=current_hospital_id,
    )

    if new_hospital is None:

        return {
            "redirect": False,
            "reason": (
                "No suitable alternative hospital available."
            ),
            "new_hospital": None,
            "candidates": candidates,
        }

    return {
        "redirect": True,
        "reason": (
            f"Hospital {current_hospital_id} "
            f"is no longer suitable."
        ),
        "new_hospital": new_hospital,
        "candidates": candidates,
    }


def print_redirection(result):

    print()
    print("=" * 70)
    print("DYNAMIC HOSPITAL REDIRECTION")
    print("=" * 70)

    if not result["redirect"]:

        print(
            "REDIRECTION:       NO"
        )

        print(
            f"Reason:            "
            f"{result['reason']}"
        )

        print("=" * 70)

        return

    print(
        "REDIRECTION:       YES"
    )

    print(
        f"Reason:            "
        f"{result['reason']}"
    )

    hospital = result[
        "new_hospital"
    ]

    print()
    print(
        "NEW HOSPITAL"
    )
    print("-" * 70)

    print(
        f"Hospital:          "
        f"{hospital['Hospital_ID']}"
    )

    print(
        f"Type:              "
        f"{hospital['Hospital_Type']}"
    )

    print(
        f"Distance:          "
        f"{hospital['Distance_KM']:.2f} km"
    )

    print(
        f"Available beds:    "
        f"{int(hospital['Available_Beds'])}"
    )

    print(
        f"Available ICU:     "
        f"{int(hospital['Available_ICU'])}"
    )

    print(
        f"Suitability:       "
        f"{int(hospital['Suitability'])}/3"
    )

    print("=" * 70)


if __name__ == "__main__":

    TEST_INCIDENT_ID = 1

    CURRENT_HOSPITAL_ID = "HOSP_182"

    result = check_redirection(
        incident_id=TEST_INCIDENT_ID,
        current_hospital_id=CURRENT_HOSPITAL_ID,
        change="full",
    )

    print_redirection(result)