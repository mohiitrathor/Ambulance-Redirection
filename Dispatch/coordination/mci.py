"""
RAAH Multi-Casualty Incident (MCI) Manager
==========================================

Defines parent-level MCI event structures, lifecycle state machines,
casualty summaries, child incident associations, and evacuation progress tracking.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


class MCIStatus:
    DECLARED = "DECLARED"
    TRIAGED = "TRIAGED"
    EVACUATING = "EVACUATING"
    RESOLVED = "RESOLVED"

    ALL = {DECLARED, TRIAGED, EVACUATING, RESOLVED}


@dataclass
class MCIEvent:
    """
    Represents a major emergency scene involving multiple casualties.
    Parent orchestration record over standard child IncidentState records.
    """
    mci_id: str
    name: str
    latitude: float
    longitude: float
    declared_sim_time: int
    description: str = ""
    status: str = MCIStatus.DECLARED
    total_casualties: int = 0
    evacuated_count: int = 0
    child_incident_ids: List[int] = field(default_factory=list)
    casualty_counts_by_severity: Dict[str, int] = field(default_factory=dict)
    casualty_counts_by_priority: Dict[str, int] = field(default_factory=dict)
    assigned_ambulance_ids: List[str] = field(default_factory=list)
    hospital_distribution: Dict[str, int] = field(default_factory=dict)
    resolved_sim_time: Optional[int] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize MCIEvent into dictionary format."""
        return {
            "mci_id": self.mci_id,
            "name": self.name,
            "description": self.description or self.notes,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "declared_sim_time": self.declared_sim_time,
            "resolved_sim_time": self.resolved_sim_time,
            "status": self.status,
            "total_casualties": self.total_casualties,
            "evacuated_count": self.evacuated_count,
            "child_incident_ids": list(self.child_incident_ids),
            "casualty_counts_by_severity": dict(self.casualty_counts_by_severity),
            "casualty_counts_by_priority": dict(self.casualty_counts_by_priority),
            "assigned_ambulance_ids": list(self.assigned_ambulance_ids),
            "hospital_distribution": dict(self.hospital_distribution),
            "notes": self.notes,
        }


class MCIManager:
    """
    Manages active and historical Multi-Casualty Incidents.
    Maintains parent-child index mapping and coordinates evacuation lifecycle.
    """

    def __init__(self):
        # mci_id -> MCIEvent
        self._mcis: Dict[str, MCIEvent] = {}
        # incident_id -> mci_id index
        self._child_to_mci: Dict[int, str] = {}

    def create_mci(
        self,
        mci_id: str,
        name: str,
        latitude: float,
        longitude: float,
        declared_sim_time: int,
        estimated_casualties: int = 0,
        description: str = "",
        notes: str = "",
    ) -> MCIEvent:
        """
        Declare and register a new Multi-Casualty Incident.
        """
        mid = str(mci_id)
        if mid in self._mcis:
            raise ValueError(f"MCI with ID '{mid}' already exists.")

        event = MCIEvent(
            mci_id=mid,
            name=str(name),
            latitude=float(latitude),
            longitude=float(longitude),
            declared_sim_time=int(declared_sim_time),
            total_casualties=int(estimated_casualties),
            description=str(description or notes),
            notes=str(notes or description),
            status=MCIStatus.DECLARED,
        )
        self._mcis[mid] = event
        return event

    def attach_child_incident(
        self,
        mci_id: str,
        incident_id: int,
        severity: str = "Moderate",
        priority: int = 3,
        ambulance_id: Optional[str] = None,
        hospital_id: Optional[str] = None,
    ) -> bool:
        """
        Associate an individual patient incident record with the parent MCI event.
        """
        mid = str(mci_id)
        iid = int(incident_id)
        if mid not in self._mcis:
            return False

        event = self._mcis[mid]
        if iid not in event.child_incident_ids:
            event.child_incident_ids.append(iid)

        self._child_to_mci[iid] = mid

        # Update severity breakdown
        sev = str(severity).title()
        event.casualty_counts_by_severity[sev] = event.casualty_counts_by_severity.get(sev, 0) + 1

        # Update priority breakdown (P1..P5)
        p_key = f"P{priority}"
        event.casualty_counts_by_priority[p_key] = event.casualty_counts_by_priority.get(p_key, 0) + 1

        if ambulance_id and ambulance_id not in event.assigned_ambulance_ids:
            event.assigned_ambulance_ids.append(str(ambulance_id))

        if hospital_id:
            hid = str(hospital_id)
            event.hospital_distribution[hid] = event.hospital_distribution.get(hid, 0) + 1

        event.total_casualties = len(event.child_incident_ids)

        # Transition status from DECLARED to TRIAGED if not already evacuating
        if event.status == MCIStatus.DECLARED:
            event.status = MCIStatus.TRIAGED

        return True

    def record_assignment(
        self,
        mci_id: str,
        ambulance_id: str,
        hospital_id: str,
    ) -> bool:
        """
        Record an ambulance and hospital assignment for an MCI casualty.
        Transitions MCI status to EVACUATING if currently TRIAGED or DECLARED.
        """
        mid = str(mci_id)
        if mid not in self._mcis:
            return False

        event = self._mcis[mid]
        aid = str(ambulance_id)
        hid = str(hospital_id)

        if aid not in event.assigned_ambulance_ids:
            event.assigned_ambulance_ids.append(aid)

        event.hospital_distribution[hid] = event.hospital_distribution.get(hid, 0) + 1

        if event.status in (MCIStatus.DECLARED, MCIStatus.TRIAGED):
            event.status = MCIStatus.EVACUATING

        return True

    def update_status(self, mci_id: str, new_status: str, sim_time: Optional[int] = None) -> bool:
        """
        Advance the lifecycle status of an MCI event.
        """
        mid = str(mci_id)
        if mid not in self._mcis:
            return False

        status_norm = str(new_status).upper()
        if status_norm not in MCIStatus.ALL:
            raise ValueError(f"Invalid MCI status: {new_status}")

        event = self._mcis[mid]
        event.status = status_norm

        if status_norm == MCIStatus.RESOLVED and sim_time is not None:
            event.resolved_sim_time = int(sim_time)

        return True

    def check_mci_progress(
        self,
        mci_id: str,
        incidents: dict,
        sim_time: int,
    ) -> Tuple[int, bool]:
        """
        Check evacuation progress of all child incidents.
        If all child incidents are arrived/resolved, mark MCI as RESOLVED.
        Returns (evacuated_count, is_resolved).
        """
        mid = str(mci_id)
        if mid not in self._mcis:
            return 0, False

        event = self._mcis[mid]
        if not event.child_incident_ids:
            return 0, False

        evacuated = 0
        all_done = True

        for cid in event.child_incident_ids:
            inc = incidents.get(cid)
            if inc is not None and getattr(inc, "status", None) in ("ARRIVED", "RESOLVED", "COMPLETED"):
                evacuated += 1
            else:
                all_done = False

        event.evacuated_count = evacuated

        # An MCI resolves ONLY when all casualties are evacuated/arrived
        if all_done and event.status == MCIStatus.EVACUATING:
            event.status = MCIStatus.RESOLVED
            event.resolved_sim_time = int(sim_time)
            return evacuated, True

        return evacuated, (event.status == MCIStatus.RESOLVED)

    def get_mci(self, mci_id: str) -> Optional[MCIEvent]:
        """Fetch a specific MCI event by ID."""
        return self._mcis.get(str(mci_id))

    def get_mci_for_incident(self, incident_id: int) -> Optional[str]:
        """Return parent mci_id for a given child incident_id."""
        return self._child_to_mci.get(int(incident_id))

    def list_active_mcis(self) -> List[MCIEvent]:
        """Return list of all non-resolved MCIs."""
        return [e for e in self._mcis.values() if e.status != MCIStatus.RESOLVED]

    def list_all_mcis(self) -> List[MCIEvent]:
        """Return list of all MCIs."""
        return list(self._mcis.values())

    def clear(self):
        """Reset all MCI records and child index."""
        self._mcis.clear()
        self._child_to_mci.clear()
