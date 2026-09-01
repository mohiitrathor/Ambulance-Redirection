"""
RAAH Resilience & Operational Performance Metrics (M10 Phase 2)
===============================================================

Extracts comprehensive fleet, incident, hospital, and MCI performance metrics
from recorded ReplayArtifact data. Calculates a transparent, multi-component
ResilienceScore without arbitrary heuristics.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import math

from Dispatch.scenarios.models import ReplayArtifact


@dataclass
class ResilienceScore:
    """Transparent, multi-component resilience evaluation (0.0 - 100.0)."""
    overall: float
    fleet_score: float
    dispatch_score: float
    hospital_score: float
    evacuation_score: float
    saturation_penalty: float
    unresolved_penalty: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DrillMetricsCalculator:
    """Calculates operational performance and resilience score from replay data."""

    @classmethod
    def compute(cls, replay: ReplayArtifact) -> Dict[str, Any]:
        snapshots = replay.snapshots or []
        events = replay.events or []

        # --------------------------------------------------------------
        # 1. FLEET TELEMETRY
        # --------------------------------------------------------------
        total_amb = 0
        peak_en_route = 0
        peak_repositioning = 0
        peak_proj_utilization = 0.0
        hospitals_reaching_full = set()
        hospitals_reaching_icu_full = set()
        max_simultaneous_reservations = 0

        for snap in snapshots:
            ambs = snap.get("ambulances", [])
            if not total_amb and ambs:
                total_amb = len(ambs)

            en_route = sum(1 for a in ambs if a.get("status") == "EN_ROUTE")
            repo = sum(1 for a in ambs if a.get("is_repositioning", False) or a.get("status") == "REPOSITIONING")
            peak_en_route = max(peak_en_route, en_route)
            peak_repositioning = max(peak_repositioning, repo)

            # Hospital telemetry from snapshots
            hosps = snap.get("hospitals", [])
            tot_incoming = 0
            for h in hosps:
                cap = max(1, h.get("capacity", 1))
                load = h.get("current_load", 0)
                tot_incoming += h.get("incoming_count", 0)
                util = load / cap
                peak_proj_utilization = max(peak_proj_utilization, util)

                if h.get("is_full") or h.get("available_beds", 1) <= 0:
                    hospitals_reaching_full.add(h.get("hospital_id"))
                if h.get("available_icu", 1) <= 0 and h.get("icu_capacity", 0) > 0:
                    hospitals_reaching_icu_full.add(h.get("hospital_id"))

            max_simultaneous_reservations = max(max_simultaneous_reservations, tot_incoming)

        # --------------------------------------------------------------
        # 2. EVENT-DRIVEN INCIDENT & DISPATCH TELEMETRY
        # --------------------------------------------------------------
        dispatch_etas = []
        dispatched_incidents = set()
        hospitals_used = set()
        hospital_load_dist: Dict[str, int] = {}
        mci_count = 0
        mci_casualties = 0
        peak_concurrent_mci = 0

        for ev in events:
            e_type = ev.get("event_type")
            e_ids = ev.get("entity_ids", {})
            payload = ev.get("payload", {})

            if e_type == "DISPATCH":
                iid = e_ids.get("incident_id")
                hid = e_ids.get("hospital_id")
                if iid is not None:
                    dispatched_incidents.add(iid)
                if hid:
                    hospitals_used.add(hid)
                    hospital_load_dist[hid] = hospital_load_dist.get(hid, 0) + 1
                eta = payload.get("eta_minutes")
                if eta is not None and isinstance(eta, (int, float)):
                    dispatch_etas.append(float(eta))

            elif e_type == "MCI_DECLARED":
                mci_count += 1
                mci_casualties += payload.get("total_casualties", 0)
                dist = payload.get("hospital_distribution", {})
                for hid, count in dist.items():
                    hospitals_used.add(hid)
                    hospital_load_dist[hid] = hospital_load_dist.get(hid, 0) + count

            elif e_type == "HOSPITAL_SATURATED":
                hid = e_ids.get("hospital_id")
                if hid:
                    hospitals_reaching_full.add(hid)

        for snap in snapshots:
            active_m = len(snap.get("active_mcis", []))
            peak_concurrent_mci = max(peak_concurrent_mci, active_m)

        # --------------------------------------------------------------
        # 3. FINAL SUMMARY TOTALS
        # --------------------------------------------------------------
        final_snap = snapshots[-1] if snapshots else {}
        final_incidents = final_snap.get("incidents", [])

        # Total casualties = total in incidents snapshot or summary
        total_casualties = len(final_incidents) if final_incidents else (len(dispatched_incidents) or mci_casualties or 1)
        # If MCI declaration had more casualties than tracked incidents
        total_casualties = max(total_casualties, mci_casualties, len(dispatched_incidents))

        dispatched_count = len(dispatched_incidents)
        arrived_count = sum(1 for i in final_incidents if i.get("status") in ("ARRIVED", "RESOLVED", "COMPLETED"))
        # Count arrivals from events if not tracked in snapshot incidents
        arrival_events = sum(1 for e in events if e.get("event_type") == "AMBULANCE_ARRIVED")
        arrived_count = max(arrived_count, arrival_events)

        waiting_count = max(0, total_casualties - dispatched_count)
        unresolved_count = max(0, total_casualties - arrived_count)

        avg_dispatch_eta = round(sum(dispatch_etas) / max(1, len(dispatch_etas)), 2) if dispatch_etas else 0.0
        max_transport_eta = round(max(dispatch_etas), 2) if dispatch_etas else 0.0

        ambulance_utilization = round((peak_en_route / max(1, total_amb)) * 100.0, 2)
        dispatch_success_ratio = round((dispatched_count / max(1, total_casualties)) * 100.0, 2)

        # --------------------------------------------------------------
        # 4. TRANSPARENT RESILIENCE SCORE FORMULA
        # --------------------------------------------------------------
        # Component 1: Dispatch Score (0 - 100) — Proportion of casualties successfully dispatched
        dispatch_score = min(100.0, (dispatched_count / max(1, total_casualties)) * 100.0)

        # Component 2: Fleet Score (0 - 100) — Penalizes unserviced casualties waiting for fleet
        fleet_score = max(0.0, 100.0 - ((waiting_count / max(1, total_casualties)) * 100.0))

        # Component 3: Hospital Score (0 - 100) — Ratio of non-saturated to saturated hospitals used
        h_used_cnt = max(1, len(hospitals_used))
        sat_ratio = min(1.0, len(hospitals_reaching_full) / h_used_cnt)
        hospital_score = max(0.0, 100.0 - (sat_ratio * 50.0))

        # Component 4: Evacuation Progress Score (0 - 100) — Rate of patients transported/admitted
        evacuation_score = min(100.0, (arrived_count / max(1, total_casualties)) * 100.0)

        # Penalties:
        saturation_penalty = round(min(30.0, len(hospitals_reaching_full) * 5.0), 2)
        unresolved_penalty = round(min(40.0, (unresolved_count / max(1, total_casualties)) * 40.0), 2)

        # Weighted composite:
        # 35% dispatch + 25% fleet coverage + 20% hospital load + 20% evacuation progress
        base_score = (
            0.35 * dispatch_score
            + 0.25 * fleet_score
            + 0.20 * hospital_score
            + 0.20 * evacuation_score
        )
        overall_score = round(max(0.0, min(100.0, base_score - (0.5 * saturation_penalty) - (0.5 * unresolved_penalty))), 2)

        resilience = ResilienceScore(
            overall=overall_score,
            fleet_score=round(dispatch_score, 2),
            dispatch_score=round(dispatch_score, 2),
            hospital_score=round(hospital_score, 2),
            evacuation_score=round(evacuation_score, 2),
            saturation_penalty=saturation_penalty,
            unresolved_penalty=unresolved_penalty,
        )

        return {
            "fleet_metrics": {
                "total_ambulances": total_amb,
                "peak_en_route": peak_en_route,
                "peak_repositioning": peak_repositioning,
                "utilization_ratio_pct": ambulance_utilization,
                "dispatch_success_ratio_pct": dispatch_success_ratio,
                "waiting_for_ambulance_count": waiting_count,
                "average_dispatch_eta_minutes": avg_dispatch_eta,
            },
            "incident_metrics": {
                "total_casualties": total_casualties,
                "dispatched_casualties": dispatched_count,
                "waiting_casualties": waiting_count,
                "arrived_casualties": arrived_count,
                "unresolved_casualties": unresolved_count,
                "average_transport_eta": avg_dispatch_eta,
                "max_transport_eta": max_transport_eta,
            },
            "hospital_metrics": {
                "hospitals_used_count": len(hospitals_used),
                "peak_projected_utilization": round(peak_proj_utilization, 3),
                "hospitals_reaching_full_count": len(hospitals_reaching_full),
                "hospitals_reaching_icu_full_count": len(hospitals_reaching_icu_full),
                "hospital_load_distribution": hospital_load_dist,
                "max_simultaneous_incoming_reservations": max_simultaneous_reservations,
            },
            "mci_metrics": {
                "total_mcis": mci_count,
                "peak_concurrent_mcis": peak_concurrent_mci,
                "unresolved_mci_casualties": unresolved_count,
            },
            "resilience_score": resilience.to_dict(),
        }
