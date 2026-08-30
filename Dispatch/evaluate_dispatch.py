import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "Dispatch"))

from dispatch_engine import dispatch_incident


PATIENTS_PATH = (
    ROOT
    / "Dataset"
    / "patient_incidents.csv"
)


def evaluate(sample_size=1000):

    patients = pd.read_csv(
        PATIENTS_PATH
    )

    sample = patients.sample(
        n=min(sample_size, len(patients)),
        random_state=42,
    )

    results = []

    print()
    print("=" * 70)
    print("RUNNING DISPATCH EVALUATION")
    print("=" * 70)

    for index, (_, incident) in enumerate(
        sample.iterrows(),
        start=1,
    ):

        incident_id = int(
            incident["Incident_ID"]
        )

        try:

            result = dispatch_incident(
                incident_id
            )

            ambulance = result.get(
                "ambulance"
            )

            hospital = result.get(
                "hospital"
            )

            results.append({
                "Incident_ID":
                    incident_id,

                "Actual_Severity":
                    str(
                        incident["Severity"]
                    ),

                "Predicted_Severity":
                    result.get(
                        "predicted_severity",
                        result.get(
                            "patient",
                            {}
                        ).get(
                            "predicted_severity"
                        ),
                    ),

                "ML_Confidence":
                    result.get(
                        "confidence",
                        result.get(
                            "patient",
                            {}
                        ).get(
                            "confidence"
                        ),
                    ),

                "Ambulance_Assigned":
                    ambulance is not None,

                "Ambulance_ID":
                    ambulance.get(
                        "ambulance_id"
                    )
                    if ambulance
                    else None,

                "Ambulance_Type":
                    ambulance.get(
                        "ambulance_type"
                    )
                    if ambulance
                    else None,

                "ETA":
                    ambulance.get(
                        "eta_minutes"
                    )
                    if ambulance
                    else None,

                "Distance":
                    ambulance.get(
                        "distance_km"
                    )
                    if ambulance
                    else None,

                "Capability_Match":
                    ambulance.get(
                        "capability_match"
                    )
                    if ambulance
                    else False,

                "Fallback":
                    ambulance.get(
                        "fallback"
                    )
                    if ambulance
                    else False,

                "Hospital_Assigned":
                    hospital is not None,

                "Hospital_ID":
                    hospital.get(
                        "hospital_id"
                    )
                    if hospital
                    else None,

                "Hospital_Type":
                    hospital.get(
                        "hospital_type"
                    )
                    if hospital
                    else None,

                "Hospital_Distance":
                    hospital.get(
                        "distance_km"
                    )
                    if hospital
                    else None,

                "Available_ICU":
                    hospital.get(
                        "available_icu"
                    )
                    if hospital
                    else None,

                "Hospital_Suitability":
                    hospital.get(
                        "suitability"
                    )
                    if hospital
                    else None,

                "Status":
                    result.get(
                        "status"
                    ),
            })

        except Exception as error:

            results.append({
                "Incident_ID":
                    incident_id,

                "Actual_Severity":
                    str(
                        incident["Severity"]
                    ),

                "Predicted_Severity":
                    None,

                "ML_Confidence":
                    None,

                "Ambulance_Assigned":
                    False,

                "Ambulance_ID":
                    None,

                "Ambulance_Type":
                    None,

                "ETA":
                    None,

                "Distance":
                    None,

                "Capability_Match":
                    False,

                "Fallback":
                    False,

                "Hospital_Assigned":
                    False,

                "Hospital_ID":
                    None,

                "Hospital_Type":
                    None,

                "Hospital_Distance":
                    None,

                "Available_ICU":
                    None,

                "Hospital_Suitability":
                    None,

                "Status":
                    f"ERROR: {error}",
            })

        if index % 100 == 0:

            print(
                f"Processed {index}/{len(sample)}"
            )

    return pd.DataFrame(results)


def print_report(results):

    total = len(results)

    ambulance_assigned = (
        results["Ambulance_Assigned"]
        .sum()
    )

    hospital_assigned = (
        results["Hospital_Assigned"]
        .sum()
    )

    capability_matches = (
        results["Capability_Match"]
        .sum()
    )

    fallback_count = (
        results["Fallback"]
        .sum()
    )

    valid_confidence = results[
        "ML_Confidence"
    ].dropna()

    valid_eta = results[
        "ETA"
    ].dropna()

    valid_distance = results[
        "Distance"
    ].dropna()

    critical = results[
        results["Predicted_Severity"]
        == "Critical"
    ]

    critical_capability = (
        critical["Capability_Match"].mean()
        if not critical.empty
        else 0
    )

    critical_icu = (
        critical["Available_ICU"]
        .notna()
        .mean()
        if not critical.empty
        else 0
    )

    print()
    print("=" * 70)
    print("DISPATCH ENGINE EVALUATION")
    print("=" * 70)

    print(
        f"Incidents tested:          "
        f"{total}"
    )

    print(
        f"Ambulance assigned:        "
        f"{ambulance_assigned / total:.2%}"
    )

    print(
        f"Hospital assigned:         "
        f"{hospital_assigned / total:.2%}"
    )

    print(
        f"Capability match:          "
        f"{capability_matches / total:.2%}"
    )

    print(
        f"Fallback dispatches:       "
        f"{fallback_count / total:.2%}"
    )

    if not valid_confidence.empty:

        print(
            f"Average ML confidence:     "
            f"{valid_confidence.mean():.2%}"
        )

    if not valid_eta.empty:

        print(
            f"Average ambulance ETA:     "
            f"{valid_eta.mean():.2f} min"
        )

    if not valid_distance.empty:

        print(
            f"Average ambulance distance:"
            f" {valid_distance.mean():.2f} km"
        )

    print()

    print("CRITICAL INCIDENTS")
    print("-" * 70)

    print(
        f"Critical incidents:        "
        f"{len(critical)}"
    )

    print(
        f"Capability requirement met:"
        f" {critical_capability:.2%}"
    )

    print(
        f"ICU destination available: "
        f"{critical_icu:.2%}"
    )

    print()

    print("PREDICTED SEVERITY")
    print("-" * 70)

    severity_counts = (
        results[
            "Predicted_Severity"
        ]
        .value_counts()
    )

    for severity, count in (
        severity_counts.items()
    ):

        print(
            f"{severity:<15}"
            f"{count:>6}"
            f"  "
            f"{count / total:.2%}"
        )

    print()

    print("HOSPITAL SELECTION")
    print("-" * 70)

    hospital_counts = (
        results[
            "Hospital_Type"
        ]
        .value_counts()
    )

    for hospital, count in (
        hospital_counts.items()
    ):

        print(
            f"{hospital:<20}"
            f"{count:>6}"
        )

    print()

    errors = results[
        results["Status"]
        .astype(str)
        .str.startswith("ERROR")
    ]

    print(
        f"Engine errors:             "
        f"{len(errors)}"
    )

    print("=" * 70)


if __name__ == "__main__":

    results = evaluate(
        sample_size=1000
    )

    print_report(results)