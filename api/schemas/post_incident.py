"""
RAAH Post-Incident Review & Continuous Regression Schemas (M10 Phase 4)
======================================================================
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class PostIncidentFindingSchema(BaseModel):
    finding_id: str
    category: str
    severity: str
    confidence: float
    title: str
    description: str
    evidence: Dict[str, Any]
    measurable_impact: str
    potential_causes: List[str]
    recommendation_id: Optional[str] = None


class RootCauseNodeSchema(BaseModel):
    node_id: str
    category: str
    label: str
    severity: str
    details: Dict[str, Any] = {}


class RootCauseEdgeSchema(BaseModel):
    source_id: str
    target_id: str
    relation: str = "CAUSES"
    confidence: float = 1.0


class RootCauseGraphSchema(BaseModel):
    nodes: List[RootCauseNodeSchema] = []
    edges: List[RootCauseEdgeSchema] = []


class OperationalRecommendationSchema(BaseModel):
    recommendation_id: str
    category: str
    priority: str
    issue: str
    evidence: str
    action: str
    expected_benefit: str


class PostIncidentReviewResponse(BaseModel):
    run_id: str
    scenario_id: str
    generated_at: str
    overall_severity: str
    resilience_score: float
    summary: str
    metrics: Dict[str, Any]
    findings: List[PostIncidentFindingSchema] = []
    root_cause_graph: RootCauseGraphSchema = Field(default_factory=RootCauseGraphSchema)
    cascading_failures: List[List[str]] = []
    recommendations: List[OperationalRecommendationSchema] = []
    key_events: List[Dict[str, Any]] = []
    analysis_hash: str


class PIRReportRequest(BaseModel):
    format: str = Field("json", description="Output format: 'json', 'markdown', or 'html'")


class PIRReportResponse(BaseModel):
    run_id: str
    scenario_id: str
    format: str
    content: Any


class PIRCompareRequest(BaseModel):
    run_id_a: str = Field(..., description="Baseline run ID")
    run_id_b: str = Field(..., description="Comparative run ID")


class PIRCompareResponse(BaseModel):
    run_id_a: str
    run_id_b: str
    resilience_score_a: float
    resilience_score_b: float
    delta_resilience: float
    new_failures: List[Dict[str, Any]]
    resolved_failures: List[Dict[str, Any]]
    worsened_metrics: List[Dict[str, Any]]
    improved_metrics: List[Dict[str, Any]]
    severity_change: str


class CreateBaselineRequest(BaseModel):
    description: str = Field("Standard Regression Baseline", description="Baseline description")


class RegressionRunRequest(BaseModel):
    run_id: Optional[str] = Field(None, description="Optional custom run ID")


class RegressionResultSchema(BaseModel):
    case_id: str
    scenario_id: str
    seed: int
    status: str
    baseline_resilience: float
    current_resilience: float
    delta_resilience: float
    baseline_eta: float
    current_eta: float
    delta_eta: float
    baseline_dispatch_success_pct: float
    current_dispatch_success_pct: float
    delta_dispatch_success_pct: float
    baseline_unresolved: int
    current_unresolved: int
    delta_unresolved: int
    deterministic_hash: str
    baseline_hash: Optional[str] = None
    hash_matched: bool = True
    violations: List[str] = []


class RegressionReportResponse(BaseModel):
    run_id: str
    baseline_version: str
    candidate_version: str
    started_at: str
    completed_at: str
    total_cases: int
    passed_cases: int
    warned_cases: int
    failed_cases: int
    overall_status: str
    cases: List[RegressionResultSchema] = []
