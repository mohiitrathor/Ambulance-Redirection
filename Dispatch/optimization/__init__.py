"""
RAAH Optimization & Decision Intelligence Package (M11 Phase 4)
===============================================================

Safe, explainable real-time optimization, operator copilot, adaptive policy layer,
and outcome-driven operational learning. Supports observational scoring, what-if
decision simulation, operator approval, authoritative Simulator execution,
persistent audit trails, bounded autonomy policies, closed-loop telemetry,
confidence calibration, drift detection, and reversible policy adaptation.
"""

from .models import (
    OperationalSnapshot,
    OptimizationCandidate,
    DecisionExplanation,
    SimulationImpact,
    OptimizationRecommendation,
    RecommendationStatus,
    ApprovalRequest,
    ApprovalDecision,
    ExecutionResult,
    CopilotSummary,
)
from .policy import (
    AutonomyMode,
    PolicyDecisionType,
    OutcomeClassification,
    PolicyRule,
    PolicyConfig,
    PolicyEvaluation,
    PolicyOutcome,
    PolicyPerformance,
    ModeChangeEvent,
)
from .learning import (
    OutcomeRecord,
    RecommendationOutcome,
    CalibrationBucket,
    ConfidenceCalibration,
    PolicyPerformanceTrend,
    LearningSafetyScore,
    LearningReport,
    OutcomeStore,
    CalibrationAnalyzer,
    calculate_learning_safety_score,
)
from .drift import (
    OperationalDrift,
    DriftSeverity,
    DriftDetector,
)
from .adaptation import (
    LearningRecommendation,
    RiskLevel,
    AdaptationStatus,
    PolicyVersionStore,
    AdaptivePolicyAdvisor,
    PolicyEvaluatorAB,
)
from .observer import OperationalObserver
from .scorer import DecisionScorer, ScoringWeights
from .fleet_optimizer import FleetOptimizer
from .hospital_optimizer import HospitalOptimizer
from .simulator import DecisionSimulator
from .audit import ExecutionAuditStore
from .executor import OptimizationExecutor
from .policy_engine import AdaptivePolicyEngine
from .decision_engine import DecisionEngine

__all__ = [
    "OperationalSnapshot",
    "OptimizationCandidate",
    "DecisionExplanation",
    "SimulationImpact",
    "OptimizationRecommendation",
    "RecommendationStatus",
    "ApprovalRequest",
    "ApprovalDecision",
    "ExecutionResult",
    "CopilotSummary",
    "AutonomyMode",
    "PolicyDecisionType",
    "OutcomeClassification",
    "PolicyRule",
    "PolicyConfig",
    "PolicyEvaluation",
    "PolicyOutcome",
    "PolicyPerformance",
    "ModeChangeEvent",
    "OutcomeRecord",
    "RecommendationOutcome",
    "CalibrationBucket",
    "ConfidenceCalibration",
    "PolicyPerformanceTrend",
    "LearningSafetyScore",
    "LearningReport",
    "OutcomeStore",
    "CalibrationAnalyzer",
    "calculate_learning_safety_score",
    "OperationalDrift",
    "DriftSeverity",
    "DriftDetector",
    "LearningRecommendation",
    "RiskLevel",
    "AdaptationStatus",
    "PolicyVersionStore",
    "AdaptivePolicyAdvisor",
    "PolicyEvaluatorAB",
    "OperationalObserver",
    "DecisionScorer",
    "ScoringWeights",
    "FleetOptimizer",
    "HospitalOptimizer",
    "DecisionSimulator",
    "ExecutionAuditStore",
    "OptimizationExecutor",
    "AdaptivePolicyEngine",
    "DecisionEngine",
]
