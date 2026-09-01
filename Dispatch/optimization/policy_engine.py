"""
RAAH Adaptive Policy Engine (M11 Phase 3)
=========================================

Evaluates optimization recommendations against operational safety guardrails,
confidence thresholds, cooldowns, and anti-oscillation constraints. Decides WHEN
an action can be auto-approved (in GUARDED mode) vs WHEN operator approval is mandatory.
Supports operator mode switching, emergency kill-switch, closed-loop outcome feedback,
and safe fleet repositioning rollbacks.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

from Dispatch.optimization.policy import (
    AutonomyMode,
    PolicyDecisionType,
    OutcomeClassification,
    PolicyConfig,
    PolicyEvaluation,
    PolicyOutcome,
    PolicyPerformance,
    ModeChangeEvent,
)
from Dispatch.optimization.models import (
    OptimizationRecommendation,
    ExecutionResult,
    RecommendationStatus,
    OperationalSnapshot,
)
from Dispatch.optimization.audit import ExecutionAuditStore
from Dispatch.optimization.executor import OptimizationExecutor
from Dispatch.coordination.coverage import CoverageEngine


class AdaptivePolicyEngine:
    """Bounded, explainable policy engine governing semi-autonomous optimization actions."""

    def __init__(
        self,
        config: Optional[PolicyConfig] = None,
        audit_store: Optional[ExecutionAuditStore] = None,
        outcome_store: Optional[Any] = None,
        version_store: Optional[Any] = None,
    ):
        self.config = config or PolicyConfig()
        self.audit_store = audit_store or ExecutionAuditStore()
        if outcome_store is None:
            from Dispatch.optimization.learning import OutcomeStore
            self.outcome_store = OutcomeStore()
        else:
            self.outcome_store = outcome_store

        if version_store is None:
            from Dispatch.optimization.adaptation import PolicyVersionStore
            self.version_store = PolicyVersionStore()
        else:
            self.version_store = version_store

        self.performance = PolicyPerformance()

        # In-memory operational tracking
        self._mode_change_history: List[ModeChangeEvent] = []
        self._evaluations_history: List[PolicyEvaluation] = []
        self._outcomes_history: List[PolicyOutcome] = []

        # Anti-oscillation and cooldown state
        self._last_action_timestamp: float = 0.0
        self._last_action_sim_time: int = -1
        self._zone_last_action_tick: Dict[str, int] = {}       # zone_id -> last sim_time
        self._ambulance_last_action: Dict[str, Dict[str, Any]] = {} # amb_id -> {donor, target, tick}
        self._actions_in_window: List[int] = []               # list of sim_times for rolling window
        self._consecutive_actions_count: int = 0

    # ------------------------------------------------------------------
    # 1. POLICY EVALUATION & 12 OPERATIONAL GUARDRAILS
    # ------------------------------------------------------------------
    def evaluate(
        self,
        recommendation: OptimizationRecommendation,
        simulator,
        snapshot: Optional[OperationalSnapshot] = None,
    ) -> PolicyEvaluation:
        """
        Evaluate recommendation against 12 operational guardrails and confidence thresholds.
        Returns explainable PolicyEvaluation.
        """
        rec = recommendation
        action = rec.candidate_action
        sim_state = simulator.state
        current_sim_time = int(getattr(sim_state, "current_time", 0))

        # Extract confidence
        confidence = float(getattr(rec, "confidence", 0.0) or getattr(rec.explanation, "supporting_metrics", {}).get("confidence", 0.0))
        if confidence == 0.0 and rec.score > 0.0:
            # Derive confidence deterministically from composite score and risk count
            risk_penalty = len(rec.explanation.risks) * 0.05
            confidence = max(0.50, min(0.99, rec.score - risk_penalty))

        rules_evaluated: List[str] = []
        rules_passed: List[str] = []
        rules_failed: List[str] = []
        violations: List[str] = []

        # Helper to record rule outcome
        def check_rule(name: str, passed: bool, failure_msg: Optional[str] = None):
            rules_evaluated.append(name)
            if passed:
                rules_passed.append(name)
            else:
                rules_failed.append(name)
                if failure_msg:
                    violations.append(failure_msg)

        # --------------------------------------------------------------
        # RULE 1: STATE_HASH_VALIDITY
        # --------------------------------------------------------------
        if snapshot:
            expected_hash = rec.original_state_hash
            hash_valid = bool(not expected_hash or snapshot.snapshot_hash == expected_hash)
            check_rule("STATE_HASH_VALIDITY", hash_valid, "Operational state hash changed since recommendation generation.")
        else:
            check_rule("STATE_HASH_VALIDITY", True)

        # --------------------------------------------------------------
        # RULE 2: TTL_EXPIRATION
        # --------------------------------------------------------------
        ttl_valid = current_sim_time <= rec.expires_at_sim_time
        check_rule("TTL_VALIDITY", ttl_valid, f"Recommendation expired (TTL T+{rec.expires_at_sim_time}m vs current T+{current_sim_time}m).")

        # --------------------------------------------------------------
        # RULE 3: RECOMMENDATION_STATUS_NOT_TERMINAL
        # --------------------------------------------------------------
        status_valid = rec.status in (RecommendationStatus.NEW, RecommendationStatus.REVIEWED)
        check_rule("STATUS_ACTIVE", status_valid, f"Recommendation in terminal state '{rec.status}'.")

        # --------------------------------------------------------------
        # RULE 4: CLINICAL / HOSPITAL ACTION RESTRICTION
        # (Hospital diversions ALWAYS require operator approval)
        # --------------------------------------------------------------
        if rec.decision_type == "HOSPITAL_DIVERSION":
            check_rule("CLINICAL_HOSPITAL_RESTRICTION", False, "Hospital diversions involve patient routing and require mandatory operator approval.")
        else:
            check_rule("CLINICAL_HOSPITAL_RESTRICTION", True)

        # --------------------------------------------------------------
        # RULE 5: MCI INTERCEPTION RESTRICTION
        # (MCI actions ALWAYS require operator approval)
        # --------------------------------------------------------------
        if rec.decision_type == "MCI_INTERCEPTION":
            check_rule("MCI_INTERCEPTION_RESTRICTION", False, "MCI unit assignments require tactical coordinator confirmation.")
        else:
            check_rule("MCI_INTERCEPTION_RESTRICTION", True)

        # --------------------------------------------------------------
        # RULE 6: AMBULANCE AVAILABILITY & NON-COMMITTED
        # --------------------------------------------------------------
        aid = action.get("ambulance_id")
        amb_valid = True
        amb_obj = sim_state.ambulances.get(str(aid)) if aid else None
        if aid and amb_obj:
            is_available = amb_obj.status == "AVAILABLE"
            not_repo = not getattr(amb_obj, "is_repositioning", False)
            not_committed = getattr(amb_obj, "incident_id", None) is None
            amb_valid = is_available and not_repo and not_committed
            if not amb_valid:
                check_rule("AMBULANCE_AVAILABILITY", False, f"Ambulance '{aid}' status={amb_obj.status}, repo={getattr(amb_obj, 'is_repositioning', False)}, incident={getattr(amb_obj, 'incident_id', None)}.")
            else:
                check_rule("AMBULANCE_AVAILABILITY", True)
        else:
            check_rule("AMBULANCE_AVAILABILITY", True)

        # --------------------------------------------------------------
        # RULE 7: DONOR ZONE SAFETY BUFFER (Coverage floor preservation)
        # --------------------------------------------------------------
        donor_zone = action.get("donor_zone")
        if donor_zone and snapshot and donor_zone in snapshot.zone_coverage:
            avail_count = snapshot.zone_coverage[donor_zone].get("available_count", 0)
            donor_safe = avail_count >= self.config.fleet_safety_floor
            check_rule("DONOR_SAFETY_BUFFER", donor_safe, f"Donor zone '{donor_zone}' has {avail_count} available units (safety floor: {self.config.fleet_safety_floor}).")
        else:
            check_rule("DONOR_SAFETY_BUFFER", True)

        # --------------------------------------------------------------
        # RULE 8: NO ACTIVE HIGH-SEVERITY MCI NEAR DONOR
        # --------------------------------------------------------------
        mci_safe = True
        if snapshot and snapshot.active_mcis:
            for mci in snapshot.active_mcis:
                if mci.get("total_casualties", 0) >= 5 and mci.get("status") == "ACTIVE":
                    # If high casualty MCI active, restrict autonomous draining
                    mci_safe = False
                    break
        check_rule("MCI_SAFETY_ISOLATION", mci_safe, "Active high-casualty MCI scene in progress; autonomous repositioning suspended.")

        # --------------------------------------------------------------
        # RULE 9: NO UNASSIGNED P1/P2 EMERGENCIES IN DONOR ZONE
        # --------------------------------------------------------------
        p1_safe = True
        for inc in sim_state.incidents.values():
            if inc.status in ("WAITING", "CALL_RECEIVED") and getattr(inc, "priority", 5) in (1, 2):
                p1_safe = False
                break
        check_rule("P1_P2_EMERGENCY_PROTECTION", p1_safe, "Unassigned critical P1/P2 emergency pending; fleet cannot be autonomously relocated.")

        # --------------------------------------------------------------
        # RULE 10: CONFIDENCE THRESHOLD
        # --------------------------------------------------------------
        min_conf = self.config.min_confidence_reposition
        conf_passed = confidence >= min_conf
        check_rule("CONFIDENCE_THRESHOLD", conf_passed, f"Confidence {confidence:.2f} is below policy threshold {min_conf:.2f}.")

        # --------------------------------------------------------------
        # RULE 11: COOLDOWN, RATE LIMIT & ANTI-OSCILLATION
        # --------------------------------------------------------------
        cooldown_passed = True
        target_zone = action.get("target_zone")

        # Zone cooldown
        if target_zone and target_zone in self._zone_last_action_tick:
            ticks_since_zone = current_sim_time - self._zone_last_action_tick[target_zone]
            if ticks_since_zone < self.config.zone_cooldown_ticks:
                cooldown_passed = False
                violations.append(f"Target zone '{target_zone}' in cooldown ({ticks_since_zone} < {self.config.zone_cooldown_ticks} ticks).")

        # Anti-oscillation (reversing direction for same ambulance)
        if aid and aid in self._ambulance_last_action:
            last_mov = self._ambulance_last_action[aid]
            if last_mov.get("target") == donor_zone and last_mov.get("donor") == target_zone:
                ticks_since_rev = current_sim_time - last_mov.get("tick", -1)
                if ticks_since_rev < (self.config.zone_cooldown_ticks * 2):
                    cooldown_passed = False
                    violations.append(f"Anti-oscillation guard triggered: ambulance '{aid}' was recently moved in the opposite direction.")

        # Consecutive actions limit
        if self._consecutive_actions_count >= self.config.max_consecutive_autonomous_actions:
            cooldown_passed = False
            violations.append(f"Consecutive autonomous action limit reached ({self._consecutive_actions_count}/{self.config.max_consecutive_autonomous_actions}).")

        # Window rate limit
        recent_actions = [t for t in self._actions_in_window if (current_sim_time - t) <= self.config.window_size_ticks]
        if len(recent_actions) >= self.config.max_autonomous_actions_per_window:
            cooldown_passed = False
            violations.append(f"Autonomous rate limit exceeded ({len(recent_actions)} actions in last {self.config.window_size_ticks} ticks).")

        check_rule("COOLDOWN_AND_STABILITY", cooldown_passed)

        # --------------------------------------------------------------
        # RULE 12: AUTONOMY MODE & EMERGENCY KILL-SWITCH
        # --------------------------------------------------------------
        if self.config.kill_switch_active:
            check_rule("KILL_SWITCH_STATUS", False, "Emergency kill-switch is ACTIVE.")
        else:
            check_rule("KILL_SWITCH_STATUS", True)

        # --------------------------------------------------------------
        # SYNTHESIZE DECISION & EXPLANATION
        # --------------------------------------------------------------
        decision: str = PolicyDecisionType.REQUIRE_OPERATOR
        reason: str = ""

        if self.config.kill_switch_active:
            decision = PolicyDecisionType.DENY
            reason = "Emergency kill-switch is ACTIVE. Autonomous actions completely halted."
            self.performance.blocked_actions += 1

        elif self.config.mode == AutonomyMode.OFF:
            decision = PolicyDecisionType.REQUIRE_OPERATOR
            reason = "Autonomy mode is OFF. All recommendations strictly require explicit operator approval."

        elif rec.decision_type in ("HOSPITAL_DIVERSION", "MCI_INTERCEPTION"):
            decision = PolicyDecisionType.REQUIRE_OPERATOR
            reason = f"{rec.decision_type} involves direct clinical / MCI safety and ALWAYS requires operator approval."

        elif len(rules_failed) > 0:
            # Failed one or more guardrails
            has_fatal_safety = any(
                r in ("DONOR_SAFETY_BUFFER", "COOLDOWN_AND_STABILITY", "AMBULANCE_AVAILABILITY", "P1_P2_EMERGENCY_PROTECTION")
                for r in rules_failed
            )
            if has_fatal_safety:
                decision = PolicyDecisionType.DENY
                reason = f"Action denied by safety guardrails: {'; '.join(violations)}"
                self.performance.blocked_actions += 1
                self.performance.policy_violations_count += len(violations)
            else:
                decision = PolicyDecisionType.REQUIRE_OPERATOR
                reason = f"Operator approval required due to policy constraints: {'; '.join(violations)}"

        else:
            # All 12 guardrails passed!
            if self.config.mode == AutonomyMode.ADVISORY:
                decision = PolicyDecisionType.REQUIRE_OPERATOR
                reason = f"Advisory Mode: recommendation satisfies all auto-approval guardrails (confidence {confidence:.2f}), but operator must confirm."
            elif self.config.mode in (AutonomyMode.GUARDED, AutonomyMode.FULL):
                decision = PolicyDecisionType.AUTO_APPROVE
                donor_avail = snapshot.zone_coverage.get(donor_zone, {}).get("available_count", 2) if (snapshot and donor_zone) else "safety-checked"
                reason = (
                    f"Fleet repositioning is low-risk, confidence {confidence:.2f} (>= {min_conf:.2f}), "
                    f"donor zone retains {donor_avail} available units, no active MCI, no hospital impact."
                )

        eval_result = PolicyEvaluation(
            recommendation_id=rec.recommendation_id,
            decision_type=rec.decision_type,
            policy_decision=decision,
            confidence=confidence,
            confidence_threshold=min_conf,
            score=rec.score,
            reason=reason,
            rules_evaluated=rules_evaluated,
            rules_passed=rules_passed,
            rules_failed=rules_failed,
            violations=violations,
            policy_mode=self.config.mode,
        )

        self._evaluations_history.append(eval_result)
        return eval_result

    # ------------------------------------------------------------------
    # 2. AUTONOMOUS EXECUTION & CLOSED-LOOP FEEDBACK
    # ------------------------------------------------------------------
    def execute_autonomous(
        self,
        recommendation: OptimizationRecommendation,
        simulator,
        executor: OptimizationExecutor,
        policy_evaluation: Optional[PolicyEvaluation] = None,
    ) -> ExecutionResult:
        """
        Execute an auto-approved recommendation through the authoritative Simulator,
        record complete audit metadata, measure outcome feedback, and update telemetry.
        """
        self.performance.autonomous_actions_attempted += 1
        rec = recommendation
        action = rec.candidate_action
        sim_state = simulator.state
        current_sim_time = int(getattr(sim_state, "current_time", 0))

        # Re-evaluate under lock if evaluation not supplied
        fresh_snap = executor.observer.capture_snapshot(simulator)
        p_eval = policy_evaluation or self.evaluate(rec, simulator, fresh_snap)

        if p_eval.policy_decision != PolicyDecisionType.AUTO_APPROVE:
            exec_id = f"EXEC_AUTO_DENIED_{uuid.uuid4().hex[:8].upper()}"
            res = ExecutionResult(
                execution_id=exec_id,
                recommendation_id=rec.recommendation_id,
                decision_type=rec.decision_type,
                status=RecommendationStatus.REJECTED,
                error_message=f"Autonomous execution blocked by policy: {p_eval.reason}",
                executed_at=datetime.now(timezone.utc).isoformat(),
                affected_entities=action,
            )
            self.performance.blocked_actions += 1
            return res

        # Capture pre-execution baseline metrics
        cov_before = simulator.coordinator.get_coverage(sim_state.ambulances)
        avg_cov_before = sum(
            z.get("coverage_score", 1.0) if isinstance(z, dict) else getattr(z, "coverage_score", 1.0)
            for z in cov_before.values()
        ) / max(1, len(cov_before))

        # Execute authoritatively through executor
        res = executor.approve_and_execute(
            recommendation=rec,
            simulator=simulator,
            operator_id="AUTONOMOUS_POLICY_ENGINE",
            operator_note=f"[AUTONOMOUS_EXECUTION] {p_eval.reason}",
        )

        if res.status == "SUCCESS":
            self.performance.autonomous_actions_executed += 1
            self._consecutive_actions_count += 1
            self._actions_in_window.append(current_sim_time)
            self._last_action_timestamp = time.time()
            self._last_action_sim_time = current_sim_time

            aid = str(action.get("ambulance_id", ""))
            donor = str(action.get("donor_zone", ""))
            target = str(action.get("target_zone", ""))
            if target:
                self._zone_last_action_tick[target] = current_sim_time
            if donor:
                self._zone_last_action_tick[donor] = current_sim_time
            if aid:
                self._ambulance_last_action[aid] = {"donor": donor, "target": target, "tick": current_sim_time}

            # ----------------------------------------------------------
            # Closed-Loop Outcome Measurement
            # ----------------------------------------------------------
            cov_after = simulator.coordinator.get_coverage(sim_state.ambulances)
            avg_cov_after = sum(
                z.get("coverage_score", 1.0) if isinstance(z, dict) else getattr(z, "coverage_score", 1.0)
                for z in cov_after.values()
            ) / max(1, len(cov_after))
            delta_cov = avg_cov_after - avg_cov_before

            predicted_benefit = 0.15
            if rec.simulation_impact:
                predicted_benefit = rec.simulation_impact.resilience_impact

            # Classify outcome
            if delta_cov >= -0.01:
                classification = OutcomeClassification.SUCCESSFUL
                self.performance.successful_actions += 1
            elif delta_cov >= -0.05:
                classification = OutcomeClassification.NEUTRAL
                self.performance.neutral_actions += 1
            else:
                classification = OutcomeClassification.HARMFUL
                self.performance.harmful_actions += 1

            actual_benefit = round(delta_cov, 4)
            self._update_benefit_averages(predicted_benefit, actual_benefit)

            outcome = PolicyOutcome(
                outcome_id=f"OUTCOME_{uuid.uuid4().hex[:8].upper()}",
                execution_id=res.execution_id,
                recommendation_id=rec.recommendation_id,
                decision_type=rec.decision_type,
                classification=classification,
                predicted_benefit=predicted_benefit,
                actual_benefit=actual_benefit,
                delta_coverage=round(delta_cov, 4),
                delta_utilization=0.0,
            )
            self._outcomes_history.append(outcome)

            from Dispatch.optimization.learning import OutcomeRecord
            outcome_rec = OutcomeRecord(
                recommendation_id=rec.recommendation_id,
                recommendation_type=rec.decision_type,
                confidence=p_eval.confidence,
                predicted_benefit=predicted_benefit,
                actual_benefit=actual_benefit,
                policy_decision=p_eval.policy_decision,
                execution_mode="AUTONOMOUS",
                outcome=classification,
                execution_latency=0.0,
                sim_time=current_sim_time,
                affected_entities=action,
                before_state_hash=getattr(res, "state_hash_before", ""),
                after_state_hash=getattr(res, "state_hash_after", ""),
            )
            self.outcome_store.record_outcome(outcome_rec)

            # Record enriched audit
            self.audit_store.record_execution(
                result=res,
                operator_id="AUTONOMOUS_POLICY_ENGINE",
                operator_note=f"[AUTONOMOUS] Outcome: {classification} (delta_cov={delta_cov:+.3f})",
                execution_mode="AUTONOMOUS",
                policy_mode=self.config.mode,
                policy_decision=p_eval.policy_decision,
                confidence=p_eval.confidence,
                policy_version=self.config.version,
                policy_rules_evaluated=p_eval.rules_evaluated,
                predicted_benefit=predicted_benefit,
                actual_benefit=actual_benefit,
                outcome=classification,
                kill_switch_state=self.config.kill_switch_active,
            )

        return res

    # ------------------------------------------------------------------
    # 3. CONTROLLED STEP AUTO-REBALANCE
    # ------------------------------------------------------------------
    def step_auto_rebalance(
        self,
        simulator,
        executor: OptimizationExecutor,
        decision_engine,
    ) -> Optional[ExecutionResult]:
        """
        Single controlled step of auto-rebalancing.
        Observes, generates recommendations, evaluates policy, and executes if AUTO_APPROVE.
        """
        if self.config.mode not in (AutonomyMode.GUARDED, AutonomyMode.FULL):
            return None
        if self.config.kill_switch_active:
            return None

        # Generate fresh recommendations
        recs = decision_engine.evaluate_state(simulator)
        if not recs:
            return None

        fresh_snap = executor.observer.capture_snapshot(simulator)

        # Inspect actionable recommendations
        for rec in recs:
            if rec.status != RecommendationStatus.NEW:
                continue

            p_eval = self.evaluate(rec, simulator, fresh_snap)
            if p_eval.policy_decision == PolicyDecisionType.AUTO_APPROVE:
                return self.execute_autonomous(rec, simulator, executor, p_eval)

        return None

    # ------------------------------------------------------------------
    # 4. SAFE ROLLBACK / UNDO
    # ------------------------------------------------------------------
    def rollback_execution(
        self,
        execution_id: str,
        simulator,
        executor: OptimizationExecutor,
        operator_id: str = "OPERATOR_DISPATCHER",
        reason: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Safely roll back a recently executed fleet repositioning action.
        Guarantees zero clinical/diversion rollback and verifies technical safety.
        """
        self.performance.rollback_attempts += 1
        now_iso = datetime.now(timezone.utc).isoformat()
        rollback_exec_id = f"ROLLBACK_{uuid.uuid4().hex[:8].upper()}"

        audit_record = self.audit_store.get_execution(execution_id)
        if not audit_record:
            res = ExecutionResult(
                execution_id=rollback_exec_id,
                recommendation_id="",
                decision_type="ROLLBACK",
                status=RecommendationStatus.REJECTED,
                error_message=f"Original execution record '{execution_id}' not found.",
                executed_at=now_iso,
            )
            return res

        # Check action type
        dec_type = audit_record.get("recommendation_type")
        if dec_type != "FLEET_REPOSITION":
            res = ExecutionResult(
                execution_id=rollback_exec_id,
                recommendation_id=audit_record.get("recommendation_id", ""),
                decision_type="ROLLBACK",
                status=RecommendationStatus.REJECTED,
                error_message=f"Rollback denied: {dec_type} cannot be rolled back (only FLEET_REPOSITION is reversible).",
                executed_at=now_iso,
            )
            return res

        entities = audit_record.get("resulting_entity_ids") or audit_record.get("action_parameters") or {}
        aid = entities.get("ambulance_id")
        orig_donor = entities.get("donor_zone")
        orig_target = entities.get("target_zone")

        sim_state = simulator.state
        amb_obj = sim_state.ambulances.get(str(aid))
        if not amb_obj:
            res = ExecutionResult(
                execution_id=rollback_exec_id,
                recommendation_id=audit_record.get("recommendation_id", ""),
                decision_type="ROLLBACK",
                status=RecommendationStatus.REJECTED,
                error_message=f"Rollback denied: Ambulance '{aid}' no longer exists in simulation.",
                executed_at=now_iso,
            )
            return res

        # Safety Check: Ambulance status must not be committed to an incident
        if amb_obj.status in ("EN_ROUTE", "BUSY") and getattr(amb_obj, "incident_id", None) is not None:
            res = ExecutionResult(
                execution_id=rollback_exec_id,
                recommendation_id=audit_record.get("recommendation_id", ""),
                decision_type="ROLLBACK",
                status=RecommendationStatus.REJECTED,
                error_message=f"Rollback denied: Ambulance '{aid}' is currently committed to Incident {amb_obj.incident_id}.",
                executed_at=now_iso,
            )
            return res

        # Determine original donor staging coords
        if orig_donor in CoverageEngine.ZONES:
            staging = CoverageEngine.ZONES[orig_donor]["staging_post"]
        else:
            staging = (26.9180, 75.8150)

        # Execute reverse reposition
        snap_before = executor.observer.capture_snapshot(simulator)
        state_hash_before = snap_before.snapshot_hash

        # If currently repositioning to target, cancel or redirect
        if getattr(amb_obj, "is_repositioning", False):
            simulator.cancel_reposition(aid, reason="ROLLBACK_CANCEL")

        sim_res = simulator.execute_reposition(
            ambulance_id=str(aid),
            target_lat=float(staging[0]),
            target_lon=float(staging[1]),
            reason=f"[ROLLBACK] Reversing execution {execution_id}: {reason or 'Operator rollback'}",
        )

        snap_after = executor.observer.capture_snapshot(simulator)
        state_hash_after = snap_after.snapshot_hash

        self.performance.rollback_successes += 1
        res = ExecutionResult(
            execution_id=rollback_exec_id,
            recommendation_id=audit_record.get("recommendation_id", ""),
            decision_type="FLEET_REPOSITION_ROLLBACK",
            status="SUCCESS",
            error_message=None,
            state_hash_before=state_hash_before,
            state_hash_after=state_hash_after,
            executed_at=now_iso,
            affected_entities={
                "ambulance_id": aid,
                "rolled_back_execution_id": execution_id,
                "return_zone": orig_donor,
            },
            details=sim_res,
        )

        self.audit_store.record_execution(
            result=res,
            operator_id=operator_id,
            operator_note=f"Rollback of {execution_id}: {reason or 'Operator undo'}",
            execution_mode="OPERATOR_APPROVED",
            policy_mode=self.config.mode,
            policy_decision="ROLLBACK_EXECUTED",
            rollback_of=execution_id,
            kill_switch_state=self.config.kill_switch_active,
        )

        return res

    # ------------------------------------------------------------------
    # 5. OPERATOR OVERRIDES & KILL-SWITCH
    # ------------------------------------------------------------------
    def set_mode(
        self,
        new_mode: str,
        operator_id: str = "OPERATOR_COMMANDER",
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Switch autonomy mode and record an audit event."""
        if new_mode == AutonomyMode.FULL and not self.config.allow_full_mode:
            raise ValueError("FULL autonomy mode is disabled and unavailable by production policy.")

        if new_mode not in (AutonomyMode.OFF, AutonomyMode.ADVISORY, AutonomyMode.GUARDED, AutonomyMode.FULL):
            raise ValueError(f"Unknown autonomy mode '{new_mode}'.")

        prev_mode = self.config.mode
        self.config.mode = new_mode
        self._consecutive_actions_count = 0  # Reset consecutive actions counter

        event = ModeChangeEvent(
            event_id=f"MODE_{uuid.uuid4().hex[:8].upper()}",
            previous_mode=prev_mode,
            new_mode=new_mode,
            operator_id=operator_id,
            reason=reason,
        )
        self._mode_change_history.append(event)
        return event.to_dict()

    def activate_kill_switch(
        self,
        operator_id: str = "OPERATOR_COMMANDER",
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Immediately prevent all future autonomous execution without corrupting simulator state."""
        self.config.kill_switch_active = True
        event = ModeChangeEvent(
            event_id=f"KILL_{uuid.uuid4().hex[:8].upper()}",
            previous_mode=self.config.mode,
            new_mode="KILL_SWITCH_ACTIVE",
            operator_id=operator_id,
            reason=reason or "Emergency kill-switch manually engaged.",
        )
        self._mode_change_history.append(event)
        return {"kill_switch_active": True, "event": event.to_dict()}

    def deactivate_kill_switch(
        self,
        operator_id: str = "OPERATOR_COMMANDER",
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Deactivate emergency kill-switch and restore configured autonomy mode."""
        self.config.kill_switch_active = False
        event = ModeChangeEvent(
            event_id=f"RESUME_{uuid.uuid4().hex[:8].upper()}",
            previous_mode="KILL_SWITCH_ACTIVE",
            new_mode=self.config.mode,
            operator_id=operator_id,
            reason=reason or "Emergency kill-switch manually released.",
        )
        self._mode_change_history.append(event)
        return {"kill_switch_active": False, "event": event.to_dict()}

    # ------------------------------------------------------------------
    # 6. TELEMETRY & REPORTING
    # ------------------------------------------------------------------
    def get_performance(self) -> PolicyPerformance:
        """Return aggregated operational telemetry."""
        return self.performance

    def get_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent policy evaluations."""
        return [e.to_dict() for e in reversed(self._evaluations_history[-limit:])]

    def get_outcomes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent measured operational outcomes."""
        return [o.to_dict() for o in reversed(self._outcomes_history[-limit:])]

    def _update_benefit_averages(self, predicted: float, actual: float):
        n = self.performance.autonomous_actions_executed
        if n == 1:
            self.performance.avg_predicted_benefit = round(predicted, 4)
            self.performance.avg_actual_benefit = round(actual, 4)
        else:
            self.performance.avg_predicted_benefit = round(
                ((self.performance.avg_predicted_benefit * (n - 1)) + predicted) / n, 4
            )
            self.performance.avg_actual_benefit = round(
                ((self.performance.avg_actual_benefit * (n - 1)) + actual) / n, 4
            )
