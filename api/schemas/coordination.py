"""
RAAH Coordination API Schemas
=============================

Pydantic models for coverage queries, repositioning advisories,
and execution requests/responses.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ZoneCoverageResponse(BaseModel):
    """Real-time metrics for an operational zone."""
    zone_id: str
    zone_name: str
    centroid: List[float]
    staging_post: List[float]
    target_capacity: int
    available_count: int
    total_count: int
    demand_weight: float
    coverage_score: float
    status: str


class CoverageSummaryResponse(BaseModel):
    """Citywide coverage response across all 6 zones."""
    sim_time: int
    zones: Dict[str, ZoneCoverageResponse]
    deficit_count: int
    surplus_count: int


class RepositionAdvisoryResponse(BaseModel):
    """Advisory recommendation for idle ambulance repositioning."""
    advisory_id: str
    ambulance_id: str
    origin_zone: str
    target_zone: str
    origin_coords: List[float]
    target_staging_post: List[float]
    reason: str
    priority: str


class RepositionExecuteRequest(BaseModel):
    """Operator request to execute a repositioning movement."""
    ambulance_id: str
    target_lat: float = Field(..., ge=-90.0, le=90.0)
    target_lon: float = Field(..., ge=-180.0, le=180.0)
    reason: Optional[str] = "COVERAGE_DEFICIT"


class RepositionResponse(BaseModel):
    """Response returned upon reposition execution or cancellation."""
    status: str
    ambulance_id: str
    origin_zone: Optional[str] = None
    target_zone: Optional[str] = None
    target_coords: Optional[List[float]] = None
    route_distance_km: Optional[float] = None
    eta_minutes: Optional[float] = None
    route_waypoints: Optional[List[List[float]]] = None
    message: Optional[str] = None


class HospitalProjectionResponse(BaseModel):
    """Predictive hospital capacity and in-flight load metrics."""
    hospital_id: str
    current_load: int
    capacity: int
    current_available_beds: int
    projected_available_beds: int
    icu_capacity: int
    current_icu_load: int
    projected_available_icu: int
    incoming_count: int
    incoming_critical: int
    utilization_ratio: float
    projected_utilization_ratio: float
    status: str


class MCIDeclareRequest(BaseModel):
    """Payload for declaring a Multi-Casualty Incident."""
    mci_id: Optional[str] = None
    name: Optional[str] = "Multi-Casualty Incident"
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    estimated_casualties: int = Field(..., ge=1, le=100)
    primary_condition: Optional[str] = "Trauma"
    description: Optional[str] = ""
    notes: Optional[str] = ""
    casualties: Optional[List[Dict[str, Any]]] = None


class MCIChildSummary(BaseModel):
    """Summary of a child incident triaged and dispatched under an MCI."""
    incident_id: int
    severity: str
    priority: int
    status: str
    ambulance_id: Optional[str] = None
    hospital_id: Optional[str] = None
    eta_minutes: Optional[float] = None


class MCIEventResponse(BaseModel):
    """Full details of a Multi-Casualty Incident."""
    mci_id: str
    name: str
    description: Optional[str] = ""
    latitude: float
    longitude: float
    declared_sim_time: int
    resolved_sim_time: Optional[int] = None
    status: str
    total_casualties: int
    evacuated_count: int = 0
    child_incident_ids: List[int] = Field(default_factory=list)
    casualty_counts_by_severity: Dict[str, int] = Field(default_factory=dict)
    casualty_counts_by_priority: Dict[str, int] = Field(default_factory=dict)
    assigned_ambulance_ids: List[str] = Field(default_factory=list)
    hospital_distribution: Dict[str, int] = Field(default_factory=dict)
    notes: Optional[str] = ""


class MCIDeclareResponse(BaseModel):
    """Response returned upon MCI declaration and batch dispatch."""
    status: str
    mci: MCIEventResponse
    child_incidents: List[MCIChildSummary]
    dispatched_count: int
    waiting_count: int
    message: str


