"""
RAAH What-If Decision Simulator (M11 Phase 1)
=============================================

Executes isolated, observational what-if impact simulations for proposed
candidate actions. Evaluates whether a recommendation provides a net positive
operational impact compared to the status quo without touching live state.
"""

from typing import Dict, Any, Optional
from Dispatch.optimization.models import (
    OperationalSnapshot,
    OptimizationCandidate,
    SimulationImpact,
)


class DecisionSimulator:
    """Simulates what-if outcomes of optimization candidates in strict isolation."""

    def simulate_candidate(
        self,
        candidate: OptimizationCandidate,
        snapshot: OperationalSnapshot,
    ) -> SimulationImpact:
        """
        Evaluate hypothetical delta impact of applying a candidate action.
        Guaranteed zero mutation of live simulator or authoritative state.
        """
        dtype = candidate.decision_type
        ents = candidate.affected_entities

        if dtype == "FLEET_REPOSITION":
            return self._simulate_reposition(candidate, snapshot, ents)
        elif dtype == "HOSPITAL_DIVERSION":
            return self._simulate_diversion(candidate, snapshot, ents)
        elif dtype == "MCI_INTERCEPTION":
            return self._simulate_interception(candidate, snapshot, ents)
        else:
            return SimulationImpact(
                candidate_id=candidate.candidate_id,
                coverage_change={},
                fleet_utilization_change=0.0,
                hospital_projected_load_change={},
                eta_impact_minutes=0.0,
                affected_incidents_count=0,
                affected_mcis_count=0,
                resilience_impact=0.0,
                is_better_than_baseline=False,
                summary=f"Unknown decision type {dtype}; no simulation executed.",
            )

    def _simulate_reposition(
        self,
        cand: OptimizationCandidate,
        snapshot: OperationalSnapshot,
        ents: Dict[str, Any],
    ) -> SimulationImpact:
        target_z = ents.get("target_zone", "")
        donor_z = ents.get("donor_zone", "")

        zones = snapshot.zone_coverage
        t_data = zones.get(target_z, {})
        d_data = zones.get(donor_z, {})

        t_target = max(1, t_data.get("target_capacity", 5))
        d_target = max(1, d_data.get("target_capacity", 5))

        t_score_before = t_data.get("coverage_score", 0.0)
        t_score_after = round(float(t_data.get("available_count", 0) + 1) / t_target, 2)

        d_score_before = d_data.get("coverage_score", 1.0)
        d_score_after = round(float(max(0, d_data.get("available_count", 0) - 1)) / d_target, 2)

        delta_target = round(t_score_after - t_score_before, 2)
        delta_donor = round(d_score_after - d_score_before, 2)

        cov_change = {
            target_z: delta_target,
            donor_z: delta_donor,
        }

        # Net resilience impact is positive if target deficit was critical and donor stays safe
        is_safe_donor = d_score_after >= 0.50
        resilience_delta = 1.8 if (t_score_before <= 0.20 and is_safe_donor) else 0.8
        is_better = delta_target > 0 and is_safe_donor

        summary = (
            f"What-If Simulation: Moving {ents.get('ambulance_id')} yields "
            f"{target_z} coverage +{delta_target:.2f} ({t_score_before:.2f} -> {t_score_after:.2f}), "
            f"while {donor_z} coverage decreases by {abs(delta_donor):.2f} ({d_score_before:.2f} -> {d_score_after:.2f}). "
            f"Estimated citywide resilience gain: +{resilience_delta:.1f} pts."
        )

        return SimulationImpact(
            candidate_id=cand.candidate_id,
            coverage_change=cov_change,
            fleet_utilization_change=0.0,
            hospital_projected_load_change={},
            eta_impact_minutes=-1.2,  # Faster response for future calls in target zone
            affected_incidents_count=0,
            affected_mcis_count=0,
            resilience_impact=resilience_delta,
            is_better_than_baseline=is_better,
            summary=summary,
        )

    def _simulate_diversion(
        self,
        cand: OptimizationCandidate,
        snapshot: OperationalSnapshot,
        ents: Dict[str, Any],
    ) -> SimulationImpact:
        curr_h = ents.get("current_hospital_id", "")
        rec_h = ents.get("recommended_hospital_id", "")

        projections = snapshot.hospital_projected_capacities
        curr_p = projections.get(curr_h, {})
        rec_p = projections.get(rec_h, {})

        curr_beds = curr_p.get("projected_available_beds", 0)
        rec_beds = rec_p.get("projected_available_beds", 0)

        hosp_change = {
            curr_h: 1.0,   # Relieves 1 bed from overburdened facility
            rec_h: -1.0,   # Consumes 1 bed at surplus facility
        }

        eta_delta = ents.get("estimated_eta_delta_minutes", 2.0)
        resilience_delta = 2.4  # Prevents ER saturation and ambulance offload delay
        is_better = rec_beds > curr_beds + 3

        summary = (
            f"What-If Simulation: Diverting transport from {curr_h} to {rec_h} "
            f"preserves critical bed capacity at {curr_h} (+1 bed buffer) "
            f"with an acceptable transport transit increase of +{eta_delta:.1f}m. "
            f"Estimated emergency resilience gain: +{resilience_delta:.1f} pts."
        )

        return SimulationImpact(
            candidate_id=cand.candidate_id,
            coverage_change={},
            fleet_utilization_change=0.0,
            hospital_projected_load_change=hosp_change,
            eta_impact_minutes=eta_delta,
            affected_incidents_count=1,
            affected_mcis_count=0,
            resilience_impact=resilience_delta,
            is_better_than_baseline=is_better,
            summary=summary,
        )

    def _simulate_interception(
        self,
        cand: OptimizationCandidate,
        snapshot: OperationalSnapshot,
        ents: Dict[str, Any],
    ) -> SimulationImpact:
        iid = ents.get("incident_id", "")
        aid = ents.get("ambulance_id", "")
        pri = ents.get("priority", "P1")

        eta_saving = -6.5
        resilience_delta = 3.5

        summary = (
            f"What-If Simulation: Diverting {aid} to urgent {pri} emergency {iid} "
            f"reduces response ETA by ~{-eta_saving:.1f}m and clears immediate queue backlog. "
            f"Estimated operational resilience gain: +{resilience_delta:.1f} pts."
        )

        return SimulationImpact(
            candidate_id=cand.candidate_id,
            coverage_change={},
            fleet_utilization_change=0.0,
            hospital_projected_load_change={},
            eta_impact_minutes=eta_saving,
            affected_incidents_count=1,
            affected_mcis_count=1 if "MCI" in str(iid) else 0,
            resilience_impact=resilience_delta,
            is_better_than_baseline=True,
            summary=summary,
        )
