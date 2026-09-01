"""
RAAH Decision Engine (M11 Phase 2)
==================================

Unified Decision Intelligence Engine combining FleetOptimizer and HospitalOptimizer.
Evaluates the current operational state, enforces constraints, ranks recommendations
deterministically, executes isolated what-if impact simulations, and bridges approved
actions into authoritative Simulator executions with audit logging.
"""

import threading
from typing import List, Dict, Any, Optional, Tuple
import time
from datetime import datetime, timezone

from Dispatch.optimization.models import (
    OperationalSnapshot,
    OptimizationCandidate,
    OptimizationRecommendation,
    SimulationImpact,
    ExecutionResult,
    RecommendationStatus,
)
from Dispatch.optimization.observer import OperationalObserver
from Dispatch.optimization.fleet_optimizer import FleetOptimizer
from Dispatch.optimization.hospital_optimizer import HospitalOptimizer
from Dispatch.optimization.simulator import DecisionSimulator
from Dispatch.optimization.scorer import DecisionScorer
from Dispatch.optimization.audit import ExecutionAuditStore
from Dispatch.optimization.executor import OptimizationExecutor


from Dispatch.optimization.policy import (
    PolicyEvaluation,
    PolicyPerformance,
    AutonomyMode,
)
from Dispatch.optimization.policy_engine import AdaptivePolicyEngine


class DecisionEngine:
    """Unified decision intelligence, adaptive policy, and operator copilot engine."""

    PRIORITY_RANKS = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }

    def __init__(
        self,
        observer: Optional[OperationalObserver] = None,
        fleet_optimizer: Optional[FleetOptimizer] = None,
        hospital_optimizer: Optional[HospitalOptimizer] = None,
        simulator: Optional[DecisionSimulator] = None,
        scorer: Optional[DecisionScorer] = None,
        audit_store: Optional[ExecutionAuditStore] = None,
        executor: Optional[OptimizationExecutor] = None,
        policy_engine: Optional[AdaptivePolicyEngine] = None,
    ):
        self.scorer = scorer or DecisionScorer()
        self.observer = observer or OperationalObserver()
        self.fleet_optimizer = fleet_optimizer or FleetOptimizer(scorer=self.scorer)
        self.hospital_optimizer = hospital_optimizer or HospitalOptimizer(scorer=self.scorer)
        self.simulator = simulator or DecisionSimulator()
        self.audit_store = audit_store or ExecutionAuditStore()
        self.executor = executor or OptimizationExecutor(
            observer=self.observer,
            audit_store=self.audit_store,
        )
        self.policy_engine = policy_engine or AdaptivePolicyEngine(
            audit_store=self.audit_store
        )
        self.outcome_store = self.policy_engine.outcome_store
        self.version_store = self.policy_engine.version_store

        from Dispatch.optimization.learning import CalibrationAnalyzer
        from Dispatch.optimization.drift import DriftDetector
        from Dispatch.optimization.adaptation import AdaptivePolicyAdvisor

        self.calibration_analyzer = CalibrationAnalyzer()
        self.drift_detector = DriftDetector()
        self.adaptation_advisor = AdaptivePolicyAdvisor()

        # Dedicated reentrant lock for internal indices and mutable recommendation state
        self._lock = threading.RLock()
        self._recommendations_index: Dict[str, OptimizationRecommendation] = {}
        self._candidates_index: Dict[str, OptimizationCandidate] = {}
        self._last_snapshot: Optional[OperationalSnapshot] = None

    def get_snapshot(self, sim_instance) -> OperationalSnapshot:
        """Capture and return the current operational snapshot."""
        snap = self.observer.capture_snapshot(sim_instance)
        with self._lock:
            self._last_snapshot = snap
        return snap

    def evaluate_state(self, sim_instance) -> List[OptimizationRecommendation]:
        """
        Observe current simulator state, generate fleet and hospital candidates,
        filter against constraints, auto-expire obsolete recommendations, and
        rank valid recommendations deterministically.
        """
        snapshot = self.get_snapshot(sim_instance)
        current_sim_time = snapshot.sim_time

        # --------------------------------------------------------------
        # 1. AUTO-DISMISSAL / EXPIRATION PASS ON EXISTING RECOMMENDATIONS
        # --------------------------------------------------------------
        ambs = sim_instance.state.ambulances
        with self._lock:
            for rid, existing_rec in list(self._recommendations_index.items()):
                if existing_rec.status in (RecommendationStatus.NEW, "ACTIVE", RecommendationStatus.REVIEWED):
                    if current_sim_time > existing_rec.expires_at_sim_time:
                        existing_rec.status = RecommendationStatus.EXPIRED
                        existing_rec.rejection_reason = "TTL expired before operator approval."
                    elif existing_rec.decision_type == "FLEET_REPOSITION":
                        aid = existing_rec.candidate_action.get("ambulance_id")
                        if aid and aid in ambs:
                            if str(ambs[aid].status).upper() != "AVAILABLE":
                                existing_rec.status = RecommendationStatus.OBSOLETE
                                existing_rec.rejection_reason = f"Ambulance '{aid}' is no longer available (now {ambs[aid].status})."

        # --------------------------------------------------------------
        # 2. GENERATE NEW CANDIDATES
        # --------------------------------------------------------------
        candidates: List[OptimizationCandidate] = []

        fleet_cands = self.fleet_optimizer.generate_candidates(snapshot)
        candidates.extend(fleet_cands)

        hosp_cands = self.hospital_optimizer.generate_candidates(snapshot)
        candidates.extend(hosp_cands)

        with self._lock:
            for c in candidates:
                self._candidates_index[c.candidate_id] = c

        # --------------------------------------------------------------
        # 3. BUILD EXPLAINABLE RECOMMENDATIONS
        # --------------------------------------------------------------
        valid_fleet = self.fleet_optimizer.build_recommendations(fleet_cands, snapshot=snapshot)
        valid_hosp = self.hospital_optimizer.build_recommendations(hosp_cands, snapshot=snapshot)
        new_recs = valid_fleet + valid_hosp

        # --------------------------------------------------------------
        # 4. DETERMINISTIC RANKING
        # --------------------------------------------------------------
        new_recs.sort(
            key=lambda r: (
                round(r.score, 3),
                self.PRIORITY_RANKS.get(r.explanation.supporting_metrics.get("affected_entities", {}).get("priority", "MEDIUM"), 2),
                r.recommendation_id,
            ),
            reverse=True,
        )

        with self._lock:
            for r in new_recs:
                self._recommendations_index[r.recommendation_id] = r

        return new_recs

    def get_recommendation(self, rec_id: str) -> Optional[OptimizationRecommendation]:
        """Retrieve a cached recommendation by its ID."""
        with self._lock:
            return self._recommendations_index.get(rec_id)

    def get_all_recommendations(self) -> List[OptimizationRecommendation]:
        """Retrieve all currently cached recommendations."""
        with self._lock:
            return list(self._recommendations_index.values())

    def get_candidate(self, cand_id: str) -> Optional[OptimizationCandidate]:
        """Retrieve a generated candidate (valid or rejected) by its ID."""
        with self._lock:
            return self._candidates_index.get(cand_id)

    def simulate_recommendation(
        self,
        rec_id: str,
        sim_instance,
    ) -> Optional[SimulationImpact]:
        """
        Execute an isolated what-if simulation for a specific recommendation.
        Returns the impact assessment without modifying live state.
        """
        rec = self.get_recommendation(rec_id)
        if not rec:
            return None

        cand_id = rec_id.replace("REC_", "")
        cand = self.get_candidate(cand_id)
        if not cand:
            cand = OptimizationCandidate(
                candidate_id=cand_id,
                decision_type=rec.decision_type,
                priority=rec.severity,
                affected_entities=rec.candidate_action,
                target=str(rec.candidate_action.get("target_zone") or rec.candidate_action.get("recommended_hospital_id") or ""),
                expected_effect=rec.explanation.expected_benefit,
                confidence=float(rec.explanation.supporting_metrics.get("confidence", 0.90)),
                score=rec.score,
                rationale=rec.explanation.summary,
                constraints=[],
                generated_at_sim_time=self._last_snapshot.sim_time if self._last_snapshot else 0,
            )

        snapshot = self._last_snapshot or self.get_snapshot(sim_instance)
        impact = self.simulator.simulate_candidate(cand, snapshot)

        rec.simulation_impact = impact
        if rec.status in (RecommendationStatus.NEW, "ACTIVE"):
            rec.status = RecommendationStatus.REVIEWED
        return impact

    def approve_recommendation(
        self,
        rec_id: str,
        sim_instance,
        operator_id: str = "OPERATOR_DISPATCHER",
        operator_note: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Authoritatively approve and execute a recommendation through the Simulator.
        """
        rec = self.get_recommendation(rec_id)
        if not rec:
            # Check if state evaluation uncovers it
            self.evaluate_state(sim_instance)
            rec = self.get_recommendation(rec_id)

        if not rec:
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            return ExecutionResult(
                execution_id=f"EXEC_NOTFOUND_{rec_id}",
                recommendation_id=rec_id,
                decision_type="UNKNOWN",
                status=RecommendationStatus.FAILED,
                error_message=f"Recommendation '{rec_id}' not found.",
                executed_at=now_iso,
            )

        return self.executor.approve_and_execute(
            recommendation=rec,
            simulator=sim_instance,
            operator_id=operator_id,
            operator_note=operator_note,
        )

    def reject_recommendation(
        self,
        rec_id: str,
        operator_id: str = "OPERATOR_DISPATCHER",
        reason: Optional[str] = None,
    ) -> Optional[OptimizationRecommendation]:
        """Explicitly dismiss or reject an advisory recommendation."""
        rec = self.get_recommendation(rec_id)
        if not rec:
            return None

        return self.executor.reject_recommendation(
            recommendation=rec,
            operator_id=operator_id,
            reason=reason,
        )

    def evaluate_policy(
        self,
        rec_id: str,
        sim_instance,
    ) -> Optional[PolicyEvaluation]:
        """Evaluate a specific recommendation against the Adaptive Policy Engine."""
        rec = self.get_recommendation(rec_id)
        if not rec:
            return None
        snapshot = self.get_snapshot(sim_instance)
        return self.policy_engine.evaluate(rec, sim_instance, snapshot)

    def step_auto_rebalance(self, sim_instance) -> Optional[ExecutionResult]:
        """Execute one controlled step of closed-loop auto-rebalancing."""
        return self.policy_engine.step_auto_rebalance(
            simulator=sim_instance,
            executor=self.executor,
            decision_engine=self,
        )

    def rollback_execution(
        self,
        execution_id: str,
        sim_instance,
        operator_id: str = "OPERATOR_DISPATCHER",
        reason: Optional[str] = None,
    ) -> ExecutionResult:
        """Roll back a previous fleet repositioning execution."""
        return self.policy_engine.rollback_execution(
            execution_id=execution_id,
            simulator=sim_instance,
            executor=self.executor,
            operator_id=operator_id,
            reason=reason,
        )

    def get_copilot_summary(self, sim_instance) -> Dict[str, Any]:
        """
        Compute aggregate Copilot status: operational health, top priority
        recommendation, pending count, stale count, latest execution result,
        and Adaptive Policy telemetry.
        """
        # Ensure fresh state
        recs = self.evaluate_state(sim_instance)
        snapshot = self._last_snapshot

        with self._lock:
            all_recs = list(self._recommendations_index.values())

        pending = [
            r for r in all_recs
            if r.status in (RecommendationStatus.NEW, "ACTIVE", RecommendationStatus.REVIEWED)
        ]
        stale = [
            r for r in all_recs
            if r.status in (RecommendationStatus.EXPIRED, RecommendationStatus.OBSOLETE)
        ]

        executions = self.audit_store.get_executions(limit=10)
        latest_outcome = executions[0] if executions else None

        # Determine health
        if snapshot and (len(snapshot.zone_coverage.get("JAIPUR_NORTH", {}).get("available_ambulances", [])) == 0
            or any(p.get("status") == "FULL" for p in snapshot.hospital_projected_capacities.values())):
            health = "STRAINED"
        else:
            health = "NORMAL"

        top_rec = recs[0].to_dict() if recs else None

        # Compute learning safety score and drift for copilot summary
        drift_obj = self.get_drift(sim_instance)
        perf_trend = self.get_performance_trend()
        calib_obj = self.get_calibration()
        from Dispatch.optimization.learning import calculate_learning_safety_score
        safety_score = calculate_learning_safety_score(calib_obj, perf_trend, drift_obj.severity)

        return {
            "operational_health": health,
            "highest_priority_recommendation": top_rec,
            "pending_recommendations_count": len(pending),
            "stale_recommendations_count": len(stale),
            "recent_executions_count": len(executions),
            "latest_execution_outcome": latest_outcome,
            "mode": "COPILOT_ADVISORY_READY",
            "policy_mode": self.policy_engine.config.mode,
            "operating_policy_version": self.policy_engine.config.policy_version,
            "kill_switch_active": self.policy_engine.config.kill_switch_active,
            "autonomous_actions_executed": self.policy_engine.performance.autonomous_actions_executed,
            "policy_performance": self.policy_engine.performance.to_dict(),
            "drift_severity": drift_obj.severity,
            "learning_safety_score": safety_score.score,
        }

    # ------------------------------------------------------------------
    # M11 PHASE 4: OPERATIONAL LEARNING, CALIBRATION & DRIFT METHODS
    # ------------------------------------------------------------------

    def get_outcomes(self, limit: int = 100) -> List[Any]:
        """Query historical recommendation outcomes."""
        return self.outcome_store.get_outcomes(limit=limit)

    def get_calibration(self) -> Any:
        """Run calibration analyzer over historical outcomes."""
        outcomes = self.outcome_store.get_outcomes(limit=500)
        return self.calibration_analyzer.analyze(outcomes)

    def get_performance_trend(self) -> Any:
        """Calculate aggregate policy performance trend metrics."""
        from Dispatch.optimization.learning import PolicyPerformanceTrend
        perf = self.policy_engine.performance
        outcomes = self.outcome_store.get_outcomes(limit=500)

        # Count stale / expired
        with self._lock:
            stale_c = sum(1 for r in self._recommendations_index.values() if r.status == RecommendationStatus.OBSOLETE)
            expired_c = sum(1 for r in self._recommendations_index.values() if r.status == RecommendationStatus.EXPIRED)

        rb_success_rate = 1.0
        if perf.rollback_attempts > 0:
            rb_success_rate = round(perf.rollback_successes / perf.rollback_attempts, 4)

        pred_err = round(perf.avg_actual_benefit - perf.avg_predicted_benefit, 4)

        return PolicyPerformanceTrend(
            autonomous_executions=perf.autonomous_actions_executed,
            operator_approved_executions=perf.operator_approvals,
            denied_actions=perf.blocked_actions,
            stale_recommendations=stale_c,
            expired_recommendations=expired_c,
            successful_actions=perf.successful_actions,
            neutral_actions=perf.neutral_actions,
            harmful_actions=perf.harmful_actions,
            rollback_attempts=perf.rollback_attempts,
            rollback_success_rate=rb_success_rate,
            average_benefit=perf.avg_actual_benefit,
            average_predicted_benefit=perf.avg_predicted_benefit,
            prediction_error=pred_err,
            average_decision_latency=8.5,
            average_execution_latency=4.2,
        )

    def get_drift(self, sim_instance) -> Any:
        """Detect operational drift against baseline EMS network metrics."""
        snapshot = self.get_snapshot(sim_instance)
        outcomes = self.outcome_store.get_outcomes(limit=50)

        # Average coverage
        cov_scores = [z.get("coverage_score", 0.85) for z in snapshot.zone_coverage.values()]
        avg_cov = sum(cov_scores) / max(1, len(cov_scores))

        # Hospital saturation pct
        hosp_full = sum(1 for h in snapshot.hospital_projected_capacities.values() if h.get("status") == "FULL")
        hosp_sat_pct = (hosp_full / max(1, len(snapshot.hospital_projected_capacities))) * 100.0

        # Autonomous success rate
        succ_rate = 0.95
        total_auto = self.policy_engine.performance.autonomous_actions_executed
        if total_auto > 0:
            succ_rate = self.policy_engine.performance.successful_actions / total_auto

        # Stale rate
        with self._lock:
            total_recs = max(1, len(self._recommendations_index))
            stale_recs = sum(1 for r in self._recommendations_index.values() if r.status in (RecommendationStatus.OBSOLETE, RecommendationStatus.EXPIRED))
        stale_pct = (stale_recs / total_recs) * 100.0

        # Mean benefit ratio
        ratios = [o.benefit_realization_ratio for o in outcomes if o.benefit_realization_ratio > 0]
        mean_ratio = (sum(ratios) / len(ratios)) if ratios else 0.90

        current_metrics = {
            "avg_eta_minutes": 6.5,
            "avg_coverage_score": round(avg_cov, 3),
            "hospital_saturation_pct": round(hosp_sat_pct, 2),
            "autonomous_success_rate": round(succ_rate, 3),
            "benefit_realization_ratio": round(mean_ratio, 3),
            "unresolved_casualty_pct": 2.0,
            "recommendation_volume_per_10m": float(len(outcomes)),
            "stale_rate_pct": round(stale_pct, 2),
        }

        return self.drift_detector.detect_drift(current_metrics)

    def get_learning_recommendations(self, sim_instance) -> List[Any]:
        """Generate or retrieve pending adaptive policy recommendations."""
        calib = self.get_calibration()
        drift_obj = self.get_drift(sim_instance)
        perf = self.get_performance_trend()
        return self.adaptation_advisor.generate_recommendations(
            calibration=calib,
            drift=drift_obj,
            performance=perf,
            current_config=self.policy_engine.config,
        )

    def get_learning_recommendation(self, rec_id: str) -> Optional[Any]:
        """Retrieve single adaptive recommendation by ID."""
        return self.adaptation_advisor.get_recommendation(rec_id)

    def approve_learning_recommendation(
        self,
        recommendation_id: str,
        operator_id: str = "OPERATOR_DISPATCHER",
    ) -> Tuple[Any, Any]:
        """Approve adaptive recommendation and update policy version."""
        new_cfg, rec = self.adaptation_advisor.approve_recommendation(
            recommendation_id=recommendation_id,
            operator_id=operator_id,
            current_config=self.policy_engine.config,
            version_store=self.version_store,
        )
        self.policy_engine.config = new_cfg
        return new_cfg, rec

    def reject_learning_recommendation(
        self,
        recommendation_id: str,
        operator_id: str = "OPERATOR_DISPATCHER",
        reason: Optional[str] = None,
    ) -> Any:
        """Reject adaptive recommendation."""
        return self.adaptation_advisor.reject_recommendation(
            recommendation_id=recommendation_id,
            operator_id=operator_id,
            reason=reason,
        )

    def compare_policies(
        self,
        policy_a: Optional[Any] = None,
        policy_b: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Perform offline A/B policy comparison over historical outcomes."""
        from Dispatch.optimization.adaptation import PolicyEvaluatorAB
        from Dispatch.optimization.policy import PolicyConfig
        cfg_a = policy_a or self.policy_engine.config
        cfg_b = policy_b or PolicyConfig(
            policy_version="candidate_b",
            min_confidence_reposition=0.97,
        )
        outcomes = self.outcome_store.get_outcomes(limit=200)
        return PolicyEvaluatorAB.compare(cfg_a, cfg_b, outcomes)

    def rollback_policy(
        self,
        target_version: str,
        operator_id: str = "OPERATOR_DISPATCHER",
        reason: Optional[str] = None,
    ) -> Any:
        """Rollback active policy to previous version creating new immutable record."""
        new_cfg = self.version_store.rollback_to_version(
            target_version_id=target_version,
            operator_id=operator_id,
            reason=reason,
        )
        self.policy_engine.config = new_cfg
        return new_cfg

    def get_policy_history(self) -> List[Dict[str, Any]]:
        """List all policy versions in chronological order."""
        return self.version_store.list_versions()

    def get_learning_report(self, sim_instance) -> Any:
        """Synthesize end-to-end LearningReport with safety score and deterministic hash."""
        from Dispatch.optimization.learning import (
            LearningReport,
            calculate_learning_safety_score,
            generate_deterministic_hash,
        )
        calib = self.get_calibration()
        drift_obj = self.get_drift(sim_instance)
        perf = self.get_performance_trend()
        recs = self.get_learning_recommendations(sim_instance)
        safety = calculate_learning_safety_score(calib, perf, drift_obj.severity)

        det_dict = {
            "safety_score": safety.score,
            "calibration_error": calib.mean_calibration_error,
            "drift_severity": drift_obj.severity,
            "autonomous_executions": perf.autonomous_executions,
            "successful_actions": perf.successful_actions,
            "harmful_actions": perf.harmful_actions,
            "recommendations_count": len(recs),
        }
        det_hash = generate_deterministic_hash(det_dict)

        return LearningReport(
            report_id=f"REPORT_{det_hash[:8].upper()}",
            created_at=datetime.now(timezone.utc).isoformat(),
            safety_score=safety,
            calibration=calib,
            drift=drift_obj.to_dict(),
            performance=perf,
            recommendations=[r.to_dict() for r in recs],
            deterministic_hash=det_hash,
        )

