from pydantic import BaseModel, Field
from typing import Optional, Literal


# ==============================================================
# PATIENT INFO
# ==============================================================

class PatientInfo(BaseModel):
    """Patient triage information from ML prediction."""

    condition: str
    predicted_severity: str
    priority: str
    confidence: Optional[float] = None


# ==============================================================
# AMBULANCE ASSIGNMENT
# ==============================================================

class AmbulanceAssignment(BaseModel):
    """Selected ambulance details from dispatch."""

    ambulance_id: str
    ambulance_type: str
    eta_minutes: float
    distance_km: float
    traffic: Optional[str] = None
    traffic_level: Optional[str] = None
    road_condition: str
    capability_match: bool
    fallback: bool


# ==============================================================
# HOSPITAL ASSIGNMENT
# ==============================================================

class HospitalAssignment(BaseModel):
    """Selected hospital details from dispatch."""

    hospital_id: str
    hospital_type: str
    distance_km: float
    available_beds: int
    available_icu: int
    suitability: int


# ==============================================================
# DISPATCH RESULT
# ==============================================================

class DispatchResult(BaseModel):
    """
    Complete dispatch decision returned by dispatch_incident().

    The predicted_severity and confidence fields appear at the
    top level only when status is NO_AMBULANCE_AVAILABLE.
    """

    status: str
    incident_id: int
    patient: PatientInfo
    ambulance: Optional[AmbulanceAssignment] = None
    hospital: Optional[HospitalAssignment] = None
    predicted_severity: Optional[str] = None
    confidence: Optional[float] = None


# ==============================================================
# CUSTOM LIVE EMERGENCY INTAKE REQUEST
# ==============================================================

class CustomIncidentRequest(BaseModel):
    """
    Live Emergency Call Intake Request.

    Matches the exact 24-feature contract of the trained ML pipeline:
      - 6 Categorical features (exact domain categories)
      - 18 Numeric features (vitals, symptoms, medical history)

    Plus geographic coordinates for spatial routing (not ML features).
    """

    # 6 Categorical Features
    Sex: Literal["Female", "Male"]
    Condition: Literal[
        "Cardiac",
        "Gastrointestinal",
        "Infection",
        "Neurological",
        "Other",
        "Respiratory",
        "Trauma",
    ]
    Oxygen_Requirement: Literal[
        "Nasal Cannula",
        "No Oxygen",
        "Oxygen Mask",
        "Ventilator",
    ]
    Consciousness: Literal[
        "Alert",
        "Confused",
        "Drowsy",
        "Unconscious",
    ]
    Injury_Type: Literal[
        "Burn",
        "Fracture",
        "Head Injury",
        "Internal Injury",
        "Laceration",
        "No Injury",
    ]
    Arrival_Mode: Literal[
        "Ambulance",
        "Referral",
        "Walk-in",
    ]

    # 18 Numeric Features (vitals & clinical indicators)
    Age: int = Field(..., ge=0, le=125, description="Patient age (0-125)")
    Heart_Rate: float = Field(..., ge=20.0, le=300.0, description="Heart rate in bpm (20-300)")
    SpO2: float = Field(..., ge=40.0, le=100.0, description="Oxygen saturation % (40-100)")
    Systolic_BP: float = Field(..., ge=40.0, le=300.0, description="Systolic blood pressure in mmHg (40-300)")
    Diastolic_BP: float = Field(..., ge=20.0, le=200.0, description="Diastolic blood pressure in mmHg (20-200)")
    Respiratory_Rate: float = Field(..., ge=4.0, le=80.0, description="Respiratory rate breaths/min (4-80)")
    Temperature: float = Field(..., ge=30.0, le=45.0, description="Body temperature in Celsius (30-45)")
    GCS: int = Field(..., ge=3, le=15, description="Glasgow Coma Scale score (3-15)")
    Pain_Score: int = Field(..., ge=0, le=10, description="Pain score (0-10)")
    Blood_Glucose: float = Field(..., ge=20.0, le=1000.0, description="Blood glucose in mg/dL (20-1000)")
    Respiratory_Distress: int = Field(..., ge=0, le=1, description="Respiratory distress (0 or 1)")
    Chest_Pain: int = Field(..., ge=0, le=1, description="Chest pain (0 or 1)")
    Bleeding: int = Field(..., ge=0, le=1, description="Active bleeding (0 or 1)")
    Seizure: int = Field(..., ge=0, le=1, description="Seizure activity (0 or 1)")
    Diabetes: int = Field(..., ge=0, le=1, description="Diabetes history (0 or 1)")
    Hypertension: int = Field(..., ge=0, le=1, description="Hypertension history (0 or 1)")
    Heart_Disease: int = Field(..., ge=0, le=1, description="Heart disease history (0 or 1)")
    Respiratory_Disease: int = Field(..., ge=0, le=1, description="Respiratory disease history (0 or 1)")

    # Spatial Coordinates (for dispatch and routing, not ML features)
    patient_lat: float = Field(..., ge=-90.0, le=90.0, description="Patient latitude")
    patient_lon: float = Field(..., ge=-180.0, le=180.0, description="Patient longitude")

