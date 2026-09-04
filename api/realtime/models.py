"""
RAAH Real-Time Event Models & Closed EventType Enumeration
=========================================================

Defines the versioned, deterministic event envelope and strict closed event types
for real-time projection and stream distribution.

INVARIANT: RealtimeEvent instances and payloads MUST NEVER contain mutable references
to DispatchState or sensitive credentials/tokens.
"""

from enum import Enum
from typing import Dict, Any, Optional
import json
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    """
    Closed, versioned enumeration of all authoritative real-time event types.
    Arbitrary or undocumented event types are strictly rejected.
    """
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    TICK = "TICK"
    INCIDENT_DISPATCHED = "INCIDENT_DISPATCHED"
    AMBULANCE_UPDATE = "AMBULANCE_UPDATE"
    REDIRECTION_EXECUTED = "REDIRECTION_EXECUTED"
    MCI_ALERT = "MCI_ALERT"
    HOSPITAL_UPDATE = "HOSPITAL_UPDATE"
    SYSTEM_ALERT = "SYSTEM_ALERT"
    HEARTBEAT = "HEARTBEAT"


class RealtimeEvent(BaseModel):
    """
    Versioned realtime event envelope.
    Guarantees deterministic serialization with sorted keys and canonical JSON formatting.
    """
    schema_version: int = Field(default=1, description="Event envelope schema version")
    event_id: str = Field(
        default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}",
        description="Unique deterministic event identifier",
    )
    event_type: str = Field(description="Must match a member of EventType enum")
    occurred_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of occurrence",
    )
    simulation_time: int = Field(description="Simulation clock time in minutes")
    sequence: int = Field(description="Strictly monotonic process-level sequence number")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Immutable projection payload")

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        valid_types = {e.value for e in EventType}
        if v not in valid_types:
            raise ValueError(
                f"Invalid event_type '{v}'. Must be one of: {sorted(valid_types)}"
            )
        return v

    def to_sse(self) -> str:
        """
        Deterministic Server-Sent Events (SSE) representation.
        Enforces sorted keys and canonical separators for repeatable stream framing.
        """
        data_str = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return f"id: {self.sequence}\nevent: {self.event_type}\ndata: {data_str}\n\n"

    def to_json(self) -> str:
        """
        Deterministic JSON string representation.
        """
        return json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
