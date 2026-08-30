from pathlib import Path

import numpy as np
import pandas as pd

from dispatch_engine import load_data, hospital_suitability


ROOT = Path(__file__).resolve().parents[1]

HOSPITALS_PATH = (
    ROOT
    / "Dataset"
    / "hospitals.csv"
)


REDIRECTION_THRESHOLD = 0.20


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


def hospital_score(hospital):

    suitability_score = (
        hospital["Suitability"] / 3
    )

    distance_score = (
        1
        / (1 + hospital["Distance_KM"])
    )

    capacity_score = min(
        hospital["Available_Beds"] / 100,
        1,
    )

    icu_score = min(
        hospital["Available_ICU"] / 20,
        1,
    )

    return (
        suitability_score * 0.50
        + distance_score * 0.25
        + capacity_score * 0.15
        + icu_score * 0.10
    )


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

        return (
            None,
            candidates,
        )

    candidates["Hospital_Score"] = (
        candidates.apply(
            hospital_score,
            axis=1,
        )
    )

    candidates = candidates.sort_values(
        by="Hospital_Score",
        ascending=False,
    ).reset_index(drop=True)

    return (
        candidates.iloc[0],
        candidates,
    )


def simulate_hospital_change(
    hospital_id,
    hospitals,
    change,
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
    change,
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
            f"Incident_ID {incident_id} "
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

    current_candidates = (
        calculate_hospitals(
            str(incident["Condition"]),
            predicted_severity,
            float(incident["Patient_Lat"]),
            float(incident["Patient_Lon"]),
            updated_hospitals,
        )
    )

    current = current_candidates[
        current_candidates["Hospital_ID"]
        == current_hospital_id
    ]

    current_available = (
        not current.empty
    )

    (
        alternative,
        alternatives,
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

    if not current_available:

        if alternative is None:

            return {
                "redirect": False,
                "reason": (
                    "No suitable alternative "
                    "hospital available."
                ),
                "new_hospital": None,
                "score_improvement": None,
            }

        return {
            "redirect": True,
            "reason": (
                f"Hospital {current_hospital_id} "
                f"is no longer suitable."
            ),
            "new_hospital": alternative,
            "score_improvement": None,
        }

    current_hospital = current.iloc[0]

    current_score = hospital_score(
        current_hospital
    )

    if alternative is None:

        return {
            "redirect": False,
            "reason": (
                "No alternative hospital "
                "available."
            ),
            "new_hospital": None,
            "score_improvement": 0,
        }

    alternative_score = hospital_score(
        alternative
    )

    if current_score == 0:

        improvement = 1

    else:

        improvement = (
            alternative_score
            - current_score
        ) / current_score

    if improvement >= REDIRECTION_THRESHOLD:

        return {
            "redirect": True,
            "reason": (
                "Alternative hospital provides "
                "a significantly better destination."
            ),
            "new_hospital": alternative,
            "score_improvement": improvement,
        }

    return {
        "redirect": False,
        "reason": (
            "Current hospital remains suitable "
            "and no significant improvement was found."
        ),
        "new_hospital": None,
        "score_improvement": improvement,
    }


def print_redirection(result):

    print()
    print("=" * 70)
    print("DYNAMIC HOSPITAL REDIRECTION")
    print("=" * 70)

    print(
        f"REDIRECTION:       "
        f"{'YES' if result['redirect'] else 'NO'}"
    )

    print(
        f"Reason:            "
        f"{result['reason']}"
    )

    if result["score_improvement"] is not None:

        print(
            f"Score improvement: "
            f"{result['score_improvement']:.2%}"
        )

    if result["new_hospital"] is not None:

        hospital = result[
            "new_hospital"
        ]

        print()
        print("NEW HOSPITAL")
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

        print(
            f"Hospital score:    "
            f"{hospital['Hospital_Score']:.3f}"
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