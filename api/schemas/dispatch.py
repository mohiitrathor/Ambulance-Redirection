from pydantic import BaseModel
from typing import Optional


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
    traffic: str
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
