from pydantic import BaseModel
from typing import Optional


# ==============================================================
# INCIDENT
# ==============================================================

class IncidentResponse(BaseModel):
    """Incident state as serialized by SimulationOutput.incident()."""

    incident_id: int
    condition: str
    severity: str
    priority: int
    status: str
    ambulance_id: Optional[str] = None
    hospital_id: Optional[str] = None


# ==============================================================
# AMBULANCE
# ==============================================================

class AmbulanceResponse(BaseModel):
    """Ambulance state as serialized by SimulationOutput.ambulance()."""

    ambulance_id: str
    ambulance_type: str
    latitude: float
    longitude: float
    status: str
    incident_id: Optional[int] = None
    hospital_id: Optional[str] = None
    eta_minutes: Optional[float] = None
    base_eta_minutes: Optional[float] = None
    traffic_level: str
    road_condition: str


# ==============================================================
# HOSPITAL
# ==============================================================

class HospitalResponse(BaseModel):
    """Hospital state as serialized by SimulationOutput.hospital()."""

    hospital_id: str
    hospital_type: str
    latitude: float
    longitude: float
    capacity: int
    current_load: int
    available_beds: int
    icu_capacity: int
    current_icu_load: int
    available_icu: int
    is_full: bool
    icu_available: bool


# ==============================================================
# FLEET SUMMARY
# ==============================================================

class FleetSummary(BaseModel):
    """Aggregate fleet status counts."""

    total: int
    available: int
    en_route: int
    busy: int
    maintenance: int
    arrived: int


# ==============================================================
# EVENT RECORD
# ==============================================================

class EventRecord(BaseModel):
    """A single simulation event log entry."""

    time: int
    message: str


# ==============================================================
# FULL SNAPSHOT
# ==============================================================

class SnapshotResponse(BaseModel):
    """
    Complete system state as returned by
    SimulationOutput.snapshot().
    """

    time: int
    incidents: list[IncidentResponse]
    ambulances: list[AmbulanceResponse]
    hospitals: list[HospitalResponse]
    fleet: FleetSummary
    events: list[EventRecord]


# ==============================================================
# DASHBOARD ACTIVE INCIDENT
# ==============================================================

class DashboardActiveIncident(BaseModel):
    """Active incident entry in the dashboard snapshot."""

    incident_id: int
    priority: int
    severity: str
    status: str
    ambulance_id: Optional[str] = None
    hospital_id: Optional[str] = None
    eta_minutes: Optional[float] = None


# ==============================================================
# DASHBOARD SNAPSHOT
# ==============================================================

class DashboardResponse(BaseModel):
    """
    Lightweight snapshot as returned by
    SimulationOutput.dashboard_snapshot().
    """

    time: int
    active_incidents: list[DashboardActiveIncident]
    fleet: FleetSummary
    events: list[EventRecord]
