"""
Pydantic Schemas for RAAH Optimization & Adaptive Policy APIs (M11 Phase 3)
==========================================================================
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class OperationalSnapshotResponse(BaseModel):
    sim_time: int
    fleet_availability: Dict[str, Any]
    fleet_utilization: float
    zone_coverage: Dict[str, Any]
    active_incidents: Dict[str, Any]
    active_mcis: List[Dict[str, Any]]
    hospital_projected_capacities: Dict[str, Any]
    incoming_reservations: int
    repositioning_units: List[str]
    active_redirections: int
    snapshot_hash: str


class DecisionExplanationSchema(BaseModel):
    decision_id: str
    summary: str
    reasons: List[str]
    supporting_metrics: Dict[str, Any]
    alternatives: List[Dict[str, Any]]
    risks: List[str]
    expected_benefit: str


class SimulationImpactSchema(BaseModel):
    candidate_id: str
    coverage_change: Dict[str, float]
    fleet_utilization_change: float
    hospital_projected_load_change: Dict[str, float]
    eta_impact_minutes: float
    affected_incidents_count: int
    affected_mcis_count: int
    resilience_impact: float
    is_better_than_baseline: bool
    summary: str


class ExecutionResultResponse(BaseModel):
    execution_id: str
    recommendation_id: str
    decision_type: str
    status: str                         # "SUCCESS", "FAILED", "OBSOLETE", "REJECTED"
    error_message: Optional[str] = None
    state_hash_before: str = ""
    state_hash_after: str = ""
    executed_at: str = ""
    affected_entities: Dict[str, Any] = Field(default_factory=dict)
    details: Dict[str, Any] = Field(default_factory=dict)


class OptimizationRecommendationResponse(BaseModel):
    recommendation_id: str
    decision_type: str
    severity: str
    score: float
    explanation: DecisionExplanationSchema
    candidate_action: Dict[str, Any]
    expires_at_sim_time: int
    status: str
    simulation_impact: Optional[SimulationImpactSchema] = None
    original_state_hash: Optional[str] = ""
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    execution_result: Optional[ExecutionResultResponse] = None
    rejection_reason: Optional[str] = None
    rejection_note: Optional[str] = None


class SimulateRecommendationRequest(BaseModel):
    recommendation_id: str


class ApproveRecommendationRequest(BaseModel):
    operator_id: str = "OPERATOR_DISPATCHER"
    operator_note: Optional[str] = None
    state_hash_at_approval: Optional[str] = None


class RejectRecommendationRequest(BaseModel):
    operator_id: str = "OPERATOR_DISPATCHER"
    reason: Optional[str] = "Operator dismissed recommendation"


class ExecutionAuditRecordResponse(BaseModel):
    execution_id: str
    recommendation_id: str
    recommendation_type: str
    operator_id: str
    operator_note: Optional[str] = None
    execution_mode: Optional[str] = "OPERATOR_APPROVED"
    policy_mode: Optional[str] = "GUARDED"
    policy_decision: Optional[str] = "AUTO_APPROVE"
    confidence: Optional[float] = 1.0
    policy_version: Optional[str] = "1.0.0"
    policy_rules_evaluated: Optional[List[str]] = Field(default_factory=list)
    policy_rejection_reason: Optional[str] = None
    predicted_benefit: Optional[float] = 0.0
    actual_benefit: Optional[float] = 0.0
    outcome: Optional[str] = "PENDING"
    rollback_of: Optional[str] = None
    kill_switch_state: Optional[bool] = False
    requested_at: str
    approved_at: str
    executed_at: str
    state_hash_before: str
    state_hash_after: str
    action_parameters: Dict[str, Any] = Field(default_factory=dict)
    execution_status: str
    failure_reason: Optional[str] = None
    resulting_entity_ids: Dict[str, Any] = Field(default_factory=dict)


class CopilotSummaryResponse(BaseModel):
    operational_health: str
    highest_priority_recommendation: Optional[Dict[str, Any]] = None
    pending_recommendations_count: int
    stale_recommendations_count: int
    recent_executions_count: int
    latest_execution_outcome: Optional[Dict[str, Any]] = None
    mode: str = "COPILOT_ADVISORY_READY"
    policy_mode: Optional[str] = "GUARDED"
    operating_policy_version: Optional[str] = "v1"
    kill_switch_active: Optional[bool] = False
    autonomous_actions_executed: Optional[int] = 0
    policy_performance: Optional[Dict[str, Any]] = None
    drift_severity: Optional[str] = "NORMAL"
    learning_safety_score: Optional[float] = 100.0


class OptimizationHealthResponse(BaseModel):
    status: str = "OPERATIONAL"
    mode: str = "GUARDED_SEMI_AUTONOMOUS"
    active_recommendations_count: int
    last_evaluated_sim_time: int
    autonomous_execution_enabled: bool = True


# ----------------------------------------------------------------------
# M11 PHASE 3: ADAPTIVE POLICY SCHEMAS
# ----------------------------------------------------------------------

class PolicyConfigResponse(BaseModel):
    mode: str
    min_confidence_reposition: float
    min_confidence_diversion: float
    min_action_interval_seconds: float
    zone_cooldown_ticks: int
    max_autonomous_actions_per_window: int
    window_size_ticks: int
    max_consecutive_autonomous_actions: int
    fleet_safety_floor: int
    allow_full_mode: bool
    kill_switch_active: bool
    version: str
    policy_version: Optional[str] = "v1"
    created_at: Optional[str] = ""
    parent_version: Optional[str] = None
    change_reason: Optional[str] = None
    approved_by: Optional[str] = None


class ChangePolicyModeRequest(BaseModel):
    mode: str                           # "OFF", "ADVISORY", "GUARDED"
    operator_id: str = "OPERATOR_COMMANDER"
    reason: Optional[str] = None


class ChangePolicyModeResponse(BaseModel):
    event_id: str
    previous_mode: str
    new_mode: str
    operator_id: str
    reason: Optional[str] = None
    timestamp: str


class KillSwitchRequest(BaseModel):
    operator_id: str = "OPERATOR_COMMANDER"
    reason: Optional[str] = "Emergency operator kill-switch triggered"
    action: str = "ENGAGE"              # "ENGAGE" or "RELEASE"


class KillSwitchResponse(BaseModel):
    kill_switch_active: bool
    event: Dict[str, Any]


class PolicyEvaluationResponse(BaseModel):
    recommendation_id: str
    decision_type: str
    policy_decision: str                # AUTO_APPROVE, REQUIRE_OPERATOR, DENY
    confidence: float
    confidence_threshold: float
    score: float
    reason: str
    rules_evaluated: List[str]
    rules_passed: List[str]
    rules_failed: List[str]
    violations: List[str]
    policy_mode: str
    evaluated_at: str


class EvaluatePolicyRequest(BaseModel):
    recommendation_id: str


class RollbackRequest(BaseModel):
    operator_id: str = "OPERATOR_DISPATCHER"
    reason: Optional[str] = "Operator requested repositioning rollback"


class PolicyPerformanceResponse(BaseModel):
    autonomous_actions_attempted: int
    autonomous_actions_executed: int
    blocked_actions: int
    operator_approvals: int
    operator_rejections: int
    successful_actions: int
    neutral_actions: int
    harmful_actions: int
    rollback_attempts: int
    rollback_successes: int
    policy_violations_count: int
    avg_predicted_benefit: float
    avg_actual_benefit: float


# ----------------------------------------------------------------------
# M11 PHASE 4: OPERATIONAL LEARNING, CALIBRATION & ADAPTATION SCHEMAS
# ----------------------------------------------------------------------

class CalibrationBucketSchema(BaseModel):
    min_confidence: float
    max_confidence: float
    recommendation_count: int
    executed_count: int
    successful_count: int
    neutral_count: int
    harmful_count: int
    empirical_success_rate: float
    mean_predicted_benefit: float
    mean_actual_benefit: float
    calibration_error: float


class ConfidenceCalibrationResponse(BaseModel):
    buckets: List[CalibrationBucketSchema]
    total_recommendations: int
    total_executed: int
    mean_calibration_error: float
    is_well_calibrated: bool
    overconfidence_detected: bool
    underconfidence_detected: bool


class OperationalDriftResponse(BaseModel):
    severity: str                       # NORMAL, WATCH, DEGRADED, CRITICAL
    overall_drift_score: float
    eta_drift_pct: float
    coverage_drift_pct: float
    hospital_saturation_drift_pct: float
    success_rate_drift_pct: float
    benefit_realization_drift_pct: float
    unresolved_casualty_drift_pct: float
    volume_drift_pct: float
    stale_rate_drift_pct: float
    baseline_metrics: Dict[str, float]
    current_metrics: Dict[str, float]
    signals: List[str]
    deterministic_hash: str


class PolicyPerformanceTrendResponse(BaseModel):
    autonomous_executions: int
    operator_approved_executions: int
    denied_actions: int
    stale_recommendations: int
    expired_recommendations: int
    successful_actions: int
    neutral_actions: int
    harmful_actions: int
    rollback_attempts: int
    rollback_success_rate: float
    average_benefit: float
    average_predicted_benefit: float
    prediction_error: float
    average_decision_latency: float
    average_execution_latency: float


class LearningSafetyScoreSchema(BaseModel):
    score: float
    calibration_quality_score: float
    harmful_action_score: float
    rollback_success_score: float
    stale_state_rejection_score: float
    policy_stability_score: float
    drift_severity_score: float
    components: Dict[str, float]


class LearningRecommendationResponse(BaseModel):
    recommendation_id: str
    policy_parameter: str
    current_value: Any
    proposed_value: Any
    evidence: str
    confidence: float
    expected_effect: str
    risk_level: str
    status: str
    created_at: str
    expires_at: str = ""
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None


class ApproveLearningRecRequest(BaseModel):
    operator_id: str = "OPERATOR_DISPATCHER"


class ApproveLearningRecResponse(BaseModel):
    recommendation: LearningRecommendationResponse
    new_policy: PolicyConfigResponse


class RejectLearningRecRequest(BaseModel):
    operator_id: str = "OPERATOR_DISPATCHER"
    reason: Optional[str] = None


class ComparePoliciesRequest(BaseModel):
    policy_a: Optional[Dict[str, Any]] = None
    policy_b: Optional[Dict[str, Any]] = None


class ComparePoliciesResponse(BaseModel):
    policy_a: Dict[str, Any]
    policy_b: Dict[str, Any]
    deltas: Dict[str, Any]
    projected_risk: str
    projected_benefit: str
    recommendation: str


class PolicyVersionSummaryResponse(BaseModel):
    version: str
    created_at: str
    parent_version: Optional[str] = None
    change_reason: Optional[str] = None
    approved_by: Optional[str] = None
    mode: str
    min_confidence_reposition: float
    fleet_safety_floor: int


class RollbackPolicyVersionRequest(BaseModel):
    operator_id: str = "OPERATOR_DISPATCHER"
    reason: Optional[str] = None


class LearningReportResponse(BaseModel):
    report_id: str
    created_at: str
    safety_score: LearningSafetyScoreSchema
    calibration: ConfidenceCalibrationResponse
    drift: OperationalDriftResponse
    performance: PolicyPerformanceTrendResponse
    recommendations: List[Dict[str, Any]]
    deterministic_hash: str

