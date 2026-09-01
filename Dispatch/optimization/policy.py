"""
RAAH Adaptive Policy Domain Models (M11 Phase 3)
================================================

Immutable and serializable domain models for the Adaptive Policy Engine:
- Autonomy modes (OFF, ADVISORY, GUARDED, FULL)
- Policy decisions (AUTO_APPROVE, REQUIRE_OPERATOR, DENY)
- Configurable confidence thresholds and operational guardrails
- Policy evaluations and explainable reasons
- Operational outcome feedback (SUCCESSFUL, NEUTRAL, HARMFUL)
- Policy performance metrics and rollback records
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import json


class AutonomyMode:
    """Bounded autonomy operation modes."""
    OFF = "OFF"                # All autonomous actions disabled, recommendations advisory only
    ADVISORY = "ADVISORY"      # Evaluates policy rules without executing; all actions require human approval
    GUARDED = "GUARDED"        # Default production mode; low-risk, high-confidence fleet repositioning auto-executes
    FULL = "FULL"              # High autonomy; strictly disabled/unavailable by default


class PolicyDecisionType:
    """Decisions rendered by the Adaptive Policy Engine."""
    AUTO_APPROVE = "AUTO_APPROVE"           # Satisfies all guardrails, safe for autonomous execution
    REQUIRE_OPERATOR = "REQUIRE_OPERATOR"   # Requires explicit operator confirmation
    DENY = "DENY"                           # Action violates hard safety floors or anti-oscillation


class OutcomeClassification:
    """Classification of measured operational outcomes following action."""
    SUCCESSFUL = "SUCCESSFUL"   # Resulting state improved coverage, ETA, or balance
    NEUTRAL = "NEUTRAL"         # Resulting state had negligible delta
    HARMFUL = "HARMFUL"         # Resulting state degraded coverage or violated constraints
    PENDING = "PENDING"         # Action executed, awaiting downstream evaluation


@dataclass
class PolicyRule:
    """Individual operational safety rule or guardrail evaluated by the policy engine."""
    rule_id: str
    name: str
    description: str
    category: str               # "SAFETY", "CLINICAL", "CONFIDENCE", "COOLDOWN", "STABILITY"
    blocking: bool = True       # If True, failure forces REQUIRE_OPERATOR or DENY

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyConfig:
    """Configurable parameters governing the Adaptive Policy Engine."""
    mode: str = AutonomyMode.GUARDED
    min_confidence_reposition: float = 0.95
    min_confidence_diversion: float = 0.99      # Diversion always requires operator regardless of score
    min_action_interval_seconds: float = 15.0   # Cooldown between any autonomous actions
    zone_cooldown_ticks: int = 3                # Simulation ticks before a zone can be modified again
    max_autonomous_actions_per_window: int = 5  # Rate limit within rolling window
    window_size_ticks: int = 10                 # Rolling window length in ticks
    max_consecutive_autonomous_actions: int = 3 # Consecutive actions before mandatory operator check
    fleet_safety_floor: int = 2                 # Minimum available ambulances donor zone must retain
    allow_full_mode: bool = False               # FULL mode is disabled by default
    kill_switch_active: bool = False            # Emergency override stopping all autonomous execution
    version: str = "1.0.0"
    policy_version: str = "v1"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parent_version: Optional[str] = None
    change_reason: Optional[str] = None
    approved_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)



@dataclass
class PolicyEvaluation:
    """Result of evaluating a recommendation against active policy rules and guardrails."""
    recommendation_id: str
    decision_type: str
    policy_decision: str                        # AUTO_APPROVE, REQUIRE_OPERATOR, DENY
    confidence: float
    confidence_threshold: float
    score: float
    reason: str
    rules_evaluated: List[str] = field(default_factory=list)
    rules_passed: List[str] = field(default_factory=list)
    rules_failed: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    policy_mode: str = AutonomyMode.GUARDED
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyOutcome:
    """Measured feedback comparing pre-action predictions with post-action reality."""
    outcome_id: str
    execution_id: str
    recommendation_id: str
    decision_type: str
    classification: str                         # SUCCESSFUL, NEUTRAL, HARMFUL, PENDING
    predicted_benefit: float
    actual_benefit: float
    metrics_before: Dict[str, Any] = field(default_factory=dict)
    metrics_after: Dict[str, Any] = field(default_factory=dict)
    delta_coverage: float = 0.0
    delta_utilization: float = 0.0
    measured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyPerformance:
    """Aggregated operational telemetry and KPI metrics for the Adaptive Policy Engine."""
    autonomous_actions_attempted: int = 0
    autonomous_actions_executed: int = 0
    blocked_actions: int = 0
    operator_approvals: int = 0
    operator_rejections: int = 0
    successful_actions: int = 0
    neutral_actions: int = 0
    harmful_actions: int = 0
    rollback_attempts: int = 0
    rollback_successes: int = 0
    policy_violations_count: int = 0
    avg_predicted_benefit: float = 0.0
    avg_actual_benefit: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModeChangeEvent:
    """Audit record capturing an operator-initiated policy mode change."""
    event_id: str
    previous_mode: str
    new_mode: str
    operator_id: str
    reason: Optional[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
