"""
RAAH State Persistence & Durability Interface
=============================================

Defines the abstract contract, data transfer models, and failure exceptions
for authoritative DispatchState persistence and checkpointing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


# ======================================================================
# EXCEPTIONS
# ======================================================================

class PersistenceError(Exception):
    """Base exception for all persistence layer errors."""
    pass


class CorruptCheckpointError(PersistenceError):
    """Raised when a checkpoint fails checksum verification or integrity checks."""
    pass


class IncompatibleSchemaError(PersistenceError):
    """Raised when a serialized state payload uses an unsupported schema version."""
    pass


class CorruptStateError(PersistenceError):
    """Raised when state fields, data types, or domain invariants are invalid."""
    pass


class DatabaseUnavailableError(PersistenceError):
    """Raised when the persistent storage medium or database cannot be reached."""
    pass


class DatabaseLockedError(PersistenceError):
    """Raised when persistent storage is locked or busy timeout expires."""
    pass


# ======================================================================
# DATA MODELS
# ======================================================================

@dataclass
class CheckpointRecord:
    """
    Durable checkpoint record containing metadata and serialized DispatchState.
    """
    checkpoint_id: str
    simulation_time: int
    schema_version: int
    saved_at: str
    payload: Dict[str, Any]
    checksum: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_valid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to a serializable dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "simulation_time": self.simulation_time,
            "schema_version": self.schema_version,
            "saved_at": self.saved_at,
            "checksum": self.checksum,
            "is_valid": self.is_valid,
            "metadata": self.metadata,
            "payload_summary": {
                "incident_count": len(self.payload.get("state", {}).get("incidents", {})),
                "ambulance_count": len(self.payload.get("state", {}).get("ambulances", {})),
                "hospital_count": len(self.payload.get("state", {}).get("hospitals", {})),
                "event_count": len(self.payload.get("state", {}).get("events", [])),
            } if isinstance(self.payload, dict) else {},
        }


@dataclass
class IdempotencyRecord:
    """
    Durable record representing an processed external event for deduplication.
    """
    idempotency_key: str
    source: str
    source_event_id: str
    event_type: str
    status: str
    response_payload: Dict[str, Any]
    first_seen_at: str
    last_seen_at: str
    seen_count: int = 1
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "idempotency_key": self.idempotency_key,
            "source": self.source,
            "source_event_id": self.source_event_id,
            "event_type": self.event_type,
            "status": self.status,
            "response_payload": self.response_payload,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "seen_count": self.seen_count,
            "correlation_id": self.correlation_id,
        }


# ======================================================================
# PERSISTENCE STORE INTERFACE
# ======================================================================

class StatePersistenceStore(ABC):
    """
    Abstract contract for state persistence and durability backends.
    """

    @abstractmethod
    def save_state(self, state_data: Dict[str, Any], key: str = "current_state") -> bool:
        """
        Atomically save an arbitrary state snapshot under a key.
        """
        pass

    @abstractmethod
    def load_state(self, key: str = "current_state") -> Optional[Dict[str, Any]]:
        """
        Load an arbitrary state snapshot by key, or return None if not found.
        """
        pass

    @abstractmethod
    def save_checkpoint(
        self,
        state_data: Dict[str, Any],
        sim_time: int,
        metadata: Optional[Dict[str, Any]] = None,
        checkpoint_id: Optional[str] = None,
    ) -> CheckpointRecord:
        """
        Atomically create and persist a durable checkpoint record.
        """
        pass

    @abstractmethod
    def load_latest_checkpoint(self) -> Optional[CheckpointRecord]:
        """
        Retrieve the latest valid checkpoint record, or None if no checkpoints exist.
        """
        pass

    @abstractmethod
    def load_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointRecord]:
        """
        Retrieve a specific checkpoint record by ID.
        """
        pass

    @abstractmethod
    def list_checkpoints(self, limit: int = 50) -> List[CheckpointRecord]:
        """
        Retrieve chronological list of checkpoint records (newest first).
        """
        pass

    @abstractmethod
    def get_idempotency_record(self, source: str, source_event_id: str) -> Optional[IdempotencyRecord]:
        """
        Lookup durable idempotency record by source and source_event_id.
        """
        pass

    @abstractmethod
    def save_idempotency_record(self, record: IdempotencyRecord) -> bool:
        """
        Atomically persist an idempotency record.
        """
        pass

    @abstractmethod
    def increment_idempotency_seen(self, source: str, source_event_id: str) -> Optional[IdempotencyRecord]:
        """
        Atomically increment seen_count and update last_seen_at for duplicate detection.
        """
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Perform diagnostic probe on storage availability and responsiveness.
        Returns a dictionary with at minimum {"healthy": bool, "backend": str}.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Cleanly close open connections, handles, and resources.
        """
        pass
