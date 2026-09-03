"""
RAAH External Telemetry & CAD Adapters Package
==============================================
"""

from api.adapters.models import (
    NormalizedEvent,
    IngestionResponse,
    EventStatus,
    EventType,
    CADIncidentInput,
    AmbulanceGPSInput,
    HospitalStatusInput,
    TrafficUpdateInput,
)
from api.adapters.interfaces import (
    IncidentSource,
    LocationSource,
    HospitalStatusSource,
    TrafficSource,
)
from api.adapters.mock_providers import (
    MockCADProvider,
    MockGPSProvider,
    MockHospitalProvider,
    MockTrafficProvider,
)
from api.adapters.registry import (
    AdapterRegistry,
    adapter_registry,
)
from api.adapters.service import (
    IngestionService,
    ingestion_service,
)

__all__ = [
    "NormalizedEvent",
    "IngestionResponse",
    "EventStatus",
    "EventType",
    "CADIncidentInput",
    "AmbulanceGPSInput",
    "HospitalStatusInput",
    "TrafficUpdateInput",
    "IncidentSource",
    "LocationSource",
    "HospitalStatusSource",
    "TrafficSource",
    "MockCADProvider",
    "MockGPSProvider",
    "MockHospitalProvider",
    "MockTrafficProvider",
    "AdapterRegistry",
    "adapter_registry",
    "IngestionService",
    "ingestion_service",
]
