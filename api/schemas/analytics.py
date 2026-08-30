"""
RAAH Analytics API Schemas
==========================

Pydantic models defining historical analysis responses.
"""

from typing import Optional, Dict, List
from pydantic import BaseModel, Field


class RunRecord(BaseModel):
    """Metadata for a simulation session."""
    run_id: int
    started_at: str
    ended_at: Optional[str] = None
    status: str
    total_ticks: int = 0
    final_sim_time: int = 0
    notes: Optional[str] = None
    total_incidents: int = 0
    total_redirections: int = 0


class RedirectionSummary(BaseModel):
    """Aggregated redirection metrics."""
    total: int = 0
    ai_autonomous: int = 0
    operator_manual: int = 0
    redirection_rate_pct: float = 0.0
    total_eta_saved: float = 0.0
    avg_eta_saved: float = 0.0


class RunSummary(BaseModel):
    """Comprehensive analytical KPI scorecard for a simulation session."""
    run_id: int
    status: str
    started_at: str
    ended_at: Optional[str] = None
    final_sim_time: int = 0
    total_incidents: int = 0
    incidents_by_priority: Dict[str, int] = Field(default_factory=dict)
    incidents_by_severity: Dict[str, int] = Field(default_factory=dict)
    average_ml_confidence: float = 0.0
    average_initial_eta: float = 0.0
    arrived_count: int = 0
    in_transit_count: int = 0
    redirections: RedirectionSummary
    hospital_saturation_events: int = 0


class AnalyticsIncident(BaseModel):
    """Historical incident triage and assignment record."""
    incident_id: int
    source: str
    condition: str
    predicted_severity: str
    priority: int
    ml_confidence: Optional[float] = None
    patient_lat: float
    patient_lon: float
    dispatched_sim_time: int
    ambulance_id: Optional[str] = None
    ambulance_type: Optional[str] = None
    initial_hospital_id: Optional[str] = None
    final_hospital_id: Optional[str] = None
    initial_eta_minutes: Optional[float] = None
    final_eta_minutes: Optional[float] = None
    dispatch_status: Optional[str] = None
    arrived_sim_time: Optional[int] = None


class AnalyticsDecision(BaseModel):
    """Historical redirection decision record."""
    id: int
    run_id: int
    incident_id: int
    ambulance_id: str
    decision_type: str
    trigger_type: str
    original_hospital_id: Optional[str] = None
    new_hospital_id: Optional[str] = None
    eta_before: Optional[float] = None
    eta_after: Optional[float] = None
    eta_saved: Optional[float] = None
    eta_improvement_pct: Optional[float] = None
    reason: str
    sim_time: int
    created_at: str


class AnalyticsEvent(BaseModel):
    """Historical simulation event record."""
    id: int
    run_id: int
    event_type: str
    sim_time: int
    facility_or_unit_id: Optional[str] = None
    message: str
    created_at: str
