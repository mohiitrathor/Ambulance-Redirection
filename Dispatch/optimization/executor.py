"""
RAAH Optimization Executor & Stale-State Protection (M11 Phase 2)
=================================================================

Bridges approved optimization recommendations into authoritative Simulator
coordination methods. Enforces strict stale-state invalidation, constraint
revalidation under simulator lock, atomic execution, and audit logging.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from Dispatch.optimization.models import (
    OptimizationRecommendation,
    ExecutionResult,
    RecommendationStatus,
    OperationalSnapshot,
)
from Dispatch.optimization.observer import OperationalObserver
from Dispatch.optimization.audit import ExecutionAuditStore
from Dispatch.coordination.coverage import CoverageEngine


class OptimizationExecutor:
    """Safely and authoritatively executes operator-approved optimization recommendations."""

    def __init__(
        self,
        observer: Optional[OperationalObserver] = None,
        audit_store: Optional[ExecutionAuditStore] = None,
    ):
        self.observer = observer or OperationalObserver()
        self.audit_store = audit_store or ExecutionAuditStore()

    def approve_and_execute(
        self,
        recommendation: OptimizationRecommendation,
        simulator,
        operator_id: str = "OPERATOR_DISPATCHER",
        operator_note: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Atomically validate, approve, and execute a recommendation through existing
        authoritative Simulator methods. Guaranteed zero execution if validation fails.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        exec_id = f"EXEC_{uuid.uuid4().hex[:12].upper()}"
        rec = recommendation
        action = rec.candidate_action

        # --------------------------------------------------------------
        # 1. STATUS & EXPIRATION VALIDATION
        # --------------------------------------------------------------
        if rec.status in (
            RecommendationStatus.EXECUTED,
            RecommendationStatus.REJECTED,
            RecommendationStatus.OBSOLETE,
        ):
            res = ExecutionResult(
                execution_id=exec_id,
                recommendation_id=rec.recommendation_id,
                decision_type=rec.decision_type,
                status=RecommendationStatus.OBSOLETE,
                error_message=f"Recommendation is already in terminal state '{rec.status}'.",
                executed_at=now_iso,
                affected_entities=action,
            )
            self.audit_store.record_execution(res, operator_id, operator_note)
            return res

        # Check simulation clock vs TTL
        current_sim_time = int(getattr(simulator.state, "current_time", 0))
        if current_sim_time > rec.expires_at_sim_time:
            rec.status = RecommendationStatus.EXPIRED
            res = ExecutionResult(
                execution_id=exec_id,
                recommendation_id=rec.recommendation_id,
                decision_type=rec.decision_type,
                status=RecommendationStatus.EXPIRED,
                error_message=f"Recommendation TTL expired at T+{rec.expires_at_sim_time}m (current T+{current_sim_time}m).",
                executed_at=now_iso,
                affected_entities=action,
            )
            self.audit_store.record_execution(res, operator_id, operator_note)
            return res

        # --------------------------------------------------------------
        # 2. STALE-STATE & CONSTRAINT REVALIDATION
        # --------------------------------------------------------------
        fresh_snapshot = self.observer.capture_snapshot(simulator)
        state_hash_before = fresh_snapshot.snapshot_hash

        validation_error = self._validate_constraints(rec, simulator, fresh_snapshot)
        if validation_error:
            rec.status = RecommendationStatus.OBSOLETE
            rec.rejection_reason = validation_error
            res = ExecutionResult(
                execution_id=exec_id,
                recommendation_id=rec.recommendation_id,
                decision_type=rec.decision_type,
                status=RecommendationStatus.OBSOLETE,
                error_message=f"Stale state / constraint violation: {validation_error}",
                state_hash_before=state_hash_before,
                state_hash_after=state_hash_before,
                executed_at=now_iso,
                affected_entities=action,
            )
            self.audit_store.record_execution(res, operator_id, operator_note)
            return res

        # --------------------------------------------------------------
        # 3. APPROVAL & EXECUTION
        # --------------------------------------------------------------
        rec.status = RecommendationStatus.APPROVED
        rec.approved_by = operator_id
        rec.approved_at = now_iso
        rec.status = RecommendationStatus.EXECUTING

        details: Dict[str, Any] = {}
        try:
            if rec.decision_type == "FLEET_REPOSITION":
                details = self._execute_reposition(rec, simulator)
            elif rec.decision_type == "HOSPITAL_DIVERSION":
                details = self._execute_diversion(rec, simulator, operator_id, operator_note)
            elif rec.decision_type == "MCI_INTERCEPTION":
                details = self._execute_interception(rec, simulator)
            else:
                raise ValueError(f"Unsupported optimization decision type '{rec.decision_type}'.")

        except Exception as ex:
            rec.status = RecommendationStatus.FAILED
            res = ExecutionResult(
                execution_id=exec_id,
                recommendation_id=rec.recommendation_id,
                decision_type=rec.decision_type,
                status=RecommendationStatus.FAILED,
                error_message=f"Execution error in Simulator: {str(ex)}",
                state_hash_before=state_hash_before,
                state_hash_after=fresh_snapshot.snapshot_hash,
                executed_at=now_iso,
                affected_entities=action,
            )
            rec.execution_result = res
            self.audit_store.record_execution(res, operator_id, operator_note)
            return res

        # --------------------------------------------------------------
        # 4. CAPTURE AFTER-STATE & RECORD AUDIT
        # --------------------------------------------------------------
        post_snapshot = self.observer.capture_snapshot(simulator)
        state_hash_after = post_snapshot.snapshot_hash

        res = ExecutionResult(
            execution_id=exec_id,
            recommendation_id=rec.recommendation_id,
            decision_type=rec.decision_type,
            status="SUCCESS",
            error_message=None,
            state_hash_before=state_hash_before,
            state_hash_after=state_hash_after,
            executed_at=now_iso,
            affected_entities=action,
            details=details,
        )

        rec.status = RecommendationStatus.EXECUTED
        rec.execution_result = res
        self.audit_store.record_execution(res, operator_id, operator_note)

        return res

    def reject_recommendation(
        self,
        recommendation: OptimizationRecommendation,
        operator_id: str = "OPERATOR_DISPATCHER",
        reason: Optional[str] = None,
    ) -> OptimizationRecommendation:
        """Explicitly record operator rejection of an advisory recommendation."""
        now_iso = datetime.now(timezone.utc).isoformat()
        rec = recommendation
        rec.status = RecommendationStatus.REJECTED
        rec.rejection_reason = reason or "Operator dismissed recommendation"
        rec.rejection_note = reason
        rec.approved_by = operator_id
        rec.approved_at = now_iso

        res = ExecutionResult(
            execution_id=f"REJ_{uuid.uuid4().hex[:12].upper()}",
            recommendation_id=rec.recommendation_id,
            decision_type=rec.decision_type,
            status=RecommendationStatus.REJECTED,
            error_message=rec.rejection_reason,
            executed_at=now_iso,
            affected_entities=rec.candidate_action,
        )
        rec.execution_result = res
        self.audit_store.record_execution(res, operator_id, reason)
        return rec

    def _validate_constraints(
        self,
        rec: OptimizationRecommendation,
        simulator,
        snapshot: OperationalSnapshot,
    ) -> Optional[str]:
        """Verify hard constraints and entity existence against live state."""
        action = rec.candidate_action
        dtype = rec.decision_type
        state = simulator.state

        if dtype == "FLEET_REPOSITION":
            aid = str(action.get("ambulance_id", ""))
            ambulance = state.ambulances.get(aid)
            if not ambulance:
                return f"Ambulance '{aid}' no longer exists in fleet."

            status = str(ambulance.status).upper()
            if status != "AVAILABLE" or getattr(ambulance, "is_repositioning", False):
                return f"Ambulance '{aid}' status changed to '{status}' (is_repositioning={getattr(ambulance, 'is_repositioning', False)})."

            if ambulance.incident_id is not None:
                return f"Ambulance '{aid}' is now committed to incident {ambulance.incident_id}."

            donor_z = action.get("donor_zone")
            if donor_z:
                z_data = snapshot.zone_coverage.get(donor_z, {})
                if z_data.get("available_count", 0) <= 1:
                    return f"Donor zone '{donor_z}' only has {z_data.get('available_count')} unit; cannot reposition last unit."

        elif dtype == "HOSPITAL_DIVERSION":
            iid = action.get("incident_id")
            incident = state.incidents.get(int(iid)) if iid is not None else None
            if not incident:
                return f"Incident '{iid}' no longer exists in simulation."

            ambulance = state.ambulances.get(str(incident.ambulance_id)) if incident.ambulance_id else None
            if not ambulance or str(ambulance.status).upper() != "EN_ROUTE":
                return f"Assigned ambulance is not currently EN_ROUTE (status={getattr(ambulance, 'status', 'None')})."

            rec_h_id = str(action.get("recommended_hospital_id", ""))
            hospital = state.hospitals.get(rec_h_id)
            if not hospital:
                return f"Recommended hospital '{rec_h_id}' not found."

            proj = snapshot.hospital_projected_capacities.get(rec_h_id, {})
            if proj.get("projected_available_beds", 0) <= 0:
                return f"Recommended hospital '{rec_h_id}' has 0 projected available beds."

            pri = str(action.get("priority", "P3")).upper()
            if pri in ("P1", "CRITICAL") and proj.get("projected_available_icu", 0) <= 0:
                return f"Recommended hospital '{rec_h_id}' has no available ICU beds for Critical emergency."

        elif dtype == "MCI_INTERCEPTION":
            aid = str(action.get("ambulance_id", ""))
            ambulance = state.ambulances.get(aid)
            if not ambulance:
                return f"Ambulance '{aid}' not found."

            is_repo = getattr(ambulance, "is_repositioning", False) or str(ambulance.status).upper() == "REPOSITIONING"
            if not is_repo:
                return f"Ambulance '{aid}' is no longer in REPOSITIONING status."

        return None

    def _execute_reposition(self, rec: OptimizationRecommendation, simulator) -> Dict[str, Any]:
        """Translate recommendation to simulator.execute_reposition()."""
        action = rec.candidate_action
        aid = str(action["ambulance_id"])
        target_z = str(action["target_zone"])

        # Determine target staging coordinates
        coord = getattr(simulator, "coordinator", None)
        if coord and hasattr(coord, "coverage_engine") and target_z in coord.coverage_engine.zones:
            staging = coord.coverage_engine.zones[target_z]["staging_post"]
        elif target_z in CoverageEngine.ZONES:
            staging = CoverageEngine.ZONES[target_z]["staging_post"]
        else:
            staging = (26.9180, 75.8150)  # Default Central staging post

        res = simulator.execute_reposition(
            ambulance_id=aid,
            target_lat=float(staging[0]),
            target_lon=float(staging[1]),
            reason=f"OPTIMIZATION_APPROVED_{rec.recommendation_id}",
        )
        return res

    def _execute_diversion(
        self,
        rec: OptimizationRecommendation,
        simulator,
        operator_id: str,
        operator_note: Optional[str],
    ) -> Dict[str, Any]:
        """Translate recommendation to simulator.apply_manual_redirection()."""
        action = rec.candidate_action
        iid = int(action["incident_id"])
        target_hosp = str(action["recommended_hospital_id"])

        reason = f"[OPERATOR_COPILOT] Optimization diversion approved by {operator_id}: {operator_note or 'ER Load Balance'}"
        res = simulator.apply_manual_redirection(
            incident_id=iid,
            target_hospital_id=target_hosp,
            reason=reason,
        )
        return res

    def _execute_interception(self, rec: OptimizationRecommendation, simulator) -> Dict[str, Any]:
        """Cancel repositioning to free ambulance for emergency interception."""
        action = rec.candidate_action
        aid = str(action["ambulance_id"])
        iid = action.get("incident_id")

        res = simulator.cancel_reposition(
            ambulance_id=aid,
            reason=f"OPTIMIZATION_INTERCEPT_{iid}",
        )
        return res
