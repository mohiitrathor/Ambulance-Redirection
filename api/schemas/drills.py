"""
RAAH Disaster Drill & Stress Testing API Schemas (M10 Phase 2)
==============================================================

Pydantic schemas for drill listing, deterministic execution,
stress surge testing, and comparative evaluations.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class DrillInfoResponse(BaseModel):
    name: str
    title: str
    description: str
    category: str
    default_parameters: Dict[str, Any]


class DrillRunRequest(BaseModel):
    drill_name: str
    seed: Optional[int] = 42
    parameters: Optional[Dict[str, Any]] = None


class StressRunRequest(BaseModel):
    casualty_count: int = Field(50, ge=1, le=500)
    seed: Optional[int] = 42
    mci_count: Optional[int] = Field(2, ge=1, le=10)
    duration_minutes: Optional[int] = Field(15, ge=5, le=120)
    hospital_surge: Optional[bool] = False


class ComparisonRunRequest(BaseModel):
    casualty_counts: Optional[List[int]] = Field(default_factory=lambda: [25, 50, 100])
    seed: Optional[int] = 42


class ResilienceScoreSchema(BaseModel):
    overall: float
    fleet_score: float
    dispatch_score: float
    hospital_score: float
    evacuation_score: float
    saturation_penalty: float
    unresolved_penalty: float


class StressRunResponse(BaseModel):
    scenario_id: str
    run_id: str
    drill_name: Optional[str]
    seed: int
    casualty_count: int
    total_simulation_minutes: int
    incidents_created: int
    incidents_dispatched: int
    incidents_waiting: int
    incidents_arrived: int
    ambulance_utilization: float
    hospital_saturation_events: int
    icu_saturation_events: int
    max_concurrent_en_route: int
    max_concurrent_mci: int
    average_response_eta: float
    average_transport_eta: float
    unresolved_incidents: int
    unresolved_mcis: int
    simulation_runtime_ms: float
    deterministic_hash: str
    metrics: Dict[str, Any]
    resilience_score: ResilienceScoreSchema
    created_at: str


class ComparisonRowResponse(BaseModel):
    scenario: str
    casualties: int
    dispatch_success_pct: float
    avg_eta_minutes: float
    unresolved_count: int
    hospital_saturation_count: int
    resilience_score: float
    runtime_ms: float
    deterministic_hash: str
    run_id: str
