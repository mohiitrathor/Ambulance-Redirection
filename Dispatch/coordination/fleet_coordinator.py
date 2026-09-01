"""
RAAH Master Fleet Coordinator
=============================

Central coordinator facade orchestrating CoverageEngine, HospitalBalancer,
and MCIManager. Exposes clean, read-only coordination queries to the Simulator
and API layers without mutating live simulation state.
"""

from typing import Dict, List, Optional, Tuple

from .coverage import CoverageEngine, ZoneCoverage, RepositionAdvisory
from .hospital_balancer import HospitalBalancer, InFlightReservation
from .mci import MCIManager, MCIEvent, MCIStatus


class FleetCoordinator:
    """
    Unified facade for citywide fleet coordination and predictive load balancing.
    """

    def __init__(
        self,
        coverage_engine: Optional[CoverageEngine] = None,
        hospital_balancer: Optional[HospitalBalancer] = None,
        mci_manager: Optional[MCIManager] = None,
    ):
        self.coverage_engine = coverage_engine or CoverageEngine()
        self.hospital_balancer = hospital_balancer or HospitalBalancer()
        self.mci_manager = mci_manager or MCIManager()

    # ------------------------------------------------------------------
    # COVERAGE & REPOSITIONING (READ-ONLY)
    # ------------------------------------------------------------------

    def get_coverage(
        self,
        ambulances: dict,
        recent_incident_coords: Optional[List[Tuple[float, float]]] = None,
    ) -> Dict[str, dict]:
        """
        Evaluate real-time fleet coverage across all 6 Jaipur sectors.
        Returns serialized dict of zone coverage summaries.
        """
        metrics = self.coverage_engine.evaluate_coverage(ambulances, recent_incident_coords)
        return {
            zid: {
                "zone_id": zm.zone_id,
                "zone_name": zm.zone_name,
                "centroid": list(zm.centroid),
                "staging_post": list(zm.staging_post),
                "target_capacity": zm.target_capacity,
                "available_count": len(zm.available_ambulances),
                "total_count": zm.total_ambulances,
                "demand_weight": zm.demand_weight,
                "coverage_score": zm.coverage_score,
                "status": zm.status,
            }
            for zid, zm in metrics.items()
        }

    def get_reposition_recommendations(
        self,
        ambulances: dict,
        recent_incident_coords: Optional[List[Tuple[float, float]]] = None,
    ) -> List[dict]:
        """
        Generate candidate idle ambulance repositioning advisories (DATA ONLY).
        """
        advisories = self.coverage_engine.get_reposition_recommendations(ambulances, recent_incident_coords)
        return [
            {
                "advisory_id": adv.advisory_id,
                "ambulance_id": adv.ambulance_id,
                "origin_zone": adv.origin_zone,
                "target_zone": adv.target_zone,
                "origin_coords": list(adv.origin_coords),
                "target_staging_post": list(adv.target_staging_post),
                "reason": adv.reason,
                "priority": adv.priority,
            }
            for adv in advisories
        ]

    # ------------------------------------------------------------------
    # HOSPITAL BALANCING (READ-ONLY)
    # ------------------------------------------------------------------

    def get_hospital_projections(self, hospitals: dict) -> Dict[str, dict]:
        """
        Compute projected remaining capacity for all active hospitals
        accounting for in-flight arrivals.
        """
        projections = {}
        for hid, hosp in hospitals.items():
            projections[str(hid)] = self.hospital_balancer.get_projected_capacity(str(hid), hosp)
        return projections

    def score_hospital_candidate(
        self,
        hospital_state,
        distance_km: float,
        eta_minutes: float,
        severity: str = "Moderate",
        condition: str = "General",
    ) -> float:
        """
        Score a single hospital candidate using predictive load balancing.
        """
        return self.hospital_balancer.score_hospital(
            hospital_state=hospital_state,
            distance_km=distance_km,
            eta_minutes=eta_minutes,
            severity=severity,
            condition=condition,
        )

    def select_balanced_hospital(
        self,
        hospitals: dict,
        patient_lat: float,
        patient_lon: float,
        severity: str = "Moderate",
        condition: str = "General",
        routing_engine=None,
        candidate_ids: Optional[set] = None,
        mci_surge_counts: Optional[Dict[str, int]] = None,
    ) -> Optional[str]:
        """
        Select optimal hospital using multi-objective load balancing.
        """
        return self.hospital_balancer.select_balanced_hospital(
            hospitals=hospitals,
            patient_lat=patient_lat,
            patient_lon=patient_lon,
            severity=severity,
            condition=condition,
            routing_engine=routing_engine,
            candidate_ids=candidate_ids,
            mci_surge_counts=mci_surge_counts,
        )

    # ------------------------------------------------------------------
    # MULTI-CASUALTY INCIDENTS (MCI)
    # ------------------------------------------------------------------

    def get_active_mcis(self) -> List[dict]:
        """
        Return serialized list of all active Multi-Casualty Incidents.
        """
        return [mci.to_dict() for mci in self.mci_manager.list_active_mcis()]

    def get_mci(self, mci_id: str) -> Optional[dict]:
        """
        Fetch details for a specific MCI.
        """
        mci = self.mci_manager.get_mci(mci_id)
        return mci.to_dict() if mci else None

    # ------------------------------------------------------------------
    # LIFECYCLE
    # ------------------------------------------------------------------

    def reset(self):
        """
        Reset transient in-flight reservations and active MCI events.
        """
        self.hospital_balancer.clear()
        self.mci_manager.clear()
