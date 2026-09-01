"""
RAAH Fleet Optimizer (M11 Phase 1)
==================================

Generates explainable fleet repositioning and ambulance interception candidate
recommendations based on real-time zone coverage deficits, surplus donors,
and waiting incident queues.
"""

from typing import List, Dict, Any, Optional, Tuple
from Dispatch.optimization.models import (
    OperationalSnapshot,
    OptimizationCandidate,
    DecisionExplanation,
    OptimizationRecommendation,
)
from Dispatch.optimization.scorer import DecisionScorer
from Dispatch.coordination.coverage import CoverageEngine


class FleetOptimizer:
    """Evaluates fleet distribution and produces explainable repositioning recommendations."""

    def __init__(self, scorer: Optional[DecisionScorer] = None):
        self.scorer = scorer or DecisionScorer()

    def generate_candidates(self, snapshot: OperationalSnapshot) -> List[OptimizationCandidate]:
        """
        Evaluate operational snapshot and generate ranked fleet repositioning candidates.
        """
        candidates: List[OptimizationCandidate] = []
        zones = snapshot.zone_coverage

        deficit_zones = [
            (zid, z) for zid, z in zones.items()
            if z.get("status") == "DEFICIT" or z.get("available_count", 0) == 0
        ]
        surplus_zones = [
            (zid, z) for zid, z in zones.items()
            if z.get("status") == "SURPLUS" or z.get("available_count", 0) > z.get("target_capacity", 5)
        ]

        # --------------------------------------------------------------
        # A & B: COVERAGE DEFICIT & SURPLUS DONOR REPOSITIONING
        # --------------------------------------------------------------
        # Sort deficit zones ascending by available count, then coverage score
        deficit_zones.sort(key=lambda item: (item[1].get("available_count", 0), item[1].get("coverage_score", 0.0)))
        # Sort surplus zones descending by available count
        surplus_zones.sort(key=lambda item: item[1].get("available_count", 0), reverse=True)

        for target_zid, target_z in deficit_zones:
            target_avail = target_z.get("available_count", 0)
            target_target = max(1, target_z.get("target_capacity", 5))
            target_score_curr = target_z.get("coverage_score", 0.0)
            target_score_next = round(float(target_avail + 1) / target_target, 2)

            if not surplus_zones:
                # Fleet saturation detected: deficit exists but no safe donor
                cand = OptimizationCandidate(
                    candidate_id=f"CAND_REPO_SAT_{target_zid}",
                    decision_type="FLEET_REPOSITION",
                    priority="HIGH",
                    affected_entities={"target_zone": target_zid},
                    target=target_zid,
                    expected_effect="No action possible due to citywide fleet saturation.",
                    confidence=0.90,
                    score=0.10,
                    rationale=f"Zone {target_zid} is in deficit ({target_avail} units), but no donor zone has surplus units to spare.",
                    constraints=["FLEET_SATURATION_NO_DONOR"],
                    generated_at_sim_time=snapshot.sim_time,
                    rejected=True,
                    rejection_reason="Cannot draw units without stripping other operational zones.",
                )
                candidates.append(cand)
                continue

            for donor_zid, donor_z in surplus_zones:
                donor_avail_ids = list(donor_z.get("available_ambulances", []))
                donor_avail_count = len(donor_avail_ids)
                donor_target = max(1, donor_z.get("target_capacity", 5))

                if donor_avail_count <= 1:
                    # Constraint: Never take the last ambulance from any zone
                    cand = OptimizationCandidate(
                        candidate_id=f"CAND_REPO_REJ_LAST_{donor_zid}_{target_zid}",
                        decision_type="FLEET_REPOSITION",
                        priority="LOW",
                        affected_entities={"donor_zone": donor_zid, "target_zone": target_zid},
                        target=target_zid,
                        expected_effect="Rejected: would deplete donor zone to zero available units.",
                        confidence=0.95,
                        score=0.0,
                        rationale=f"Refused donor {donor_zid}: only {donor_avail_count} unit available.",
                        constraints=["LAST_AMBULANCE_PROTECTION"],
                        generated_at_sim_time=snapshot.sim_time,
                        rejected=True,
                        rejection_reason=f"Constraint violation: taking unit would reduce {donor_zid} to zero coverage.",
                    )
                    candidates.append(cand)
                    continue

                chosen_amb = donor_avail_ids[0]
                donor_score_curr = donor_z.get("coverage_score", 1.0)
                donor_score_next = round(float(donor_avail_count - 1) / donor_target, 2)

                # Composite score calculation
                coverage_gain = min(1.0, (target_score_next - target_score_curr) + 0.5)
                safety = 0.95
                hosp_imp = 0.50
                eta_imp = 0.70
                risk = 0.15 if donor_avail_count >= 3 else 0.35

                score, breakdown, explanation = self.scorer.score_candidate(
                    decision_type="FLEET_REPOSITION",
                    clinical_safety=safety,
                    fleet_coverage=coverage_gain,
                    hospital_capacity=hosp_imp,
                    eta_impact=eta_imp,
                    operational_risk=risk,
                )

                cand = OptimizationCandidate(
                    candidate_id=f"CAND_REPO_{chosen_amb}_{target_zid}",
                    decision_type="FLEET_REPOSITION",
                    priority="HIGH" if target_avail == 0 else "MEDIUM",
                    affected_entities={
                        "ambulance_id": chosen_amb,
                        "donor_zone": donor_zid,
                        "target_zone": target_zid,
                        "donor_avail_before": donor_avail_count,
                        "donor_avail_after": donor_avail_count - 1,
                        "target_avail_before": target_avail,
                        "target_avail_after": target_avail + 1,
                    },
                    target=target_zid,
                    expected_effect=f"Increase {target_zid} coverage {target_score_curr:.2f} -> {target_score_next:.2f} (+1 unit).",
                    confidence=0.92,
                    score=score,
                    rationale=f"Zone {target_zid} has deficit ({target_avail} avail). Donor {donor_zid} has surplus ({donor_avail_count} avail).",
                    constraints=[
                        "DONOR_RETAINS_MINIMUM_UNITS",
                        "UNIT_IS_AVAILABLE_AND_IDLE",
                        "GEOGRAPHIC_ZONE_BOUNDARY_RESPECTED",
                    ],
                    generated_at_sim_time=snapshot.sim_time,
                    rejected=False,
                    score_breakdown=breakdown,
                )
                candidates.append(cand)
                break  # Recommend top donor for this deficit zone

        # --------------------------------------------------------------
        # C: AMBULANCE INTERCEPTION OPPORTUNITY FOR WAITING INCIDENTS
        # --------------------------------------------------------------
        waiting_incidents = snapshot.active_incidents.get("waiting_incidents", [])
        repositioning_units = snapshot.repositioning_units

        if waiting_incidents and repositioning_units:
            for inc in waiting_incidents[:3]:  # Top waiting
                pri = inc.get("priority", "P3")
                if pri in ("P1", "P2"):
                    # High severity waiting incident: propose intercepting nearest repo unit
                    target_amb = repositioning_units[0]
                    score, breakdown, explanation = self.scorer.score_candidate(
                        decision_type="MCI_INTERCEPTION",
                        clinical_safety=1.0,
                        fleet_coverage=0.60,
                        hospital_capacity=0.70,
                        eta_impact=0.90,
                        operational_risk=0.10,
                    )
                    cand = OptimizationCandidate(
                        candidate_id=f"CAND_INTERCEPT_{target_amb}_{inc['incident_id']}",
                        decision_type="MCI_INTERCEPTION",
                        priority="CRITICAL",
                        affected_entities={
                            "ambulance_id": target_amb,
                            "incident_id": inc["incident_id"],
                            "priority": pri,
                        },
                        target=inc["incident_id"],
                        expected_effect=f"Divert repositioning unit {target_amb} to urgent {pri} incident {inc['incident_id']}.",
                        confidence=0.96,
                        score=score,
                        rationale=f"Repositioning unit {target_amb} can be intercepted mid-transit to resolve high-priority {pri} emergency queue.",
                        constraints=["UNIT_STATUS_REPOSITIONING", "INCIDENT_STATUS_WAITING"],
                        generated_at_sim_time=snapshot.sim_time,
                        rejected=False,
                        score_breakdown=breakdown,
                    )
                    candidates.append(cand)

        return candidates

    def build_recommendations(
        self,
        candidates: List[OptimizationCandidate],
        snapshot: Optional[OperationalSnapshot] = None,
    ) -> List[OptimizationRecommendation]:
        """
        Convert valid OptimizationCandidate items into explainable OptimizationRecommendation items.
        """
        recs: List[OptimizationRecommendation] = []
        for c in candidates:
            if c.rejected:
                continue

            ents = c.affected_entities
            if c.decision_type == "FLEET_REPOSITION":
                summary = f"Reposition ambulance {ents.get('ambulance_id')} to {ents.get('target_zone')}."
                reasons = [
                    f"Target zone {ents.get('target_zone')} is currently in coverage deficit ({ents.get('target_avail_before')} available).",
                    f"Donor zone {ents.get('donor_zone')} has adequate staging buffer ({ents.get('donor_avail_before')} available).",
                    c.expected_effect,
                ]
                risks = [
                    f"Donor zone {ents.get('donor_zone')} available units decrease to {ents.get('donor_avail_after')}.",
                    "Ambulance is in transit and temporarily non-dispatchable unless intercepted.",
                ]
                benefit = f"Balances citywide coverage and eliminates critical coverage void in {ents.get('target_zone')}."
            else:
                summary = f"Intercept repositioning ambulance {ents.get('ambulance_id')} for emergency {ents.get('incident_id')}."
                reasons = [
                    f"Urgent {ents.get('priority')} incident {ents.get('incident_id')} is currently waiting in dispatch queue.",
                    f"Unit {ents.get('ambulance_id')} is actively transiting and can be diverted without teleportation.",
                ]
                risks = ["Cancels the intended repositioning movement to the target zone."]
                benefit = f"Immediate response to life-threatening {ents.get('priority')} call."

            explanation = DecisionExplanation(
                decision_id=f"EXPL_{c.candidate_id}",
                summary=summary,
                reasons=reasons,
                supporting_metrics={
                    "score_breakdown": c.score_breakdown,
                    "confidence": c.confidence,
                    "affected_entities": ents,
                },
                alternatives=[],
                risks=risks,
                expected_benefit=benefit,
            )

            severity = "CRITICAL" if c.priority == "CRITICAL" else ("WARNING" if c.priority == "HIGH" else "INFO")

            rec = OptimizationRecommendation(
                recommendation_id=f"REC_{c.candidate_id}",
                decision_type=c.decision_type,
                severity=severity,
                score=c.score,
                explanation=explanation,
                candidate_action=c.affected_entities,
                expires_at_sim_time=c.generated_at_sim_time + 3,  # Valid for 3 sim minutes
                status="NEW",
                original_state_hash=snapshot.snapshot_hash if snapshot else "",
            )
            recs.append(rec)

        return recs
