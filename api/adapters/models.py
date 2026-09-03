"""
RAAH Normalized External Event & Ingestion Models
=================================================

Defines the normalized event contracts, payload schemas, and ingestion responses
for external CAD, GPS, Hospital status, and Traffic telemetry feeds.
"""

import time
import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Literal
from pydantic import BaseModel, Field, field_validator


class EventStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    REJECTED = "REJECTED"
    STALE = "STALE"
    QUARANTINED = "QUARANTINED"


class EventType(str, Enum):
    INCIDENT_CALL = "INCIDENT_CALL"
    AMBULANCE_GPS = "AMBULANCE_GPS"
    HOSPITAL_STATUS = "HOSPITAL_STATUS"
    TRAFFIC_UPDATE = "TRAFFIC_UPDATE"


# ======================================================================
# NORMALIZED EVENT CONTRACT
# ======================================================================

class NormalizedEvent(BaseModel):
    """
    Versioned normalized contract for all inbound external operational telemetry.
    """
    event_id: str = Field(
        default_factory=lambda: f"evt_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
        description="Globally unique normalized event ID",
    )
    event_type: str = Field(
        ...,
        description="Event classification: INCIDENT_CALL | AMBULANCE_GPS | HOSPITAL_STATUS | TRAFFIC_UPDATE",
    )
    source: str = Field(
        ...,
        description="Identifier of originating external provider (e.g., CAD_911, AVLS_GPS)",
    )
    source_event_id: str = Field(
        ...,
        description="Idempotent event ID issued by the external source system",
    )
    schema_version: int = Field(
        default=1,
        description="Normalized contract schema version",
    )
    occurred_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp when the event occurred in the real world",
    )
    received_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp when RAAH ingested the event",
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Distributed tracing correlation ID",
    )
    payload: Dict[str, Any] = Field(
        ...,
        description="Domain-specific payload dictionary",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Operational context, provider headers, or audit tags",
    )

    @field_validator("occurred_at", mode="before")
    @classmethod
    def default_occurred_at(cls, v: Any) -> str:
        if not v:
            return datetime.now(timezone.utc).isoformat()
        return str(v)

    @field_validator("correlation_id", mode="before")
    @classmethod
    def default_correlation_id(cls, v: Any) -> str:
        if not v:
            return str(uuid.uuid4())
        return str(v)

    @field_validator("source_event_id", "source", "event_type")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("Field cannot be empty or whitespace.")
        return str(v).strip()


# ======================================================================
# INGESTION RESPONSE
# ======================================================================

class IngestionResponse(BaseModel):
    """
    Deterministic response returned for external event ingestion.
    """
    status: EventStatus = Field(..., description="Ingestion outcome: ACCEPTED | DUPLICATE | REJECTED | STALE")
    event_id: str = Field(..., description="Normalized event ID")
    source: str = Field(..., description="External source identifier")
    source_event_id: str = Field(..., description="External source event ID")
    event_type: str = Field(..., description="Event type classification")
    received_at: str = Field(..., description="Receipt timestamp")
    message: str = Field(..., description="Human-readable result explanation")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Authoritative simulator outcome (e.g. dispatch assignment)")
    correlation_id: str = Field(..., description="Correlation ID for audit trace")
    duplicate_of: Optional[str] = Field(default=None, description="Event ID of initial accepted event if duplicate")
    seen_count: int = Field(default=1, description="Number of times this source_event_id was received")


# ======================================================================
# TYPED EXTERNAL PAYLOAD MODELS
# ======================================================================

class CADIncidentInput(BaseModel):
    """
    Inbound CAD emergency call intake payload.
    """
    source_event_id: str = Field(..., description="Unique CAD dispatch/incident ID")
    source: str = Field(default="CAD_911", description="CAD provider identifier")
    occurred_at: Optional[str] = Field(default=None, description="Call intake timestamp")

    # 6 Categorical Features (ML Pipeline)
    Sex: Literal["Female", "Male"] = "Female"
    Condition: Literal[
        "Cardiac",
        "Gastrointestinal",
        "Infection",
        "Neurological",
        "Other",
        "Respiratory",
        "Trauma",
    ] = "Cardiac"
    Oxygen_Requirement: Literal[
        "Nasal Cannula",
        "No Oxygen",
        "Oxygen Mask",
        "Ventilator",
    ] = "Oxygen Mask"
    Consciousness: Literal[
        "Alert",
        "Confused",
        "Drowsy",
        "Unconscious",
    ] = "Alert"
    Injury_Type: Literal[
        "Burn",
        "Fracture",
        "Head Injury",
        "Internal Injury",
        "Laceration",
        "No Injury",
    ] = "No Injury"
    Arrival_Mode: Literal[
        "Ambulance",
        "Referral",
        "Walk-in",
    ] = "Ambulance"

    # 18 Numeric Clinical Features
    Age: int = Field(default=45, ge=0, le=125)
    Heart_Rate: float = Field(default=85.0, ge=20.0, le=300.0)
    SpO2: float = Field(default=96.0, ge=40.0, le=100.0)
    Systolic_BP: float = Field(default=120.0, ge=40.0, le=300.0)
    Diastolic_BP: float = Field(default=80.0, ge=20.0, le=200.0)
    Respiratory_Rate: float = Field(default=18.0, ge=4.0, le=80.0)
    Temperature: float = Field(default=37.0, ge=30.0, le=45.0)
    GCS: int = Field(default=15, ge=3, le=15)
    Pain_Score: int = Field(default=4, ge=0, le=10)
    Blood_Glucose: float = Field(default=110.0, ge=20.0, le=1000.0)
    Respiratory_Distress: int = Field(default=0, ge=0, le=1)
    Chest_Pain: int = Field(default=1, ge=0, le=1)
    Bleeding: int = Field(default=0, ge=0, le=1)
    Seizure: int = Field(default=0, ge=0, le=1)
    Diabetes: int = Field(default=0, ge=0, le=1)
    Hypertension: int = Field(default=0, ge=0, le=1)
    Heart_Disease: int = Field(default=0, ge=0, le=1)
    Respiratory_Disease: int = Field(default=0, ge=0, le=1)

    # Location
    patient_lat: float = Field(..., ge=-90.0, le=90.0)
    patient_lon: float = Field(..., ge=-180.0, le=180.0)


class AmbulanceGPSInput(BaseModel):
    """
    Automatic Vehicle Location (AVL) GPS fix from ambulance unit.
    """
    source_event_id: str = Field(..., description="GPS fix transmission ID")
    source: str = Field(default="AVLS_GPS", description="GPS feed source")
    ambulance_id: str = Field(..., description="Vehicle identifier (e.g. AMB_01)")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    speed_kmh: Optional[float] = Field(default=None, ge=0.0, le=200.0)
    status: Optional[str] = Field(default=None, description="AVAILABLE | EN_ROUTE | AT_HOSPITAL")
    traffic_level: Optional[str] = Field(default=None, description="LIGHT | NORMAL | MODERATE | HEAVY | SEVERE")
    road_condition: Optional[str] = Field(default=None, description="GOOD | AVERAGE | POOR")
    occurred_at: Optional[str] = Field(default=None, description="GPS fix timestamp")


class HospitalStatusInput(BaseModel):
    """
    External hospital capacity and status telemetry.
    """
    source_event_id: str = Field(..., description="Hospital capacity feed transmission ID")
    source: str = Field(default="HOSP_FEED", description="Hospital feed source")
    hospital_id: str = Field(..., description="Hospital identifier (e.g. HOSP_01)")
    capacity: Optional[int] = Field(default=None, ge=0)
    current_load: Optional[int] = Field(default=None, ge=0)
    icu_capacity: Optional[int] = Field(default=None, ge=0)
    current_icu_load: Optional[int] = Field(default=None, ge=0)
    occurred_at: Optional[str] = Field(default=None, description="Status snapshot timestamp")


class TrafficUpdateInput(BaseModel):
    """
    External traffic or road incident telemetry feed.
    """
    source_event_id: str = Field(..., description="Traffic advisory transmission ID")
    source: str = Field(default="TRAFFIC_FEED", description="Traffic feed source")
    ambulance_id: Optional[str] = Field(default=None, description="Specific unit affected, or None for area-wide")
    traffic_level: str = Field(..., description="LIGHT | NORMAL | MODERATE | HEAVY | SEVERE")
    road_condition: str = Field(default="GOOD", description="GOOD | AVERAGE | POOR")
    occurred_at: Optional[str] = Field(default=None, description="Advisory timestamp")
