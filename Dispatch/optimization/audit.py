"""
RAAH Optimization Execution Audit Store (M11 Phase 2)
=====================================================

Provides atomic, process-restart persistent logging for all operator approval
decisions and authoritative optimization executions.
"""

import os
import json
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from Dispatch.optimization.models import ExecutionResult


def _safe_serialize(obj):
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_safe_serialize(item) for item in obj]
    if hasattr(obj, "to_dict"):
        return _safe_serialize(obj.to_dict())
    if hasattr(obj, "__dict__"):
        return _safe_serialize(vars(obj))
    return str(obj)


_REPO_ROOT = Path(__file__).resolve().parents[2]


class ExecutionAuditStore:
    """Thread-safe, atomic JSON store for optimization execution audit records."""

    DEFAULT_STORE_PATH = _REPO_ROOT / "data" / "optimization" / "execution_audit.json"

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = store_path or self.DEFAULT_STORE_PATH
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self):
        with self._lock:
            if not self.store_path.exists():
                self._write_atomic([])

    def _read_records(self) -> List[Dict[str, Any]]:
        if not self.store_path.exists():
            return []
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_atomic(self, records: List[Dict[str, Any]]):
        clean_records = _safe_serialize(records)
        tmp_path = self.store_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(clean_records, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.store_path)

    def record_execution(
        self,
        result: ExecutionResult,
        operator_id: str = "OPERATOR_DISPATCHER",
        operator_note: Optional[str] = None,
        execution_mode: str = "OPERATOR_APPROVED",
        policy_mode: str = "GUARDED",
        policy_decision: str = "AUTO_APPROVE",
        confidence: float = 1.0,
        policy_version: str = "1.0.0",
        policy_rules_evaluated: Optional[List[str]] = None,
        policy_rejection_reason: Optional[str] = None,
        predicted_benefit: float = 0.0,
        actual_benefit: float = 0.0,
        outcome: str = "PENDING",
        rollback_of: Optional[str] = None,
        kill_switch_state: bool = False,
    ) -> Dict[str, Any]:
        """Atomically append or update an execution audit record with policy metadata."""
        now_iso = datetime.now(timezone.utc).isoformat()
        record = {
            "execution_id": result.execution_id,
            "recommendation_id": result.recommendation_id,
            "recommendation_type": result.decision_type,
            "operator_id": operator_id,
            "operator_note": operator_note,
            "execution_mode": execution_mode,
            "policy_mode": policy_mode,
            "policy_decision": policy_decision,
            "confidence": float(confidence),
            "policy_version": policy_version,
            "policy_rules_evaluated": policy_rules_evaluated or [],
            "policy_rejection_reason": policy_rejection_reason,
            "predicted_benefit": float(predicted_benefit),
            "actual_benefit": float(actual_benefit),
            "outcome": outcome,
            "rollback_of": rollback_of,
            "kill_switch_state": bool(kill_switch_state),
            "requested_at": result.executed_at or now_iso,
            "approved_at": result.executed_at or now_iso,
            "executed_at": result.executed_at or now_iso,
            "state_hash_before": result.state_hash_before,
            "state_hash_after": result.state_hash_after,
            "action_parameters": _safe_serialize(result.details),
            "execution_status": result.status,
            "failure_reason": result.error_message,
            "resulting_entity_ids": _safe_serialize(result.affected_entities),
        }

        with self._lock:
            records = self._read_records()
            records = [r for r in records if r.get("execution_id") != result.execution_id]
            records.append(record)
            self._write_atomic(records)

        return record

    def update_outcome(
        self,
        execution_id: str,
        outcome: str,
        actual_benefit: float,
    ) -> Optional[Dict[str, Any]]:
        """Update the measured outcome and actual benefit for an execution record."""
        with self._lock:
            records = self._read_records()
            target_record = None
            for r in records:
                if r.get("execution_id") == execution_id:
                    r["outcome"] = outcome
                    r["actual_benefit"] = float(actual_benefit)
                    target_record = r
                    break
            if target_record:
                self._write_atomic(records)
            return target_record

    def get_executions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent execution audit records in reverse chronological order."""
        with self._lock:
            records = self._read_records()
            return sorted(records, key=lambda r: r.get("executed_at", ""), reverse=True)[:limit]

    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific execution audit record by execution_id."""
        with self._lock:
            records = self._read_records()
            for r in records:
                if r.get("execution_id") == execution_id:
                    return r
        return None

    def clear(self):
        """Purge all audit records (primarily for test resets)."""
        with self._lock:
            self._write_atomic([])
