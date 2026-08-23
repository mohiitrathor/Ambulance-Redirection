import os
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "Dataset"
RESULTS_DIR = BASE_DIR / "EDA Results"
PLOTS_DIR = RESULTS_DIR / "plots"
REPORTS_DIR = RESULTS_DIR / "reports"

PLOTS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOAD DATASETS
# ============================================================

patients = pd.read_csv(
    DATA_DIR / "patient_incidents.csv"
)

ambulances = pd.read_csv(
    DATA_DIR / "ambulances.csv"
)

hospitals = pd.read_csv(
    DATA_DIR / "hospitals.csv"
)

dispatch = pd.read_csv(
    DATA_DIR / "dispatch_scenarios.csv"
)


# ============================================================
# REPORT STORAGE
# ============================================================

report = []


def add_report(text=""):
    """Add a line to the EDA report."""
    report.append(text)


def section(title):
    """Add a section heading."""
    add_report("")
    add_report("=" * 70)
    add_report(title)
    add_report("=" * 70)


# ============================================================
# BASIC DATASET INSPECTION
# ============================================================

def inspect_dataset(df, name):

    section(f"{name.upper()} - BASIC INFORMATION")

    add_report(f"Rows: {df.shape[0]:,}")
    add_report(f"Columns: {df.shape[1]:,}")

    add_report("")
    add_report("Columns:")
    for column in df.columns:
        add_report(f"  - {column}")

    add_report("")
    add_report("Data types:")

    for column, dtype in df.dtypes.items():
        add_report(
            f"  {column}: {dtype}"
        )

    add_report("")

    duplicate_count = df.duplicated().sum()

    add_report(
        f"Duplicate rows: {duplicate_count:,}"
    )


# ============================================================
# MISSING VALUES
# ============================================================

def analyze_missing_values(df, name):

    section(f"{name.upper()} - MISSING VALUES")

    missing = df.isnull().sum()

    missing = missing[
        missing > 0
    ].sort_values(
        ascending=False
    )

    if missing.empty:

        add_report(
            "No missing values found."
        )

    else:

        for column, count in missing.items():

            percentage = (
                count / len(df) * 100
            )

            add_report(
                f"{column}: "
                f"{count:,} "
                f"({percentage:.2f}%)"
            )


# ============================================================
# NUMERICAL SUMMARY
# ============================================================

def analyze_numerical_features(df, name):

    section(
        f"{name.upper()} - NUMERICAL SUMMARY"
    )

    numerical = df.select_dtypes(
        include=np.number
    )

    if numerical.empty:

        add_report(
            "No numerical features found."
        )

        return

    summary = numerical.describe().T

    for column, row in summary.iterrows():

        add_report(
            f"\n{column}"
        )

        add_report(
            f"  Mean: {row['mean']:.2f}"
        )

        add_report(
            f"  Std: {row['std']:.2f}"
        )

        add_report(
            f"  Min: {row['min']:.2f}"
        )

        add_report(
            f"  25%: {row['25%']:.2f}"
        )

        add_report(
            f"  Median: {row['50%']:.2f}"
        )

        add_report(
            f"  75%: {row['75%']:.2f}"
        )

        add_report(
            f"  Max: {row['max']:.2f}"
        )


# ============================================================
# CATEGORICAL SUMMARY
# ============================================================

def analyze_categorical_features(df, name):

    section(
        f"{name.upper()} - CATEGORICAL FEATURES"
    )

    categorical = df.select_dtypes(
        include=["object"]
    ).columns

    if len(categorical) == 0:

        add_report(
            "No categorical features found."
        )

        return

    for column in categorical:

        add_report("")
        add_report(column)
        add_report("-" * len(column))

        counts = (
            df[column]
            .value_counts(
                dropna=False
            )
        )

        for value, count in counts.items():

            percentage = (
                count / len(df) * 100
            )

            add_report(
                f"  {value}: "
                f"{count:,} "
                f"({percentage:.2f}%)"
            )


# ============================================================
# PATIENT SEVERITY ANALYSIS
# ============================================================

def analyze_severity(df):

    section(
        "PATIENT INCIDENTS - SEVERITY ANALYSIS"
    )

    severity_order = [
        "Non-Urgent",
        "Low",
        "Moderate",
        "Emergency",
        "Critical"
    ]

    counts = (
        df["Severity"]
        .value_counts()
        .reindex(
            severity_order,
            fill_value=0
        )
    )

    add_report(
        "Severity distribution:"
    )

    for severity, count in counts.items():

        percentage = (
            count / len(df) * 100
        )

        add_report(
            f"  {severity}: "
            f"{count:,} "
            f"({percentage:.2f}%)"
        )

    # --------------------------------------------------------
    # Plot
    # --------------------------------------------------------

    plt.figure(
        figsize=(9, 6)
    )

    counts.plot(
        kind="bar"
    )

    plt.title(
        "Patient Severity Distribution"
    )

    plt.xlabel(
        "Severity"
    )

    plt.ylabel(
        "Number of Patients"
    )

    plt.xticks(
        rotation=0
    )

    plt.tight_layout()

    plt.savefig(
        PLOTS_DIR /
        "severity_distribution.png",
        dpi=300
    )

    plt.close()


# ============================================================
# CONDITION ANALYSIS
# ============================================================

def analyze_conditions(df):

    section(
        "PATIENT INCIDENTS - CONDITION ANALYSIS"
    )

    counts = (
        df["Condition"]
        .value_counts()
    )

    for condition, count in counts.items():

        percentage = (
            count / len(df) * 100
        )

        add_report(
            f"  {condition}: "
            f"{count:,} "
            f"({percentage:.2f}%)"
        )

    # --------------------------------------------------------
    # Plot
    # --------------------------------------------------------

    plt.figure(
        figsize=(9, 6)
    )

    counts.sort_values().plot(
        kind="barh"
    )

    plt.title(
        "Emergency Condition Distribution"
    )

    plt.xlabel(
        "Number of Incidents"
    )

    plt.ylabel(
        "Condition"
    )

    plt.tight_layout()

    plt.savefig(
        PLOTS_DIR /
        "condition_distribution.png",
        dpi=300
    )

    plt.close()


# ============================================================
# CONDITION × SEVERITY
# ============================================================

def analyze_condition_severity(df):

    section(
        "CONDITION × SEVERITY"
    )

    severity_order = [
        "Non-Urgent",
        "Low",
        "Moderate",
        "Emergency",
        "Critical"
    ]

    table = pd.crosstab(
        df["Condition"],
        df["Severity"],
        normalize="index"
    ) * 100

    table = table.reindex(
        columns=severity_order,
        fill_value=0
    )

    add_report(
        "\nPercentage distribution:"
    )

    add_report(
        table.round(2).to_string()
    )

    # --------------------------------------------------------
    # Plot
    # --------------------------------------------------------

    plt.figure(
        figsize=(11, 7)
    )

    table.plot(
        kind="bar",
        stacked=True,
        figsize=(11, 7)
    )

    plt.title(
        "Severity Distribution by Condition"
    )

    plt.xlabel(
        "Condition"
    )

    plt.ylabel(
        "Percentage"
    )

    plt.xticks(
        rotation=30,
        ha="right"
    )

    plt.legend(
        title="Severity"
    )

    plt.tight_layout()

    plt.savefig(
        PLOTS_DIR /
        "condition_vs_severity.png",
        dpi=300
    )

    plt.close()


# ============================================================
# CLINICAL FEATURES VS SEVERITY
# ============================================================

def analyze_clinical_features(df):

    section(
        "PATIENT INCIDENTS - CLINICAL FEATURES BY SEVERITY"
    )

    severity_order = [
        "Non-Urgent",
        "Low",
        "Moderate",
        "Emergency",
        "Critical"
    ]

    clinical_features = [
        "Heart_Rate",
        "SpO2",
        "Systolic_BP",
        "Diastolic_BP",
        "Respiratory_Rate",
        "Temperature",
        "GCS",
        "Pain_Score",
        "Blood_Glucose"
    ]

    available_features = [
        feature
        for feature in clinical_features
        if feature in df.columns
    ]

    means = (
        df.groupby("Severity")[
            available_features
        ]
        .mean()
        .reindex(severity_order)
    )

    add_report(
        "\nMean clinical values by severity:"
    )

    add_report(
        means.round(2).to_string()
    )

    # --------------------------------------------------------
    # Individual boxplots
    # --------------------------------------------------------

    for feature in available_features:

        plt.figure(
            figsize=(9, 6)
        )

        data = [
            df.loc[
                df["Severity"] == severity,
                feature
            ].dropna()
            for severity in severity_order
        ]

        plt.boxplot(
            data,
            tick_labels=severity_order
        )

        plt.title(
            f"{feature} by Severity"
        )

        plt.xlabel(
            "Severity"
        )

        plt.ylabel(
            feature
        )

        plt.xticks(
            rotation=20
        )

        plt.tight_layout()

        filename = (
            feature.lower()
            + "_by_severity.png"
        )

        plt.savefig(
            PLOTS_DIR / filename,
            dpi=300
        )

        plt.close()


# ============================================================
# CORRELATION ANALYSIS
# ============================================================

def analyze_correlations(df):

    section(
        "PATIENT INCIDENTS - CORRELATION ANALYSIS"
    )

    numerical = df.select_dtypes(
        include=np.number
    )

    correlation = numerical.corr()

    add_report(
        "\nCorrelation matrix:"
    )

    add_report(
        correlation.round(2).to_string()
    )

    # --------------------------------------------------------
    # Plot
    # --------------------------------------------------------

    plt.figure(
        figsize=(15, 12)
    )

    plt.imshow(
        correlation,
        interpolation="nearest",
        aspect="auto"
    )

    plt.colorbar(
        label="Correlation"
    )

    plt.xticks(
        range(len(correlation.columns)),
        correlation.columns,
        rotation=90
    )

    plt.yticks(
        range(len(correlation.columns)),
        correlation.columns
    )

    plt.title(
        "Numerical Feature Correlation Matrix"
    )

    plt.tight_layout()

    plt.savefig(
        PLOTS_DIR /
        "correlation_matrix.png",
        dpi=300
    )

    plt.close()


# ============================================================
# BINARY CLINICAL FEATURES
# ============================================================

def analyze_binary_features(df):

    section(
        "PATIENT INCIDENTS - BINARY CLINICAL FEATURES"
    )

    binary_features = [
        "Respiratory_Distress",
        "Chest_Pain",
        "Bleeding",
        "Seizure",
        "Diabetes",
        "Hypertension",
        "Heart_Disease",
        "Respiratory_Disease"
    ]

    available_features = [
        feature
        for feature in binary_features
        if feature in df.columns
    ]

    for feature in available_features:

        counts = (
            df[feature]
            .value_counts()
            .sort_index()
        )

        add_report(
            f"\n{feature}:"
        )

        for value, count in counts.items():

            percentage = (
                count / len(df) * 100
            )

            add_report(
                f"  {value}: "
                f"{count:,} "
                f"({percentage:.2f}%)"
            )


# ============================================================
# AMBULANCE ANALYSIS
# ============================================================

def analyze_ambulances(df):

    section(
        "AMBULANCES - ANALYSIS"
    )

    add_report(
        f"Total ambulances: {len(df):,}"
    )

    if "Ambulance_Type" in df.columns:

        add_report(
            "\nAmbulance types:"
        )

        add_report(
            df["Ambulance_Type"]
            .value_counts()
            .to_string()
        )

    if "Availability" in df.columns:

        add_report(
            "\nAvailability:"
        )

        add_report(
            df["Availability"]
            .value_counts()
            .to_string()
        )

    # --------------------------------------------------------
    # Ambulance type plot
    # --------------------------------------------------------

    if "Ambulance_Type" in df.columns:

        counts = (
            df["Ambulance_Type"]
            .value_counts()
        )

        plt.figure(
            figsize=(9, 6)
        )

        counts.plot(
            kind="bar"
        )

        plt.title(
            "Ambulance Type Distribution"
        )

        plt.xlabel(
            "Ambulance Type"
        )

        plt.ylabel(
            "Number of Ambulances"
        )

        plt.xticks(
            rotation=20
        )

        plt.tight_layout()

        plt.savefig(
            PLOTS_DIR /
            "ambulance_type_distribution.png",
            dpi=300
        )

        plt.close()


# ============================================================
# HOSPITAL ANALYSIS
# ============================================================

def analyze_hospitals(df):

    section(
        "HOSPITALS - ANALYSIS"
    )

    add_report(
        f"Total hospitals: {len(df):,}"
    )

    if "Hospital_Type" in df.columns:

        add_report(
            "\nHospital types:"
        )

        add_report(
            df["Hospital_Type"]
            .value_counts()
            .to_string()
        )

    # --------------------------------------------------------
    # Capacity statistics
    # --------------------------------------------------------

    numerical_features = [
        "Hospital_Capacity",
        "Current_Load",
        "ICU_Capacity",
        "Current_ICU_Load"
    ]

    available_features = [
        feature
        for feature in numerical_features
        if feature in df.columns
    ]

    if available_features:

        add_report(
            "\nHospital capacity statistics:"
        )

        add_report(
            df[available_features]
            .describe()
            .round(2)
            .to_string()
        )

    # --------------------------------------------------------
    # Hospital utilization
    # --------------------------------------------------------

    if {
        "Hospital_Capacity",
        "Current_Load"
    }.issubset(df.columns):

        utilization = (
            df["Current_Load"]
            / df["Hospital_Capacity"]
            * 100
        )

        add_report(
            "\nHospital utilization:"
        )

        add_report(
            f"  Mean: {utilization.mean():.2f}%"
        )

        add_report(
            f"  Minimum: {utilization.min():.2f}%"
        )

        add_report(
            f"  Maximum: {utilization.max():.2f}%"
        )

    # --------------------------------------------------------
    # ICU utilization
    # --------------------------------------------------------

    if {
        "ICU_Capacity",
        "Current_ICU_Load"
    }.issubset(df.columns):

        icu_utilization = (
            df["Current_ICU_Load"]
            / df["ICU_Capacity"]
            * 100
        )

        add_report(
            "\nICU utilization:"
        )

        add_report(
            f"  Mean: {icu_utilization.mean():.2f}%"
        )

        add_report(
            f"  Minimum: {icu_utilization.min():.2f}%"
        )

        add_report(
            f"  Maximum: {icu_utilization.max():.2f}%"
        )

    # --------------------------------------------------------
    # Hospital type plot
    # --------------------------------------------------------

    if "Hospital_Type" in df.columns:

        counts = (
            df["Hospital_Type"]
            .value_counts()
        )

        plt.figure(
            figsize=(9, 6)
        )

        counts.plot(
            kind="bar"
        )

        plt.title(
            "Hospital Type Distribution"
        )

        plt.xlabel(
            "Hospital Type"
        )

        plt.ylabel(
            "Number of Hospitals"
        )

        plt.xticks(
            rotation=20
        )

        plt.tight_layout()

        plt.savefig(
            PLOTS_DIR /
            "hospital_type_distribution.png",
            dpi=300
        )

        plt.close()


# ============================================================
# DISPATCH ANALYSIS
# ============================================================

def analyze_dispatch(df):

    section(
        "DISPATCH SCENARIOS - ANALYSIS"
    )

    add_report(
        f"Total dispatch scenarios: {len(df):,}"
    )

    if "Selected" in df.columns:

        selected_count = (
            df["Selected"]
            .sum()
        )

        add_report(
            f"Selected ambulances: "
            f"{selected_count:,}"
        )

    if "Patient_Severity" in df.columns:

        add_report(
            "\nPatient severity in dispatch scenarios:"
        )

        add_report(
            df["Patient_Severity"]
            .value_counts()
            .to_string()
        )

    if "Traffic_Level" in df.columns:

        add_report(
            "\nTraffic levels:"
        )

        add_report(
            df["Traffic_Level"]
            .value_counts()
            .to_string()
        )

    if "Road_Condition" in df.columns:

        add_report(
            "\nRoad conditions:"
        )

        add_report(
            df["Road_Condition"]
            .value_counts()
            .to_string()
        )

    if "Capability_Match" in df.columns:

        match_rate = (
            df["Capability_Match"]
            .mean()
            * 100
        )

        add_report(
            f"\nCapability match rate: "
            f"{match_rate:.2f}%"
        )

    # --------------------------------------------------------
    # ETA statistics
    # --------------------------------------------------------

    if "Predicted_ETA_Minutes" in df.columns:

        eta = df[
            "Predicted_ETA_Minutes"
        ]

        add_report(
            "\nPredicted ETA statistics:"
        )

        add_report(
            f"  Mean: {eta.mean():.2f} minutes"
        )

        add_report(
            f"  Median: {eta.median():.2f} minutes"
        )

        add_report(
            f"  Minimum: {eta.min():.2f} minutes"
        )

        add_report(
            f"  Maximum: {eta.max():.2f} minutes"
        )

    # --------------------------------------------------------
    # Traffic distribution plot
    # --------------------------------------------------------

    if "Traffic_Level" in df.columns:

        counts = (
            df["Traffic_Level"]
            .value_counts()
        )

        plt.figure(
            figsize=(9, 6)
        )

        counts.plot(
            kind="bar"
        )

        plt.title(
            "Traffic Level Distribution"
        )

        plt.xlabel(
            "Traffic Level"
        )

        plt.ylabel(
            "Number of Scenarios"
        )

        plt.xticks(
            rotation=20
        )

        plt.tight_layout()

        plt.savefig(
            PLOTS_DIR /
            "traffic_distribution.png",
            dpi=300
        )

        plt.close()


# ============================================================
# FINAL DATASET VALIDATION
# ============================================================

def final_validation():

    section(
        "FINAL EDA VALIDATION"
    )

    datasets = {
        "Patients": patients,
        "Ambulances": ambulances,
        "Hospitals": hospitals,
        "Dispatch": dispatch
    }

    for name, df in datasets.items():

        add_report(
            f"\n{name}"
        )

        add_report(
            f"  Rows: {len(df):,}"
        )

        add_report(
            f"  Columns: {len(df.columns):,}"
        )

        add_report(
            f"  Missing values: "
            f"{df.isnull().sum().sum():,}"
        )

        add_report(
            f"  Duplicate rows: "
            f"{df.duplicated().sum():,}"
        )


# ============================================================
# SAVE REPORT
# ============================================================

def save_report():

    report_path = (
        REPORTS_DIR /
        "eda_summary.txt"
    )

    with open(
        report_path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "\n".join(report)
        )

    print(
        f"\nEDA report saved to:\n"
        f"{report_path}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n" + "=" * 70)
    print("EMERGENCY AMBULANCE SYSTEM - EDA")
    print("=" * 70)

    print("\nAnalyzing datasets...")

    # --------------------------------------------------------
    # Basic inspection
    # --------------------------------------------------------

    inspect_dataset(
        patients,
        "Patient Incidents"
    )

    inspect_dataset(
        ambulances,
        "Ambulances"
    )

    inspect_dataset(
        hospitals,
        "Hospitals"
    )

    inspect_dataset(
        dispatch,
        "Dispatch Scenarios"
    )

    # --------------------------------------------------------
    # Missing values
    # --------------------------------------------------------

    analyze_missing_values(
        patients,
        "Patient Incidents"
    )

    analyze_missing_values(
        ambulances,
        "Ambulances"
    )

    analyze_missing_values(
        hospitals,
        "Hospitals"
    )

    analyze_missing_values(
        dispatch,
        "Dispatch Scenarios"
    )

    # --------------------------------------------------------
    # Numerical analysis
    # --------------------------------------------------------

    analyze_numerical_features(
        patients,
        "Patient Incidents"
    )

    analyze_numerical_features(
        ambulances,
        "Ambulances"
    )

    analyze_numerical_features(
        hospitals,
        "Hospitals"
    )

    analyze_numerical_features(
        dispatch,
        "Dispatch Scenarios"
    )

    # --------------------------------------------------------
    # Categorical analysis
    # --------------------------------------------------------

    analyze_categorical_features(
        patients,
        "Patient Incidents"
    )

    analyze_categorical_features(
        ambulances,
        "Ambulances"
    )

    analyze_categorical_features(
        hospitals,
        "Hospitals"
    )

    analyze_categorical_features(
        dispatch,
        "Dispatch Scenarios"
    )

    # --------------------------------------------------------
    # Patient analysis
    # --------------------------------------------------------

    analyze_severity(
        patients
    )

    analyze_conditions(
        patients
    )

    analyze_condition_severity(
        patients
    )

    analyze_clinical_features(
        patients
    )

    analyze_correlations(
        patients
    )

    analyze_binary_features(
        patients
    )

    # --------------------------------------------------------
    # Ambulance analysis
    # --------------------------------------------------------

    analyze_ambulances(
        ambulances
    )

    # --------------------------------------------------------
    # Hospital analysis
    # --------------------------------------------------------

    analyze_hospitals(
        hospitals
    )

    # --------------------------------------------------------
    # Dispatch analysis
    # --------------------------------------------------------

    analyze_dispatch(
        dispatch
    )

    # --------------------------------------------------------
    # Final validation
    # --------------------------------------------------------

    final_validation()

    # --------------------------------------------------------
    # Save report
    # --------------------------------------------------------

    save_report()

    print("\n" + "=" * 70)
    print("EDA COMPLETE")
    print("=" * 70)

    print(
        f"\nResults directory:\n"
        f"{RESULTS_DIR}"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()