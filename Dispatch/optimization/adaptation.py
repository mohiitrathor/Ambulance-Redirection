"""
RAAH Adaptive Policy Recommendations, Versioning & A/B Evaluation (M11 Phase 4)
==============================================================================

Generates auditable, operator-facing recommendations to calibrate policy thresholds,
governs immutable PolicyConfig versioning, enables safe policy rollback, and supports
isolated offline A/B policy comparison.

HARD SAFETY INVARIANTS:
- May NEVER modify clinical ML models or predictions.
- May NEVER remove operator approval for hospital diversions or MCI clinical prioritizations.
- May NEVER lower fleet safety floor below hard minimum (2 units).
- May NEVER disable kill-switch, stale validation, or rollback safety checks.
"""

import os
import json
import uuid
import copy
import hashlib
import threading
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

from Dispatch.optimization.policy import PolicyConfig, AutonomyMode
from Dispatch.optimization.learning import (
    ConfidenceCalibration,
    PolicyPerformanceTrend,
    OutcomeRecord,
)
from Dispatch.optimization.drift import OperationalDrift, DriftSeverity


class RiskLevel:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AdaptationStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class LearningRecommendation:
    """
    Evidence-backed suggestion to adjust a configurable policy parameter.
    Requires explicit operator approval to take effect.
    """
    recommendation_id: str
    policy_parameter: str
    current_value: Any
    proposed_value: Any
    evidence: str
    confidence: float
    expected_effect: str
    risk_level: str = RiskLevel.LOW
    status: str = AdaptationStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = ""
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LearningRecommendation":
        return cls(
            recommendation_id=str(d.get("recommendation_id", "")),
            policy_parameter=str(d.get("policy_parameter", "")),
            current_value=d.get("current_value"),
            proposed_value=d.get("proposed_value"),
            evidence=str(d.get("evidence", "")),
            confidence=float(d.get("confidence", 0.9)),
            expected_effect=str(d.get("expected_effect", "")),
            risk_level=str(d.get("risk_level", RiskLevel.LOW)),
            status=str(d.get("status", AdaptationStatus.PENDING)),
            created_at=str(d.get("created_at", "")),
            expires_at=str(d.get("expires_at", "")),
            approved_by=d.get("approved_by"),
            approved_at=d.get("approved_at"),
            rejection_reason=d.get("rejection_reason"),
        )


_REPO_ROOT = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------------
# POLICY VERSION STORE (IMMUTABLE CONFIG HISTORY)
# ----------------------------------------------------------------------

class PolicyVersionStore:
    """
    Manages atomic, immutable versions of PolicyConfig under
    data/optimization/policy_versions/.
    Every update or rollback writes a new immutable version file.
    """

    DEFAULT_STORE_DIR = _REPO_ROOT / "data" / "optimization" / "policy_versions"

    def __init__(self, store_dir: Optional[Path] = None):
        self.store_dir = store_dir or self.DEFAULT_STORE_DIR
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_initial_version()

    def _ensure_initial_version(self):
        """Ensure initial baseline version v1 exists."""
        with self._lock:
            v1_file = self.store_dir / "v1.json"
            if not v1_file.exists():
                init_cfg = PolicyConfig(
                    policy_version="v1",
                    version="1.0.0",
                    change_reason="Initial production baseline",
                    approved_by="SYSTEM_INIT",
                )
                self._save_file("v1", init_cfg)

    def _save_file(self, ver_id: str, config: PolicyConfig):
        target_file = self.store_dir / f"{ver_id}.json"
        tmp_file = self.store_dir / f"{ver_id}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2)
        tmp_file.replace(target_file)

    def get_latest_version(self) -> PolicyConfig:
        """Retrieve the most recently created policy version."""
        with self._lock:
            versions = self._list_version_ids()
            if not versions:
                init_cfg = PolicyConfig(policy_version="v1")
                self._save_file("v1", init_cfg)
                return init_cfg
            latest_id = versions[-1]
            return self._load_file(latest_id)

    def get_version(self, version_id: str) -> Optional[PolicyConfig]:
        """Load a specific version by ID (e.g. 'v1')."""
        with self._lock:
            vid = version_id if version_id.startswith("v") else f"v{version_id}"
            file_path = self.store_dir / f"{vid}.json"
            if not file_path.exists():
                return None
            return self._load_file(vid)

    def save_new_version(
        self,
        config: PolicyConfig,
        reason: str,
        operator_id: str,
    ) -> PolicyConfig:
        """
        Create and persist a new immutable version (v2, v3, ...), linking parent.
        """
        with self._lock:
            versions = self._list_version_ids()
            next_num = 1
            if versions:
                nums = [int(v.replace("v", "")) for v in versions if v.replace("v", "").isdigit()]
                if nums:
                    next_num = max(nums) + 1
            new_ver_id = f"v{next_num}"

            new_cfg = copy.deepcopy(config)
            new_cfg.parent_version = config.policy_version
            new_cfg.policy_version = new_ver_id
            new_cfg.version = f"1.{next_num}.0"
            new_cfg.change_reason = reason
            new_cfg.approved_by = operator_id
            new_cfg.created_at = datetime.now(timezone.utc).isoformat()

            self._save_file(new_ver_id, new_cfg)
            return new_cfg

    def rollback_to_version(
        self,
        target_version_id: str,
        operator_id: str,
        reason: Optional[str] = None,
    ) -> PolicyConfig:
        """
        Rollback to a previous configuration by creating a NEW version
        that restores the parameters of target_version.
        Preserves complete historical audit trail without mutation.
        """
        target_cfg = self.get_version(target_version_id)
        if not target_cfg:
            raise ValueError(f"Target policy version '{target_version_id}' does not exist.")

        reason_str = reason if (reason and "rollback" in reason.lower()) else (f"Rollback to {target_version_id}: {reason}" if reason else f"Rollback configuration to {target_cfg.policy_version}")
        return self.save_new_version(target_cfg, reason=reason_str, operator_id=operator_id)

    def list_versions(self) -> List[Dict[str, Any]]:
        """List all policy versions in chronological order."""
        with self._lock:
            res = []
            for vid in self._list_version_ids():
                cfg = self._load_file(vid)
                if cfg:
                    res.append({
                        "version": cfg.policy_version,
                        "created_at": cfg.created_at,
                        "parent_version": cfg.parent_version,
                        "change_reason": cfg.change_reason,
                        "approved_by": cfg.approved_by,
                        "mode": cfg.mode,
                        "min_confidence_reposition": cfg.min_confidence_reposition,
                        "fleet_safety_floor": cfg.fleet_safety_floor,
                    })
            return res

    def _list_version_ids(self) -> List[str]:
        files = list(self.store_dir.glob("v*.json"))
        nums = []
        for f in files:
            stem = f.stem
            if stem.startswith("v") and stem[1:].isdigit():
                nums.append(int(stem[1:]))
        nums.sort()
        return [f"v{n}" for n in nums]

    def _load_file(self, ver_id: str) -> Optional[PolicyConfig]:
        target = self.store_dir / f"{ver_id}.json"
        if not target.exists():
            return None
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
            return PolicyConfig(
                mode=data.get("mode", AutonomyMode.GUARDED),
                min_confidence_reposition=float(data.get("min_confidence_reposition", 0.95)),
                min_confidence_diversion=float(data.get("min_confidence_diversion", 0.99)),
                min_action_interval_seconds=float(data.get("min_action_interval_seconds", 15.0)),
                zone_cooldown_ticks=int(data.get("zone_cooldown_ticks", 3)),
                max_autonomous_actions_per_window=int(data.get("max_autonomous_actions_per_window", 5)),
                window_size_ticks=int(data.get("window_size_ticks", 10)),
                max_consecutive_autonomous_actions=int(data.get("max_consecutive_autonomous_actions", 3)),
                fleet_safety_floor=int(data.get("fleet_safety_floor", 2)),
                allow_full_mode=bool(data.get("allow_full_mode", False)),
                kill_switch_active=bool(data.get("kill_switch_active", False)),
                version=data.get("version", "1.0.0"),
                policy_version=data.get("policy_version", ver_id),
                created_at=data.get("created_at", ""),
                parent_version=data.get("parent_version"),
                change_reason=data.get("change_reason"),
                approved_by=data.get("approved_by"),
            )


# ----------------------------------------------------------------------
# ADAPTIVE POLICY ADVISOR
# ----------------------------------------------------------------------

class AdaptivePolicyAdvisor:
    """
    Evaluates empirical outcomes, calibration stats, and drift signals to
    propose safe, operator-reviewed adjustments to policy parameters.
    """

    # Strictly enforced allowed ranges for policy tuning
    ALLOWED_PARAMETER_BOUNDS = {
        "min_confidence_reposition": (0.90, 0.99),
        "max_autonomous_actions_per_window": (1, 10),
        "window_size_ticks": (5, 30),
        "zone_cooldown_ticks": (1, 10),
        "min_action_interval_seconds": (5.0, 60.0),
        "fleet_safety_floor": (2, 5),          # Hard floor: NEVER below 2
    }

    FORBIDDEN_PARAMETERS = {
        "clinical_model",
        "predict_severity",
        "p1_p2_prioritization",
        "mci_clinical_triage",
        "min_confidence_diversion",             # Hospital diversion must stay operator-only
        "kill_switch_active",
        "allow_full_mode",
    }

    def __init__(self):
        self._recommendations_store: Dict[str, LearningRecommendation] = {}

    def generate_recommendations(
        self,
        calibration: ConfidenceCalibration,
        drift: OperationalDrift,
        performance: PolicyPerformanceTrend,
        current_config: PolicyConfig,
    ) -> List[LearningRecommendation]:
        """
        Synthesize recommendations based on empirical operational evidence.
        """
        recs: List[LearningRecommendation] = []

        # 1. Overconfidence Recalibration
        # If highest bucket (0.95–1.00) observed success is below 93%, recommend raising threshold
        high_bucket = None
        for b in calibration.buckets:
            if b.min_confidence >= 0.95:
                high_bucket = b
                break

        if high_bucket and high_bucket.executed_count >= 5:
            if high_bucket.empirical_success_rate < 0.93:
                curr_val = current_config.min_confidence_reposition
                new_val = min(0.98, round(curr_val + 0.02, 2))
                if new_val > curr_val:
                    rec_id = f"ADAPT_CONF_{uuid.uuid4().hex[:6].upper()}"
                    recs.append(LearningRecommendation(
                        recommendation_id=rec_id,
                        policy_parameter="min_confidence_reposition",
                        current_value=curr_val,
                        proposed_value=new_val,
                        evidence=f"Observed success rate in top confidence bucket is {high_bucket.empirical_success_rate:.1%}, below target 95% (calibration error {high_bucket.calibration_error:.1%}).",
                        confidence=0.92,
                        expected_effect=f"Reduces low-yield auto-repositions by tightening qualification threshold to {new_val:.2f}.",
                        risk_level=RiskLevel.LOW,
                    ))

        # 2. Rate Limit Throttling on Drift / High Harmful Rate
        if drift.severity in (DriftSeverity.DEGRADED, DriftSeverity.CRITICAL) or performance.harmful_actions >= 2:
            curr_rate = current_config.max_autonomous_actions_per_window
            if curr_rate > 2:
                new_rate = max(2, curr_rate - 2)
                rec_id = f"ADAPT_RATE_{uuid.uuid4().hex[:6].upper()}"
                recs.append(LearningRecommendation(
                    recommendation_id=rec_id,
                    policy_parameter="max_autonomous_actions_per_window",
                    current_value=curr_rate,
                    proposed_value=new_rate,
                    evidence=f"Operational drift is {drift.severity} with {performance.harmful_actions} harmful actions observed. Rolling window actions should be restricted.",
                    confidence=0.90,
                    expected_effect=f"Throttles autonomous action rate to max {new_rate} per {current_config.window_size_ticks} ticks to ensure stability.",
                    risk_level=RiskLevel.MEDIUM,
                ))

        # 3. Zone Cooldown Expansion on Anti-Oscillation Triggers
        if performance.harmful_actions >= 1 and current_config.zone_cooldown_ticks < 5:
            curr_cool = current_config.zone_cooldown_ticks
            new_cool = curr_cool + 2
            rec_id = f"ADAPT_COOL_{uuid.uuid4().hex[:6].upper()}"
            recs.append(LearningRecommendation(
                recommendation_id=rec_id,
                policy_parameter="zone_cooldown_ticks",
                current_value=curr_cool,
                proposed_value=new_cool,
                evidence="Harmful repositions detected; increasing zone stabilization cooldown period prevents fleet turbulence.",
                confidence=0.88,
                expected_effect=f"Increases zone cooldown from {curr_cool} to {new_cool} ticks.",
                risk_level=RiskLevel.LOW,
            ))

        # Index recommendations
        for r in recs:
            self._recommendations_store[r.recommendation_id] = r

        return recs

    def get_recommendation(self, rec_id: str) -> Optional[LearningRecommendation]:
        return self._recommendations_store.get(rec_id)

    def list_recommendations(self) -> List[LearningRecommendation]:
        return list(self._recommendations_store.values())

    def approve_recommendation(
        self,
        recommendation_id: str,
        operator_id: str,
        current_config: PolicyConfig,
        version_store: PolicyVersionStore,
    ) -> Tuple[PolicyConfig, LearningRecommendation]:
        """
        Validate safety bounds, apply parameter update, record new policy version,
        and mark recommendation APPROVED.
        """
        rec = self._recommendations_store.get(recommendation_id)
        if not rec:
            raise ValueError(f"Adaptive recommendation '{recommendation_id}' not found.")
        if rec.status != AdaptationStatus.PENDING:
            raise ValueError(f"Recommendation '{recommendation_id}' is not in PENDING state (current: {rec.status}).")

        param = rec.policy_parameter
        proposed = rec.proposed_value

        # Enforce Hard Safety Constraints
        if param in self.FORBIDDEN_PARAMETERS:
            raise ValueError(f"Safety Violation: Parameter '{param}' is protected and may never be modified.")

        if param in self.ALLOWED_PARAMETER_BOUNDS:
            min_val, max_val = self.ALLOWED_PARAMETER_BOUNDS[param]
            if not (min_val <= proposed <= max_val):
                raise ValueError(f"Safety Violation: Proposed value {proposed} for '{param}' violates safe bounds [{min_val}, {max_val}].")
        else:
            raise ValueError(f"Safety Violation: Parameter '{param}' is not a recognized configurable policy parameter.")

        # Apply update to new configuration copy
        new_config = copy.deepcopy(current_config)
        setattr(new_config, param, proposed)

        # Persist new immutable version
        reason = f"Applied adaptive recommendation {recommendation_id}: {param}={proposed} ({rec.expected_effect})"
        saved_config = version_store.save_new_version(new_config, reason=reason, operator_id=operator_id)

        # Mark recommendation approved
        rec.status = AdaptationStatus.APPROVED
        rec.approved_by = operator_id
        rec.approved_at = datetime.now(timezone.utc).isoformat()

        return saved_config, rec

    def reject_recommendation(
        self,
        recommendation_id: str,
        operator_id: str,
        reason: Optional[str] = None,
    ) -> LearningRecommendation:
        """Reject an adaptive recommendation with reason."""
        rec = self._recommendations_store.get(recommendation_id)
        if not rec:
            raise ValueError(f"Adaptive recommendation '{recommendation_id}' not found.")
        rec.status = AdaptationStatus.REJECTED
        rec.rejection_reason = reason or f"Dismissed by operator {operator_id}"
        return rec


# ----------------------------------------------------------------------
# A/B POLICY EVALUATOR (OFFLINE SIMULATION)
# ----------------------------------------------------------------------

class PolicyEvaluatorAB:
    """
    Simulates Policy A vs. Policy B offline against historical outcome distributions
    or replay scenarios without mutating the live simulator.
    """

    @classmethod
    def compare(
        cls,
        policy_a: PolicyConfig,
        policy_b: PolicyConfig,
        outcomes: List[OutcomeRecord],
    ) -> Dict[str, Any]:
        """
        Evaluate impact of Policy A vs. Policy B over a set of historical outcomes.
        """
        def eval_policy(cfg: PolicyConfig) -> Dict[str, Any]:
            auto_count = 0
            human_count = 0
            denied_count = 0
            harmful_count = 0
            total_benefit = 0.0

            for out in outcomes:
                # Check if action would qualify for autonomous execution under cfg
                if cfg.mode == AutonomyMode.GUARDED and out.recommendation_type == "FLEET_REPOSITION":
                    if out.confidence >= cfg.min_confidence_reposition and not cfg.kill_switch_active:
                        auto_count += 1
                        total_benefit += out.actual_benefit
                        if out.outcome == "HARMFUL":
                            harmful_count += 1
                    else:
                        human_count += 1
                        total_benefit += out.actual_benefit
                else:
                    human_count += 1
                    total_benefit += out.actual_benefit

            return {
                "policy_version": cfg.policy_version,
                "mode": cfg.mode,
                "confidence_threshold": cfg.min_confidence_reposition,
                "autonomous_actions": auto_count,
                "operator_actions": human_count,
                "denied_actions": denied_count,
                "harmful_actions": harmful_count,
                "net_realized_benefit": round(total_benefit, 4),
            }

        res_a = eval_policy(policy_a)
        res_b = eval_policy(policy_b)

        delta_auto = res_b["autonomous_actions"] - res_a["autonomous_actions"]
        delta_harm = res_b["harmful_actions"] - res_a["harmful_actions"]
        delta_benefit = round(res_b["net_realized_benefit"] - res_a["net_realized_benefit"], 4)

        if delta_harm < 0:
            rec_text = f"Policy B ({policy_b.policy_version}) reduces harmful actions by {abs(delta_harm)} with minimal benefit impact. Recommended."
        elif delta_auto > 0 and delta_harm == 0:
            rec_text = f"Policy B ({policy_b.policy_version}) increases autonomous coverage rebalancing by +{delta_auto} with zero increase in harmful actions. Recommended."
        else:
            rec_text = f"Policy A ({policy_a.policy_version}) maintains superior conservative bounds. Retain Policy A."

        comparison = {
            "policy_a": res_a,
            "policy_b": res_b,
            "deltas": {
                "autonomous_actions_delta": delta_auto,
                "harmful_actions_delta": delta_harm,
                "net_benefit_delta": delta_benefit,
            },
            "projected_risk": "LOW" if delta_harm <= 0 else "MEDIUM",
            "projected_benefit": f"Net benefit delta: {delta_benefit:+.3f}",
            "recommendation": rec_text,
        }
        return comparison
