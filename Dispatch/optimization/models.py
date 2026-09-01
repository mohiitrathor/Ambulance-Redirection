"""
RAAH Real-Time Optimization Models (M11 Phase 2)
=================================================

Immutable and serializable domain models for the operational observer,
optimization candidates, explainable recommendations, what-if simulations,
operator approval decisions, authoritative execution results, and copilot summaries.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
import hashlib
import json


class RecommendationStatus:
    """Explicit lifecycle states for optimization recommendations."""
    NEW = "NEW"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    OBSOLETE = "OBSOLETE"
    FAILED = "FAILED"


@dataclass
class OperationalSnapshot:
    """Read-only capture of current operational simulator state."""
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
    snapshot_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OptimizationCandidate:
    """Proposed candidate action evaluated against operational constraints."""
    candidate_id: str
    decision_type: str                  # "FLEET_REPOSITION", "HOSPITAL_DIVERSION", "MCI_INTERCEPTION"
    priority: str                       # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    affected_entities: Dict[str, Any]   # Entities involved (ambulance_id, hospital_id, etc.)
    target: str                         # Target zone or facility
    expected_effect: str
    confidence: float                   # 0.0 to 1.0
    score: float                        # 0.0 to 1.0 composite score
    rationale: str
    constraints: List[str]
    generated_at_sim_time: int
    rejected: bool = False
    rejection_reason: Optional[str] = None
    score_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionExplanation:
    """Deep, explainable operational reasoning supporting a recommendation."""
    decision_id: str
    summary: str
    reasons: List[str]
    supporting_metrics: Dict[str, Any]
    alternatives: List[Dict[str, Any]]
    risks: List[str]
    expected_benefit: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationImpact:
    """Result of an isolated what-if decision simulation."""
    candidate_id: str
    coverage_change: Dict[str, float]                 # zone_id -> delta coverage score
    fleet_utilization_change: float                   # delta utilization pct
    hospital_projected_load_change: Dict[str, float]  # hospital_id -> delta beds/load
    eta_impact_minutes: float                         # delta ETA (negative = faster)
    affected_incidents_count: int
    affected_mcis_count: int
    resilience_impact: float                          # estimated resilience point delta
    is_better_than_baseline: bool
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionResult:
    """Result of authoritatively applying an approved optimization recommendation."""
    execution_id: str
    recommendation_id: str
    decision_type: str
    status: str                         # "SUCCESS", "FAILED", "OBSOLETE", "REJECTED"
    error_message: Optional[str] = None
    state_hash_before: str = ""
    state_hash_after: str = ""
    executed_at: str = ""
    affected_entities: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovalRequest:
    """Operator submission to approve an actionable recommendation."""
    recommendation_id: str
    operator_id: str = "OPERATOR_DISPATCHER"
    operator_note: Optional[str] = None
    state_hash_at_approval: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovalDecision:
    """Audit record of operator approval or rejection decision."""
    decision_id: str
    recommendation_id: str
    decision: str                       # "APPROVED", "REJECTED"
    operator_id: str
    operator_note: Optional[str] = None
    decided_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OptimizationRecommendation:
    """Actionable recommendation presented to dispatch operators with full lifecycle."""
    recommendation_id: str
    decision_type: str
    severity: str                       # "INFO", "WARNING", "CRITICAL"
    score: float
    explanation: DecisionExplanation
    candidate_action: Dict[str, Any]
    expires_at_sim_time: int
    status: str = RecommendationStatus.NEW  # NEW, REVIEWED, APPROVED, EXECUTING, EXECUTED, REJECTED, EXPIRED, OBSOLETE, FAILED
    simulation_impact: Optional[SimulationImpact] = None
    original_state_hash: str = ""
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    execution_result: Optional[ExecutionResult] = None
    rejection_reason: Optional[str] = None
    rejection_note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class CopilotSummary:
    """Real-time summary of copilot health, alerts, and recent execution outcomes."""
    operational_health: str
    highest_priority_recommendation: Optional[Dict[str, Any]]
    pending_recommendations_count: int
    stale_recommendations_count: int
    recent_executions_count: int
    latest_execution_outcome: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
