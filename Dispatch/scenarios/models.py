"""
RAAH Scenario & Replay Domain Models (M10 Phase 1)
=================================================

Declarative scenario specifications, scheduled actions, simulation run metadata,
and portable replay container data structures.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone


@dataclass
class ScheduledIncident:
    """An incident scheduled to occur at a specific simulation clock minute."""
    sim_time: int
    incident_id: Optional[int] = None
    custom_data: Optional[Dict[str, Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    condition: Optional[str] = None
    severity: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledIncident":
        return cls(**data)


@dataclass
class ScheduledMCI:
    """A Multi-Casualty Incident scheduled for declaration at a specific clock minute."""
    sim_time: int
    name: str
    latitude: float
    longitude: float
    estimated_casualties: int
    mci_id: Optional[str] = None
    primary_condition: str = "Trauma"
    notes: str = ""
    casualties: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledMCI":
        return cls(**data)


@dataclass
class ScheduledReposition:
    """An idle ambulance repositioning movement scheduled for execution."""
    sim_time: int
    ambulance_id: str
    target_lat: float
    target_lon: float
    reason: str = "SCHEDULED_REPOSITION"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledReposition":
        return cls(**data)


@dataclass
class ScheduledRedirection:
    """A redirection intervention scheduled for execution."""
    sim_time: int
    incident_id: int
    target_hospital_id: Optional[str] = None
    reason: str = "SCHEDULED_DIVERSION"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledRedirection":
        return cls(**data)


@dataclass
class ScheduledHospitalEvent:
    """A facility capacity saturation or disruption event scheduled at a clock minute."""
    sim_time: int
    hospital_id: str
    event_type: str = "SET_SATURATED"  # SET_SATURATED, RELEASE_SATURATED, OVERRIDE_LOAD
    value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledHospitalEvent":
        return cls(**data)


@dataclass
class ScenarioConfig:
    """Execution parameters for deterministic scenario execution."""
    duration_minutes: int = 60
    tick_minutes: float = 1.0
    snapshot_interval_ticks: int = 5
    deterministic_seed: int = 42
    routing_engine_version: str = "M8_LocalApproxRouter"
    coordination_version: str = "M9_FleetCoordinator"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScenarioConfig":
        return cls(**data)


@dataclass
class ScenarioDefinition:
    """
    Pure declarative specification of an operational scenario.
    Does NOT contain live state, but defines all inputs, events, and scheduling.
    """
    scenario_id: str
    name: str
    description: str = ""
    config: ScenarioConfig = field(default_factory=ScenarioConfig)
    scheduled_incidents: List[ScheduledIncident] = field(default_factory=list)
    scheduled_mcis: List[ScheduledMCI] = field(default_factory=list)
    scheduled_repositions: List[ScheduledReposition] = field(default_factory=list)
    scheduled_redirections: List[ScheduledRedirection] = field(default_factory=list)
    scheduled_hospital_events: List[ScheduledHospitalEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "config": self.config.to_dict(),
            "scheduled_incidents": [i.to_dict() for i in self.scheduled_incidents],
            "scheduled_mcis": [m.to_dict() for m in self.scheduled_mcis],
            "scheduled_repositions": [r.to_dict() for r in self.scheduled_repositions],
            "scheduled_redirections": [d.to_dict() for d in self.scheduled_redirections],
            "scheduled_hospital_events": [h.to_dict() for h in self.scheduled_hospital_events],
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScenarioDefinition":
        return cls(
            scenario_id=str(data["scenario_id"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            config=ScenarioConfig.from_dict(data.get("config", {})),
            scheduled_incidents=[ScheduledIncident.from_dict(i) for i in data.get("scheduled_incidents", [])],
            scheduled_mcis=[ScheduledMCI.from_dict(m) for m in data.get("scheduled_mcis", [])],
            scheduled_repositions=[ScheduledReposition.from_dict(r) for r in data.get("scheduled_repositions", [])],
            scheduled_redirections=[ScheduledRedirection.from_dict(d) for d in data.get("scheduled_redirections", [])],
            scheduled_hospital_events=[ScheduledHospitalEvent.from_dict(h) for h in data.get("scheduled_hospital_events", [])],
            metadata=dict(data.get("metadata", {})),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )


@dataclass
class RunMetadata:
    """Telemetry and outcome metrics for a scenario execution run."""
    scenario_id: str
    run_id: str
    start_sim_time: int
    end_sim_time: int
    wall_clock_duration_seconds: float
    event_count: int
    snapshot_count: int
    completion_status: str  # COMPLETED, FAILED, STOPPED
    deterministic_seed: int
    replay_format_version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunMetadata":
        return cls(**data)


@dataclass
class ReplayArtifact:
    """
    Portable, self-contained JSON replay archive.
    Enables exact operational reconstruction and forward stepping without simulator locks.
    """
    replay_format_version: str
    run_metadata: RunMetadata
    scenario_definition: ScenarioDefinition
    events: List[Dict[str, Any]]
    snapshots: List[Dict[str, Any]]
    final_summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "replay_format_version": self.replay_format_version,
            "run_metadata": self.run_metadata.to_dict(),
            "scenario_definition": self.scenario_definition.to_dict(),
            "events": list(self.events),
            "snapshots": list(self.snapshots),
            "final_summary": dict(self.final_summary),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReplayArtifact":
        return cls(
            replay_format_version=str(data.get("replay_format_version", "1.0.0")),
            run_metadata=RunMetadata.from_dict(data["run_metadata"]),
            scenario_definition=ScenarioDefinition.from_dict(data["scenario_definition"]),
            events=list(data.get("events", [])),
            snapshots=list(data.get("snapshots", [])),
            final_summary=dict(data.get("final_summary", {})),
        )
