from pydantic import BaseModel, Field
from typing import Optional


# ==============================================================
# MANUAL REDIRECTION REQUEST
# ==============================================================

class ManualRedirectionRequest(BaseModel):
    """
    Operator manual redirection request.
    If target_hospital_id is omitted, the engine will dynamically
    evaluate and assign the best available alternative hospital.
    """

    target_hospital_id: Optional[str] = Field(
        None,
        description=(
            "Optional target hospital ID to redirect to. "
            "If omitted, engine selects best alternative."
        ),
    )
    reason: Optional[str] = Field(
        "Operator manual override",
        max_length=200,
        description="Operator justification for manual redirection.",
    )


# ==============================================================
# ALTERNATIVE HOSPITAL
# ==============================================================

class AlternativeHospital(BaseModel):
    """
    Alternative hospital details from
    evaluate_redirection() result.
    """

    hospital_id: str
    hospital_type: str
    available_beds: int
    available_icu: int
    score: float
    eta: Optional[float] = None


# ==============================================================
# REDIRECTION RESULT
# ==============================================================

class RedirectionResult(BaseModel):
    """
    Redirection evaluation result from
    check_live_redirection() / evaluate_redirection().
    """

    redirect: bool
    reason: str
    trigger: Optional[str] = None
    alternative_hospital: Optional[AlternativeHospital] = None
    eta_before: Optional[float] = None
    eta_after: Optional[float] = None
    eta_saved: Optional[float] = None
    eta_improvement_percent: Optional[float] = None


# ==============================================================
# DECISION RECORD
# ==============================================================

class DecisionRecord(BaseModel):
    """
    A single logged redirection decision from
    DecisionLogger, matching RedirectionDecision dataclass.
    """

    incident_id: int
    time: int
    decision: str
    reason: str
    original_hospital: Optional[str] = None
    new_hospital: Optional[str] = None
    eta_before: Optional[float] = None
    eta_after: Optional[float] = None
    eta_saved: Optional[float] = None
    eta_improvement_percent: Optional[float] = None
    severity: Optional[str] = None
    ambulance_id: Optional[str] = None
