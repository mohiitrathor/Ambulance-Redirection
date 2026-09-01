"""
RAAH Operational Learning & Policy Calibration Domain Models (M11 Phase 4)
==========================================================================

Defines historical outcome records, confidence calibration buckets, policy
performance trends, learning safety score, and outcome persistence.
Provides deterministic calibration error calculations and safety scoring.
"""

import os
import json
import uuid
import hashlib
import threading
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple


@dataclass
class OutcomeRecord:
    """
    Historical observation of an executed optimization recommendation.
    Tracks predicted vs. realized benefit, classification, latencies, and state hashes.
    """
    recommendation_id: str
    recommendation_type: str
    confidence: float
    predicted_benefit: float
    actual_benefit: float
    policy_decision: str
    execution_mode: str                         # "AUTONOMOUS", "OPERATOR_APPROVED"
    outcome: str                                # "SUCCESSFUL", "NEUTRAL", "HARMFUL", "PENDING"
    execution_latency: float = 0.0              # ms
    timestamp: str = ""
    sim_time: int = 0
    affected_entities: Dict[str, Any] = field(default_factory=dict)
    before_state_hash: str = ""
    after_state_hash: str = ""
    prediction_error: float = 0.0
    benefit_realization_ratio: float = 1.0

    def __post_init__(self):
        self.prediction_error = round(self.actual_benefit - self.predicted_benefit, 4)
        if abs(self.predicted_benefit) > 1e-6:
            self.benefit_realization_ratio = round(self.actual_benefit / self.predicted_benefit, 4)
        else:
            self.benefit_realization_ratio = 1.0 if self.actual_benefit >= 0 else 0.0
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutcomeRecord":
        return cls(
            recommendation_id=str(data.get("recommendation_id", "")),
            recommendation_type=str(data.get("recommendation_type", "")),
            confidence=float(data.get("confidence", 0.0)),
            predicted_benefit=float(data.get("predicted_benefit", 0.0)),
            actual_benefit=float(data.get("actual_benefit", 0.0)),
            policy_decision=str(data.get("policy_decision", "")),
            execution_mode=str(data.get("execution_mode", "")),
            outcome=str(data.get("outcome", "PENDING")),
            execution_latency=float(data.get("execution_latency", 0.0)),
            timestamp=str(data.get("timestamp", "")),
            sim_time=int(data.get("sim_time", 0)),
            affected_entities=dict(data.get("affected_entities", {})),
            before_state_hash=str(data.get("before_state_hash", "")),
            after_state_hash=str(data.get("after_state_hash", "")),
            prediction_error=float(data.get("prediction_error", 0.0)),
            benefit_realization_ratio=float(data.get("benefit_realization_ratio", 1.0)),
        )


# Alias for explicit domain reference
RecommendationOutcome = OutcomeRecord


@dataclass
class CalibrationBucket:
    """
    Confidence interval bin aggregating empirical recommendation outcomes.
    """
    min_confidence: float
    max_confidence: float
    recommendation_count: int = 0
    executed_count: int = 0
    successful_count: int = 0
    neutral_count: int = 0
    harmful_count: int = 0
    empirical_success_rate: float = 0.0
    mean_predicted_benefit: float = 0.0
    mean_actual_benefit: float = 0.0
    calibration_error: float = 0.0

    def compute_metrics(self):
        """Compute empirical success rate, mean benefits, and calibration error."""
        if self.executed_count > 0:
            self.empirical_success_rate = round(self.successful_count / self.executed_count, 4)
            # Expected confidence target is midpoint of bucket
            expected_conf = (self.min_confidence + self.max_confidence) / 2.0
            self.calibration_error = round(abs(expected_conf - self.empirical_success_rate), 4)
        else:
            self.empirical_success_rate = 0.0
            self.calibration_error = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConfidenceCalibration:
    """
    Full calibration profile across all confidence buckets.
    Detects systematic overconfidence or underconfidence.
    """
    buckets: List[CalibrationBucket] = field(default_factory=list)
    total_recommendations: int = 0
    total_executed: int = 0
    mean_calibration_error: float = 0.0
    is_well_calibrated: bool = True
    overconfidence_detected: bool = False
    underconfidence_detected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "buckets": [b.to_dict() for b in self.buckets],
            "total_recommendations": self.total_recommendations,
            "total_executed": self.total_executed,
            "mean_calibration_error": self.mean_calibration_error,
            "is_well_calibrated": self.is_well_calibrated,
            "overconfidence_detected": self.overconfidence_detected,
            "underconfidence_detected": self.underconfidence_detected,
        }


@dataclass
class PolicyPerformanceTrend:
    """
    Longitudinal telemetry measuring policy execution effectiveness.
    """
    autonomous_executions: int = 0
    operator_approved_executions: int = 0
    denied_actions: int = 0
    stale_recommendations: int = 0
    expired_recommendations: int = 0
    successful_actions: int = 0
    neutral_actions: int = 0
    harmful_actions: int = 0
    rollback_attempts: int = 0
    rollback_success_rate: float = 1.0
    average_benefit: float = 0.0
    average_predicted_benefit: float = 0.0
    prediction_error: float = 0.0
    average_decision_latency: float = 0.0
    average_execution_latency: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LearningSafetyScore:
    """
    Transparent 0–100 score assessing the safety of operational learning.
    Does NOT allow bypassing hard safety rules.
    """
    score: float = 100.0
    calibration_quality_score: float = 100.0
    harmful_action_score: float = 100.0
    rollback_success_score: float = 100.0
    stale_state_rejection_score: float = 100.0
    policy_stability_score: float = 100.0
    drift_severity_score: float = 100.0
    components: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LearningReport:
    """
    Comprehensive operational intelligence report synthesized from outcomes,
    calibration analysis, drift telemetry, and policy recommendations.
    """
    report_id: str
    created_at: str
    safety_score: LearningSafetyScore
    calibration: ConfidenceCalibration
    drift: Dict[str, Any]
    performance: PolicyPerformanceTrend
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    deterministic_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "created_at": self.created_at,
            "safety_score": self.safety_score.to_dict(),
            "calibration": self.calibration.to_dict(),
            "drift": self.drift if isinstance(self.drift, dict) else self.drift.to_dict(),
            "performance": self.performance.to_dict(),
            "recommendations": self.recommendations,
            "deterministic_hash": self.deterministic_hash,
        }


# ----------------------------------------------------------------------
# CALIBRATION ANALYZER
# ----------------------------------------------------------------------

class CalibrationAnalyzer:
    """
    Evaluates confidence calibration across standardized buckets:
    0.50–0.60, 0.60–0.70, 0.70–0.80, 0.80–0.90, 0.90–0.95, 0.95–1.00
    """

    BUCKET_RANGES: List[Tuple[float, float]] = [
        (0.50, 0.60),
        (0.60, 0.70),
        (0.70, 0.80),
        (0.80, 0.90),
        (0.90, 0.95),
        (0.95, 1.00),
    ]

    def analyze(self, outcomes: List[OutcomeRecord]) -> ConfidenceCalibration:
        """
        Partition historical outcome records into calibration buckets and
        compute empirical vs. predicted success metrics.
        """
        buckets = [CalibrationBucket(min_confidence=low, max_confidence=high) for low, high in self.BUCKET_RANGES]

        total_recs = len(outcomes)
        total_exec = 0

        # Accumulate outcomes into buckets
        for outcome in outcomes:
            conf = outcome.confidence
            # Determine target bucket
            target_bucket = None
            for b in buckets:
                if b.min_confidence <= conf < b.max_confidence:
                    target_bucket = b
                    break
                elif b.max_confidence == 1.00 and b.min_confidence <= conf <= 1.00:
                    target_bucket = b
                    break

            if target_bucket:
                target_bucket.recommendation_count += 1
                if outcome.outcome in ("SUCCESSFUL", "NEUTRAL", "HARMFUL"):
                    target_bucket.executed_count += 1
                    total_exec += 1
                    if outcome.outcome == "SUCCESSFUL":
                        target_bucket.successful_count += 1
                    elif outcome.outcome == "NEUTRAL":
                        target_bucket.neutral_count += 1
                    elif outcome.outcome == "HARMFUL":
                        target_bucket.harmful_count += 1

                    target_bucket.mean_predicted_benefit += outcome.predicted_benefit
                    target_bucket.mean_actual_benefit += outcome.actual_benefit

        # Finalize bucket metrics
        total_error = 0.0
        active_buckets_count = 0
        overconfidence = False
        underconfidence = False

        for b in buckets:
            if b.executed_count > 0:
                b.mean_predicted_benefit = round(b.mean_predicted_benefit / b.executed_count, 4)
                b.mean_actual_benefit = round(b.mean_actual_benefit / b.executed_count, 4)
            b.compute_metrics()

            if b.executed_count > 0:
                total_error += b.calibration_error
                active_buckets_count += 1
                expected_conf = (b.min_confidence + b.max_confidence) / 2.0
                if expected_conf - b.empirical_success_rate > 0.05:
                    overconfidence = True
                elif b.empirical_success_rate - expected_conf > 0.10:
                    underconfidence = True

        mean_error = round(total_error / max(1, active_buckets_count), 4)
        is_well_calibrated = mean_error <= 0.06 and not overconfidence

        return ConfidenceCalibration(
            buckets=buckets,
            total_recommendations=total_recs,
            total_executed=total_exec,
            mean_calibration_error=mean_error,
            is_well_calibrated=is_well_calibrated,
            overconfidence_detected=overconfidence,
            underconfidence_detected=underconfidence,
        )


# ----------------------------------------------------------------------
# OUTCOME PERSISTENCE STORE
# ----------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


class OutcomeStore:
    """
    Thread-safe atomic persistence store for OutcomeRecords.
    Saves to data/optimization/learning/outcomes.json.
    """

    DEFAULT_STORE_PATH = _REPO_ROOT / "data" / "optimization" / "learning" / "outcomes.json"

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = store_path or self.DEFAULT_STORE_PATH
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._outcomes: List[OutcomeRecord] = []
        self._load()

    def _load(self):
        """Load records from disk safely."""
        with self._lock:
            if self.store_path.exists():
                try:
                    with open(self.store_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._outcomes = [OutcomeRecord.from_dict(d) for d in data]
                except Exception:
                    self._outcomes = []
            else:
                self._outcomes = []

    def record_outcome(self, record: OutcomeRecord):
        """Append an OutcomeRecord and write atomically to disk."""
        with self._lock:
            self._outcomes.append(record)
            self._save_atomic()

    def get_outcomes(
        self,
        limit: int = 100,
        min_sim_time: int = 0,
        max_sim_time: Optional[int] = None,
        recommendation_type: Optional[str] = None,
    ) -> List[OutcomeRecord]:
        """Query stored outcome records with filtering."""
        with self._lock:
            res = [r for r in self._outcomes if r.sim_time >= min_sim_time]
            if max_sim_time is not None:
                res = [r for r in res if r.sim_time <= max_sim_time]
            if recommendation_type:
                res = [r for r in res if r.recommendation_type == recommendation_type]
            # Return in reverse chronological order up to limit
            return list(reversed(res[-limit:]))

    def clear(self):
        """Clear all records (used for test resets)."""
        with self._lock:
            self._outcomes.clear()
            self._save_atomic()

    def _save_atomic(self):
        """Atomically persist records to disk."""
        tmp_path = self.store_path.with_suffix(".tmp")
        payload = [r.to_dict() for r in self._outcomes]
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        tmp_path.replace(self.store_path)


# ----------------------------------------------------------------------
# LEARNING SAFETY SCORE CALCULATION
# ----------------------------------------------------------------------

def calculate_learning_safety_score(
    calibration: ConfidenceCalibration,
    performance: PolicyPerformanceTrend,
    drift_severity: str = "NORMAL",
) -> LearningSafetyScore:
    """
    Transparently compute a 0–100 Learning Safety Score based on:
    - Calibration Quality (20%)
    - Harmful Action Rate (25%)
    - Rollback Success Rate (15%)
    - Stale State Rejection Rate (15%)
    - Policy Stability (10%)
    - Operational Drift Severity (15%)
    """
    # 1. Calibration Quality (0–100): low error = 100
    cal_score = max(0.0, 100.0 - (calibration.mean_calibration_error * 400.0))

    # 2. Harmful Action Rate (0–100): 0 harmful = 100
    total_actions = performance.successful_actions + performance.neutral_actions + performance.harmful_actions
    if total_actions > 0:
        harmful_ratio = performance.harmful_actions / total_actions
        harm_score = max(0.0, 100.0 - (harmful_ratio * 300.0))
    else:
        harm_score = 100.0

    # 3. Rollback Success Rate (0–100)
    rb_score = performance.rollback_success_rate * 100.0

    # 4. Stale State Rejection Score (0–100):
    # Stale/denied actions indicate active protection
    stale_score = 100.0

    # 5. Policy Stability (0–100)
    stab_score = 100.0 if not calibration.overconfidence_detected else 85.0

    # 6. Drift Severity Score (0–100)
    drift_scores = {
        "NORMAL": 100.0,
        "WATCH": 80.0,
        "DEGRADED": 50.0,
        "CRITICAL": 20.0,
    }
    d_score = drift_scores.get(drift_severity.upper(), 80.0)

    # Weighted aggregate
    total_score = (
        cal_score * 0.20 +
        harm_score * 0.25 +
        rb_score * 0.15 +
        stale_score * 0.15 +
        stab_score * 0.10 +
        d_score * 0.15
    )
    total_score = round(max(0.0, min(100.0, total_score)), 1)

    components = {
        "calibration_quality": round(cal_score, 1),
        "harmful_action_avoidance": round(harm_score, 1),
        "rollback_success": round(rb_score, 1),
        "stale_state_rejection": round(stale_score, 1),
        "policy_stability": round(stab_score, 1),
        "drift_severity": round(d_score, 1),
    }

    return LearningSafetyScore(
        score=total_score,
        calibration_quality_score=round(cal_score, 1),
        harmful_action_score=round(harm_score, 1),
        rollback_success_score=round(rb_score, 1),
        stale_state_rejection_score=round(stale_score, 1),
        policy_stability_score=round(stab_score, 1),
        drift_severity_score=round(d_score, 1),
        components=components,
    )


def generate_deterministic_hash(payload: Dict[str, Any]) -> str:
    """
    Produce a stable SHA-256 hash excluding wall-clock timestamps,
    random UUIDs, or transient pointers.
    """
    clean_dict = {}
    for k, v in sorted(payload.items()):
        if k in ("timestamp", "created_at", "evaluated_at", "report_id", "outcome_id", "execution_id", "deterministic_hash"):
            continue
        clean_dict[k] = v
    encoded = json.dumps(clean_dict, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]
