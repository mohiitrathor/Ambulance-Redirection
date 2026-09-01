"""
RAAH Scenario & Replay API Schemas (M10 Phase 1)
================================================

Pydantic schemas for scenario creation, execution runs, and replay querying.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ScheduledIncidentSchema(BaseModel):
    sim_time: int = Field(..., ge=0)
    incident_id: Optional[int] = None
    custom_data: Optional[Dict[str, Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    condition: Optional[str] = None
    severity: Optional[str] = None
    notes: Optional[str] = ""


class ScheduledMCISchema(BaseModel):
    sim_time: int = Field(..., ge=0)
    name: str
    latitude: float
    longitude: float
    estimated_casualties: int = Field(..., ge=1, le=200)
    mci_id: Optional[str] = None
    primary_condition: Optional[str] = "Trauma"
    notes: Optional[str] = ""
    casualties: Optional[List[Dict[str, Any]]] = None


class ScheduledRepositionSchema(BaseModel):
    sim_time: int = Field(..., ge=0)
    ambulance_id: str
    target_lat: float
    target_lon: float
    reason: Optional[str] = "SCHEDULED_REPOSITION"


class ScheduledRedirectionSchema(BaseModel):
    sim_time: int = Field(..., ge=0)
    incident_id: int
    target_hospital_id: Optional[str] = None
    reason: Optional[str] = "SCHEDULED_DIVERSION"


class ScheduledHospitalEventSchema(BaseModel):
    sim_time: int = Field(..., ge=0)
    hospital_id: str
    event_type: str = "SET_SATURATED"
    value: Optional[Any] = None


class ScenarioConfigSchema(BaseModel):
    duration_minutes: int = Field(60, ge=1, le=1440)
    tick_minutes: float = Field(1.0, gt=0, le=60)
    snapshot_interval_ticks: int = Field(5, ge=1, le=100)
    deterministic_seed: int = 42
    routing_engine_version: Optional[str] = "M8_LocalApproxRouter"
    coordination_version: Optional[str] = "M9_FleetCoordinator"


class ScenarioCreateRequest(BaseModel):
    scenario_id: Optional[str] = None
    name: str
    description: Optional[str] = ""
    config: Optional[ScenarioConfigSchema] = None
    scheduled_incidents: Optional[List[ScheduledIncidentSchema]] = None
    scheduled_mcis: Optional[List[ScheduledMCISchema]] = None
    scheduled_repositions: Optional[List[ScheduledRepositionSchema]] = None
    scheduled_redirections: Optional[List[ScheduledRedirectionSchema]] = None
    scheduled_hospital_events: Optional[List[ScheduledHospitalEventSchema]] = None
    metadata: Optional[Dict[str, Any]] = None


class ScenarioResponse(BaseModel):
    scenario_id: str
    name: str
    description: str
    config: ScenarioConfigSchema
    scheduled_incidents_count: int
    scheduled_mcis_count: int
    scheduled_repositions_count: int
    scheduled_redirections_count: int
    created_at: str


class ScenarioRunRequest(BaseModel):
    run_id: Optional[str] = None
    override_seed: Optional[int] = None
    duration_minutes: Optional[int] = None


class RunMetadataResponse(BaseModel):
    scenario_id: str
    run_id: str
    start_sim_time: int
    end_sim_time: int
    wall_clock_duration_seconds: float
    event_count: int
    snapshot_count: int
    completion_status: str
    deterministic_seed: int
    replay_format_version: str
    created_at: str


class ReplayStateResponse(BaseModel):
    sim_time: int
    current_event_index: int
    total_events: int
    progress_percent: float
    is_completed: bool
    incidents: List[Dict[str, Any]]
    ambulances: List[Dict[str, Any]]
    hospitals: List[Dict[str, Any]]
    active_mcis: List[Dict[str, Any]]
    repositioning: List[Dict[str, Any]]
    coverage_summary: Dict[str, Any]
