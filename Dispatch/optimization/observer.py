"""
RAAH Read-Only Operational Observer (M11 Phase 1)
=================================================

Passively observes the current authoritative DispatchState and Simulator state.
Constructs an immutable, normalized OperationalSnapshot without mutating any
simulator state, moving ambulances, or altering reservations.
"""

from typing import Dict, List, Any, Optional
import hashlib
import json

from Dispatch.optimization.models import OperationalSnapshot
from Dispatch.coordination.coverage import CoverageEngine
from Dispatch.coordination.hospital_balancer import HospitalBalancer


class OperationalObserver:
    """Read-only telemetry and state observer for real-time optimization."""

    def __init__(
        self,
        coverage_engine: Optional[CoverageEngine] = None,
        hospital_balancer: Optional[HospitalBalancer] = None,
    ):
        self.coverage_engine = coverage_engine or CoverageEngine()
        self.hospital_balancer = hospital_balancer or HospitalBalancer()

    def capture_snapshot(self, simulator) -> OperationalSnapshot:
        """
        Extract an immutable, observational operational snapshot from the simulator.
        Strictly read-only; no internal state mutations.
        """
        state = simulator.state
        sim_time = int(getattr(state, "current_time", 0))

        # --------------------------------------------------------------
        # 1. FLEET OBSERVATION
        # --------------------------------------------------------------
        ambulances = getattr(state, "ambulances", {})
        total_amb = len(ambulances)
        avail_amb = []
        busy_amb = []
        repo_amb = []
        maint_amb = []

        for aid, amb in ambulances.items():
            status = str(getattr(amb, "status", "AVAILABLE")).upper()
            if status == "AVAILABLE":
                avail_amb.append(str(aid))
            elif status == "REPOSITIONING":
                repo_amb.append(str(aid))
            elif status == "MAINTENANCE":
                maint_amb.append(str(aid))
            else:
                busy_amb.append(str(aid))

        fleet_util = round(float(len(busy_amb)) / max(1, total_amb) * 100.0, 2)

        # Zone Coverage
        recent_incident_coords = [
            (float(inc.patient_lat), float(inc.patient_lon))
            for inc in getattr(state, "incidents", {}).values()
            if getattr(inc, "patient_lat", None) is not None
        ][-20:]

        zone_coverages = self.coverage_engine.evaluate_coverage(
            ambulances=ambulances,
            recent_incident_coords=recent_incident_coords,
        )

        zone_coverage_dict = {}
        deficit_zones = []
        surplus_zones = []
        for zid, zc in zone_coverages.items():
            z_dict = {
                "zone_id": zc.zone_id,
                "zone_name": zc.zone_name,
                "available_count": len(zc.available_ambulances),
                "total_ambulances": zc.total_ambulances,
                "target_capacity": zc.target_capacity,
                "coverage_score": zc.coverage_score,
                "status": zc.status,
                "demand_weight": zc.demand_weight,
                "available_ambulances": list(zc.available_ambulances),
            }
            zone_coverage_dict[zid] = z_dict
            if zc.status == "DEFICIT":
                deficit_zones.append(zid)
            elif zc.status == "SURPLUS":
                surplus_zones.append(zid)

        fleet_availability = {
            "total_ambulances": total_amb,
            "available_count": len(avail_amb),
            "busy_count": len(busy_amb),
            "repositioning_count": len(repo_amb),
            "maintenance_count": len(maint_amb),
            "available_ambulance_ids": avail_amb,
            "deficit_zones": deficit_zones,
            "surplus_zones": surplus_zones,
        }

        # --------------------------------------------------------------
        # 2. INCIDENTS OBSERVATION
        # --------------------------------------------------------------
        incidents = getattr(state, "incidents", {})
        waiting_incidents = []
        active_incidents = []
        severity_dist = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0}

        for iid, inc in incidents.items():
            status = str(getattr(inc, "status", "UNKNOWN")).upper()
            pri = str(getattr(inc, "priority", "P3")).upper()
            if not pri.startswith("P"):
                pri = f"P{pri}"
            if pri in severity_dist:
                severity_dist[pri] += 1

            inc_summary = {
                "incident_id": str(iid),
                "priority": pri,
                "status": status,
                "ambulance_id": str(getattr(inc, "ambulance_id", None)),
                "hospital_id": str(getattr(inc, "hospital_id", None)),
                "eta_minutes": float(getattr(inc, "eta_minutes", 0.0)),
            }

            if status in ("WAITING", "QUEUED", "PENDING"):
                waiting_incidents.append(inc_summary)
            elif status in ("DISPATCHED", "EN_ROUTE", "ASSIGNED"):
                active_incidents.append(inc_summary)

        incidents_data = {
            "total_incidents": len(incidents),
            "waiting_count": len(waiting_incidents),
            "active_count": len(active_incidents),
            "severity_distribution": severity_dist,
            "waiting_incidents": waiting_incidents,
            "active_incidents": active_incidents,
        }

        # --------------------------------------------------------------
        # 3. HOSPITALS OBSERVATION
        # --------------------------------------------------------------
        hospitals = getattr(state, "hospitals", {})
        # If coordinator balancer is attached, use its projections
        balancer = getattr(simulator, "coordinator", None)
        if balancer and hasattr(balancer, "balancer"):
            h_balancer = balancer.balancer
        else:
            h_balancer = self.hospital_balancer

        hospital_projections = h_balancer.get_all_projections(hospitals)
        total_incoming = sum(p.get("incoming_count", 0) for p in hospital_projections.values())

        # --------------------------------------------------------------
        # 4. MCI OBSERVATION
        # --------------------------------------------------------------
        active_mcis = []
        coordinator = getattr(simulator, "coordinator", None)
        if coordinator and hasattr(coordinator, "mci_manager"):
            mci_mgr = coordinator.mci_manager
            for mid, mci in getattr(mci_mgr, "_active_mcis", {}).items():
                active_mcis.append({
                    "mci_id": str(mid),
                    "name": getattr(mci, "name", ""),
                    "status": getattr(mci, "status", "ACTIVE"),
                    "total_casualties": int(getattr(mci, "total_casualties", 0)),
                    "evacuated_count": int(getattr(mci, "evacuated_count", 0)),
                    "waiting_count": int(getattr(mci, "waiting_count", 0)),
                    "assigned_ambulances": list(getattr(mci, "assigned_ambulance_ids", [])),
                    "hospital_distribution": dict(getattr(mci, "hospital_distribution", {})),
                })

        # Redirection count
        redir_count = len(getattr(state, "redirection_history", []))

        # Deterministic snapshot hash
        hash_payload = {
            "sim_time": sim_time,
            "fleet_util": fleet_util,
            "avail_count": len(avail_amb),
            "waiting_count": len(waiting_incidents),
            "mci_count": len(active_mcis),
            "incoming_reservations": total_incoming,
            "deficit_zones": sorted(deficit_zones),
        }
        snap_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True).encode("utf-8")).hexdigest()[:20]

        return OperationalSnapshot(
            sim_time=sim_time,
            fleet_availability=fleet_availability,
            fleet_utilization=fleet_util,
            zone_coverage=zone_coverage_dict,
            active_incidents=incidents_data,
            active_mcis=active_mcis,
            hospital_projected_capacities=hospital_projections,
            incoming_reservations=total_incoming,
            repositioning_units=repo_amb,
            active_redirections=redir_count,
            snapshot_hash=snap_hash,
        )
