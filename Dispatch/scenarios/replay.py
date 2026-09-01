"""
RAAH Replay Engine (M10 Phase 1)
================================

Standalone playback engine for recorded ReplayArtifact archives.
Provides deterministic operational state reconstruction, forward stepping,
seeking (via snapshots + event catchup), and fast-forward playback
without mutating recorded archives or interfering with live simulation state.
"""

from typing import Dict, List, Optional, Any
from copy import deepcopy

from .models import ReplayArtifact


class ReplayEngine:
    """
    Independent playback and state reconstruction engine.
    Does NOT depend on Simulator or DispatchState; faithfully reconstructs
    observable operational state for timeline inspection and command center replay.
    """

    def __init__(self, artifact: ReplayArtifact):
        self.artifact = artifact
        # Immutable event sequence sorted deterministically
        self._events: List[Dict[str, Any]] = sorted(
            artifact.events, key=lambda e: (e.get("sim_time", 0), e.get("event_id", 0))
        )
        # Snapshots indexed by simulation time
        self._snapshots: List[Dict[str, Any]] = sorted(
            artifact.snapshots, key=lambda s: s.get("sim_time", 0)
        )

        self.current_time: int = 0
        self.current_event_index: int = 0

        # Observable reconstructed operational state
        self.incidents: Dict[int, Dict[str, Any]] = {}
        self.ambulances: Dict[str, Dict[str, Any]] = {}
        self.hospitals: Dict[str, Dict[str, Any]] = {}
        self.active_mcis: Dict[str, Dict[str, Any]] = {}
        self.repositioning: Dict[str, Dict[str, Any]] = {}
        self.coverage_summary: Dict[str, Any] = {}
        self.events_history: List[Dict[str, Any]] = []

        # Initialize to first snapshot if present
        if self._snapshots:
            self._apply_snapshot(self._snapshots[0])
            self.current_time = self._snapshots[0].get("sim_time", 0)

    def _apply_snapshot(self, snap: Dict[str, Any]):
        """Load observable state directly from a snapshot."""
        self.incidents = {i["incident_id"]: deepcopy(i) for i in snap.get("incidents", [])}
        self.ambulances = {a["ambulance_id"]: deepcopy(a) for a in snap.get("ambulances", [])}
        self.hospitals = {h["hospital_id"]: deepcopy(h) for h in snap.get("hospitals", [])}
        self.active_mcis = {m["mci_id"]: deepcopy(m) for m in snap.get("active_mcis", [])}
        self.repositioning = {r["ambulance_id"]: deepcopy(r) for r in snap.get("repositioning", [])}
        self.coverage_summary = deepcopy(snap.get("coverage_summary", {}))

    def _apply_event(self, ev: Dict[str, Any]):
        """Apply operational effect of a single event to reconstructed state."""
        e_type = ev.get("event_type")
        payload = ev.get("payload", {})
        entity_ids = ev.get("entity_ids", {})

        if e_type == "DISPATCH":
            iid = entity_ids.get("incident_id")
            aid = entity_ids.get("ambulance_id")
            hid = entity_ids.get("hospital_id")
            if iid is not None:
                self.incidents[iid] = {
                    "incident_id": iid,
                    "status": "DISPATCHED",
                    "ambulance_id": aid,
                    "hospital_id": hid,
                    "severity": payload.get("severity", "Moderate"),
                    "priority": payload.get("priority", 3),
                }
            if aid and aid in self.ambulances:
                self.ambulances[aid]["status"] = "EN_ROUTE"
                self.ambulances[aid]["incident_id"] = iid
                self.ambulances[aid]["hospital_id"] = hid
                if "eta_minutes" in payload:
                    self.ambulances[aid]["eta_minutes"] = payload["eta_minutes"]

        elif e_type == "AMBULANCE_ARRIVED":
            aid = entity_ids.get("ambulance_id")
            hid = entity_ids.get("hospital_id")
            if aid and aid in self.ambulances:
                self.ambulances[aid]["status"] = "ARRIVED"
                self.ambulances[aid]["eta_minutes"] = 0.0
                iid = self.ambulances[aid].get("incident_id")
                if iid and iid in self.incidents:
                    self.incidents[iid]["status"] = "ARRIVED"
            if hid and hid in self.hospitals:
                self.hospitals[hid]["current_load"] = self.hospitals[hid].get("current_load", 0) + 1

        elif e_type == "REDIRECTION":
            iid = entity_ids.get("incident_id")
            new_hid = entity_ids.get("target_hospital_id")
            if iid and iid in self.incidents:
                self.incidents[iid]["hospital_id"] = new_hid
                aid = self.incidents[iid].get("ambulance_id")
                if aid and aid in self.ambulances:
                    self.ambulances[aid]["hospital_id"] = new_hid

        elif e_type == "REPOSITION_START":
            aid = entity_ids.get("ambulance_id")
            if aid and aid in self.ambulances:
                self.ambulances[aid]["status"] = "REPOSITIONING"
                self.ambulances[aid]["is_repositioning"] = True
                self.repositioning[aid] = {
                    "ambulance_id": aid,
                    "target_lat": payload.get("target_coords", [0, 0])[0] if payload.get("target_coords") else 0.0,
                    "target_lon": payload.get("target_coords", [0, 0])[1] if payload.get("target_coords") else 0.0,
                }

        elif e_type == "MCI_DECLARED":
            mid = entity_ids.get("mci_id")
            if mid:
                self.active_mcis[mid] = {
                    "mci_id": mid,
                    "name": payload.get("name", "MCI"),
                    "status": "EVACUATING" if payload.get("dispatched_count", 0) > 0 else "TRIAGED",
                    "total_casualties": payload.get("total_casualties", 0),
                    "evacuated_count": 0,
                    "assigned_ambulance_ids": payload.get("assigned_ambulances", []),
                    "hospital_distribution": payload.get("hospital_distribution", {}),
                }

        elif e_type == "HOSPITAL_SATURATED":
            hid = entity_ids.get("hospital_id")
            if hid and hid in self.hospitals:
                self.hospitals[hid]["is_full"] = True
                self.hospitals[hid]["available_beds"] = 0
                self.hospitals[hid]["current_load"] = self.hospitals[hid].get("capacity", 0)

        elif e_type == "HOSPITAL_RESTORED":
            hid = entity_ids.get("hospital_id")
            if hid and hid in self.hospitals:
                self.hospitals[hid]["is_full"] = False
                self.hospitals[hid]["current_load"] = int(self.hospitals[hid].get("capacity", 0) * 0.5)
                self.hospitals[hid]["available_beds"] = max(
                    0, self.hospitals[hid]["capacity"] - self.hospitals[hid]["current_load"]
                )

        self.events_history.append(ev)

    def step(self) -> bool:
        """
        Advance one event forward in the replay timeline.
        Returns True if an event was processed, False if at the end of the replay.
        """
        if self.current_event_index >= len(self._events):
            return False

        ev = self._events[self.current_event_index]
        self._apply_event(ev)
        self.current_time = ev.get("sim_time", self.current_time)
        self.current_event_index += 1
        return True

    def seek(self, target_sim_time: int) -> bool:
        """
        Seek to a specific simulation clock minute.
        Finds the closest preceding snapshot and fast-forwards events up to target_sim_time.
        """
        target_t = int(target_sim_time)
        if target_t < 0:
            target_t = 0

        # Find closest preceding snapshot
        best_snap = None
        for s in self._snapshots:
            if s.get("sim_time", 0) <= target_t:
                best_snap = s
            else:
                break

        self.events_history.clear()

        if best_snap:
            self._apply_snapshot(best_snap)
            snap_time = best_snap.get("sim_time", 0)
            self.current_time = snap_time
            # Position event index to first event at or after snap_time
            idx = 0
            while idx < len(self._events) and self._events[idx].get("sim_time", 0) < snap_time:
                idx += 1
            self.current_event_index = idx
        else:
            self.current_time = 0
            self.current_event_index = 0

        # Play forward up to target_sim_time
        while self.current_event_index < len(self._events):
            ev = self._events[self.current_event_index]
            if ev.get("sim_time", 0) > target_t:
                break
            self._apply_event(ev)
            self.current_time = ev.get("sim_time", self.current_time)
            self.current_event_index += 1

        self.current_time = target_t
        return True

    def play_to_end(self) -> int:
        """Fast-forward through all remaining events in the replay artifact."""
        count = 0
        while self.step():
            count += 1
        return count

    def get_state(self) -> Dict[str, Any]:
        """
        Return the reconstructed operational state at the current replay position.
        """
        total_evs = len(self._events)
        pct = round((self.current_event_index / max(1, total_evs)) * 100, 1)

        return {
            "sim_time": self.current_time,
            "current_event_index": self.current_event_index,
            "total_events": total_evs,
            "progress_percent": pct,
            "is_completed": self.current_event_index >= total_evs,
            "incidents": list(self.incidents.values()),
            "ambulances": list(self.ambulances.values()),
            "hospitals": list(self.hospitals.values()),
            "active_mcis": list(self.active_mcis.values()),
            "repositioning": list(self.repositioning.values()),
            "coverage_summary": dict(self.coverage_summary),
        }

    def get_events(self, processed_only: bool = True) -> List[Dict[str, Any]]:
        """Return events processed up to current position or entire event log."""
        if processed_only:
            return list(self.events_history)
        return list(self._events)
