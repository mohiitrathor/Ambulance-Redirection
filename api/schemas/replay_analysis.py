"""
RAAH Replay Analysis & Operational Workstation API Schemas (M10 Phase 3)
========================================================================

Pydantic schemas for timeline inspection, deep event details,
scenario comparisons, before/after telemetry deltas, and drill reports.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ReplayEventSummaryResponse(BaseModel):
    event_index: int
    sim_time: int
    event_type: str
    entity_ids: Dict[str, Any]
    description: str
    payload: Dict[str, Any]
    detail: Dict[str, Any]


class ReplayTimelineResponse(BaseModel):
    scenario_id: str
    run_id: str
    start_time: int
    end_time: int
    duration: int
    event_count: int
    snapshot_count: int
    events: List[ReplayEventSummaryResponse]


class ReplayAnalysisResponse(BaseModel):
    scenario_id: str
    run_id: str
    duration: int
    total_events: int
    dispatch_count: int
    arrival_count: int
    redirection_count: int
    reposition_count: int
    mci_count: int
    hospital_saturation_count: int
    peak_en_route: int
    peak_repositioning: int
    peak_incoming_reservations: int
    unresolved_incidents: int
    unresolved_mcis: int
    fleet_metrics: Dict[str, Any]
    incident_metrics: Optional[Dict[str, Any]] = None
    hospital_metrics: Dict[str, Any]
    mci_metrics: Dict[str, Any]
    resilience_score: Dict[str, Any]
    deterministic_hash: str


class ScenarioComparisonRequest(BaseModel):
    run_id_a: str = Field(..., description="Run ID of baseline scenario")
    run_id_b: str = Field(..., description="Run ID of comparative scenario")


class ScenarioComparisonResponse(BaseModel):
    scenario_a: Dict[str, Any]
    scenario_b: Dict[str, Any]
    delta: Dict[str, Any]
    performance_explanation: str


class BeforeAfterRequest(BaseModel):
    time_a: int = Field(..., ge=0, description="Earlier simulation minute T_a")
    time_b: int = Field(..., ge=0, description="Later simulation minute T_b")


class BeforeAfterResponse(BaseModel):
    time_a: Dict[str, Any]
    time_b: Dict[str, Any]
    delta: Dict[str, Any]


class DrillReportRequest(BaseModel):
    format: Optional[str] = Field("json", description="'json' or 'markdown'")


class DrillReportResponse(BaseModel):
    report_title: str
    scenario_metadata: Dict[str, Any]
    deterministic_hash: str
    resilience_score: Dict[str, Any]
    performance_summary: Dict[str, Any]
    fleet_metrics: Dict[str, Any]
    hospital_metrics: Dict[str, Any]
    mci_metrics: Dict[str, Any]
    important_events: List[Dict[str, Any]]
    markdown_content: Optional[str] = None


class ReplayModeRequest(BaseModel):
    session_id: Optional[str] = "default"
    mode: str = Field("REPLAY", description="'REPLAY' or 'LIVE'")
