"""
RAAH Scenario Event Recorder & State Snapshots (M10 Phase 1)
============================================================

Captures structured, deterministically sequenced operational events
and lightweight, serializable state snapshots across simulation execution.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone


@dataclass
class OperationalEvent:
    """A structured operational event recorded during scenario execution."""
    event_id: int
    sim_time: int
    event_type: str
    entity_ids: Dict[str, Any] = field(default_factory=dict)
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sim_time": self.sim_time,
            "event_type": self.event_type,
            "entity_ids": dict(self.entity_ids),
            "payload": dict(self.payload),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OperationalEvent":
        return cls(**data)


@dataclass
class StateSnapshot:
    """Lightweight operational state captured at a simulation clock minute."""
    snapshot_id: int
    sim_time: int
    incidents: List[Dict[str, Any]] = field(default_factory=list)
    ambulances: List[Dict[str, Any]] = field(default_factory=list)
    hospitals: List[Dict[str, Any]] = field(default_factory=list)
    active_mcis: List[Dict[str, Any]] = field(default_factory=list)
    repositioning: List[Dict[str, Any]] = field(default_factory=list)
    coverage_summary: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "sim_time": self.sim_time,
            "incidents": list(self.incidents),
            "ambulances": list(self.ambulances),
            "hospitals": list(self.hospitals),
            "active_mcis": list(self.active_mcis),
            "repositioning": list(self.repositioning),
            "coverage_summary": dict(self.coverage_summary),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateSnapshot":
        return cls(**data)


class ScenarioRecorder:
    """
    Observational recorder attached to a scenario execution run.
    Maintains strictly monotonic event sequences and serializable periodic snapshots.
    """

    def __init__(self):
        self._events: List[OperationalEvent] = []
        self._snapshots: List[StateSnapshot] = []
        self._next_event_id: int = 1
        self._next_snapshot_id: int = 1

    def record_event(
        self,
        sim_time: int,
        event_type: str,
        entity_ids: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> OperationalEvent:
        """
        Record a structured operational event with monotonic sequence ordering.
        """
        ev = OperationalEvent(
            event_id=self._next_event_id,
            sim_time=int(sim_time),
            event_type=str(event_type),
            entity_ids=dict(entity_ids or {}),
            payload=dict(payload or {}),
        )
        self._next_event_id += 1
        self._events.append(ev)
        return ev

    def capture_snapshot(self, sim_time: int, sim) -> StateSnapshot:
        """
        Capture a lightweight, serializable state snapshot from the simulator.
        Does not mutate state or copy locks or internal engine references.
        """
        # 1. Incidents summary
        incidents_list = []
        for inc in sim.state.incidents.values():
            incidents_list.append({
                "incident_id": inc.incident_id,
                "condition": getattr(inc, "condition", ""),
                "severity": getattr(inc, "severity", ""),
                "priority": getattr(inc, "priority", 5),
                "status": getattr(inc, "status", ""),
                "ambulance_id": getattr(inc, "ambulance_id", None),
                "hospital_id": getattr(inc, "hospital_id", None),
            })

        # 2. Ambulances summary
        ambulances_list = []
        for amb in sim.state.ambulances.values():
            wps = getattr(amb, "route_waypoints", None)
            ambulances_list.append({
                "ambulance_id": amb.ambulance_id,
                "ambulance_type": getattr(amb, "ambulance_type", "BLS"),
                "status": getattr(amb, "status", "AVAILABLE"),
                "latitude": float(getattr(amb, "latitude", 0.0)),
                "longitude": float(getattr(amb, "longitude", 0.0)),
                "incident_id": getattr(amb, "incident_id", None),
                "hospital_id": getattr(amb, "hospital_id", None),
                "eta_minutes": float(amb.eta_minutes) if getattr(amb, "eta_minutes", None) is not None else None,
                "route_waypoints": [list(p) for p in wps] if wps else [],
                "is_repositioning": bool(getattr(amb, "is_repositioning", False)),
            })

        # 3. Hospitals summary
        hospitals_list = []
        projections = {}
        if hasattr(sim, "coordinator") and hasattr(sim.coordinator, "get_hospital_projections"):
            projections = sim.coordinator.get_hospital_projections(sim.state.hospitals)

        for hid, h in sim.state.hospitals.items():
            proj = projections.get(hid, {})
            hospitals_list.append({
                "hospital_id": hid,
                "name": getattr(h, "name", str(hid)),
                "current_load": int(getattr(h, "current_load", 0)),
                "capacity": int(getattr(h, "capacity", 0)),
                "available_beds": int(getattr(h, "available_beds", 0)),
                "projected_available_beds": int(proj.get("projected_available_beds", getattr(h, "available_beds", 0))),
                "icu_capacity": int(getattr(h, "icu_capacity", 0)),
                "current_icu_load": int(getattr(h, "current_icu_load", 0)),
                "available_icu": int(getattr(h, "available_icu", 0)),
                "projected_available_icu": int(proj.get("projected_available_icu", getattr(h, "available_icu", 0))),
                "incoming_count": int(proj.get("incoming_count", 0)),
                "incoming_critical": int(proj.get("incoming_critical", 0)),
                "is_full": bool(getattr(h, "is_full", False)),
            })

        # 4. MCIs
        mcis_list = []
        if hasattr(sim, "coordinator") and hasattr(sim.coordinator, "mci_manager"):
            mcis_list = [m.to_dict() for m in sim.coordinator.mci_manager.list_all_mcis()]

        # 5. Repositioning state
        repositions_list = []
        for aid, data in getattr(sim, "repositioning_data", {}).items():
            repositions_list.append({
                "ambulance_id": aid,
                "origin_zone": data.get("origin_zone"),
                "target_zone": data.get("target_zone"),
                "target_coords": data.get("target_coords"),
            })

        # 6. Coverage summary
        cov_summary = {}
        if hasattr(sim, "coordinator") and hasattr(sim.coordinator, "get_coverage"):
            try:
                cov_summary = sim.coordinator.get_coverage(sim.state.ambulances)
            except Exception:
                pass

        snap = StateSnapshot(
            snapshot_id=self._next_snapshot_id,
            sim_time=int(sim_time),
            incidents=incidents_list,
            ambulances=ambulances_list,
            hospitals=hospitals_list,
            active_mcis=mcis_list,
            repositioning=repositions_list,
            coverage_summary=cov_summary,
        )
        self._next_snapshot_id += 1
        self._snapshots.append(snap)
        return snap

    def get_events(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._events]

    def get_snapshots(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._snapshots]

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)

    def clear(self):
        self._events.clear()
        self._snapshots.clear()
        self._next_event_id = 1
        self._next_snapshot_id = 1
