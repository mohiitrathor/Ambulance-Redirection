"""
RAAH Hospital Optimizer (M11 Phase 1)
=====================================

Analyzes hospital projected capacities, incoming in-flight reservation surges,
and ICU exhaustion risks. Produces explainable hospital diversion and load-balancing
recommendations without executing any live redirections.
"""

from typing import List, Dict, Any, Optional
from Dispatch.optimization.models import (
    OperationalSnapshot,
    OptimizationCandidate,
    DecisionExplanation,
    OptimizationRecommendation,
)
from Dispatch.optimization.scorer import DecisionScorer
from Dispatch.coordination.hospital_balancer import HospitalBalancer


class HospitalOptimizer:
    """Produces explainable candidate hospital diversion recommendations."""

    def __init__(self, scorer: Optional[DecisionScorer] = None):
        self.scorer = scorer or DecisionScorer()

    def generate_candidates(self, snapshot: OperationalSnapshot) -> List[OptimizationCandidate]:
        """
        Evaluate hospital projections and active en-route incidents to discover
        overburdened facilities and viable alternative diversion targets.
        """
        candidates: List[OptimizationCandidate] = []
        projections = snapshot.hospital_projected_capacities
        active_incidents = snapshot.active_incidents.get("active_incidents", [])

        # Identify hospitals under severe strain or imminent saturation
        strained_hospitals = {}
        viable_alternatives = []

        for hid, p in projections.items():
            proj_beds = p.get("projected_available_beds", 0)
            proj_icu = p.get("projected_available_icu", 0)
            incoming = p.get("incoming_count", 0)
            status = p.get("status", "AVAILABLE")

            if status in ("FULL", "CRITICAL_ICU", "NEAR_CAPACITY") or proj_beds <= 2 or incoming >= 4:
                strained_hospitals[hid] = p
            elif proj_beds >= 10 and status == "AVAILABLE":
                viable_alternatives.append((hid, p))

        # Sort alternatives by projected available beds descending
        viable_alternatives.sort(key=lambda item: item[1].get("projected_available_beds", 0), reverse=True)

        if not strained_hospitals:
            return []

        # Check active en-route incidents heading to strained hospitals
        for inc in active_incidents:
            h_curr_id = inc.get("hospital_id")
            if not h_curr_id or h_curr_id not in strained_hospitals:
                continue

            strained_p = strained_hospitals[h_curr_id]
            pri = inc.get("priority", "P3")
            aid = inc.get("ambulance_id")
            iid = inc.get("incident_id")

            # Check if viable alternative exists
            suitable_alt = None
            for alt_id, alt_p in viable_alternatives:
                if alt_id == h_curr_id:
                    continue
                # Constraint: Critical patients require available projected ICU
                if pri == "P1" and alt_p.get("projected_available_icu", 0) <= 0:
                    continue
                # Constraint: Must have positive projected beds
                if alt_p.get("projected_available_beds", 0) <= 0:
                    continue

                suitable_alt = (alt_id, alt_p)
                break

            if not suitable_alt:
                # No alternative found; record constraint rejection
                cand = OptimizationCandidate(
                    candidate_id=f"CAND_DIV_NOALT_{iid}",
                    decision_type="HOSPITAL_DIVERSION",
                    priority="HIGH",
                    affected_entities={
                        "incident_id": iid,
                        "ambulance_id": aid,
                        "current_hospital": h_curr_id,
                    },
                    target=h_curr_id,
                    expected_effect="Diversion rejected: no alternative facility has sufficient capacity.",
                    confidence=0.90,
                    score=0.10,
                    rationale=f"Hospital {h_curr_id} is strained, but all secondary centers lack required capacity.",
                    constraints=["NO_VIABLE_ALTERNATIVE_WITH_CAPACITY"],
                    generated_at_sim_time=snapshot.sim_time,
                    rejected=True,
                    rejection_reason="No alternative facility satisfies projected bed and ICU constraints.",
                )
                candidates.append(cand)
                continue

            alt_id, alt_p = suitable_alt
            cap_diff = alt_p.get("projected_available_beds", 0) - strained_p.get("projected_available_beds", 0)
            eta_diff = 2.5  # Estimated diversion circuity penalty in minutes

            score, breakdown, explanation = self.scorer.score_candidate(
                decision_type="HOSPITAL_DIVERSION",
                clinical_safety=0.98 if pri == "P1" else 0.90,
                fleet_coverage=0.50,
                hospital_capacity=min(1.0, 0.60 + cap_diff * 0.02),
                eta_impact=0.75,
                operational_risk=0.15,
            )

            cand = OptimizationCandidate(
                candidate_id=f"CAND_DIV_{aid}_{alt_id}",
                decision_type="HOSPITAL_DIVERSION",
                priority="HIGH" if strained_p.get("status") == "FULL" else "MEDIUM",
                affected_entities={
                    "incident_id": iid,
                    "ambulance_id": aid,
                    "priority": pri,
                    "current_hospital_id": h_curr_id,
                    "recommended_hospital_id": alt_id,
                    "current_projected_beds": strained_p.get("projected_available_beds", 0),
                    "target_projected_beds": alt_p.get("projected_available_beds", 0),
                    "capacity_difference": cap_diff,
                    "estimated_eta_delta_minutes": eta_diff,
                },
                target=alt_id,
                expected_effect=f"Divert transport from strained {h_curr_id} to {alt_id} (+{cap_diff} beds).",
                confidence=0.94,
                score=score,
                rationale=(
                    f"Current destination {h_curr_id} is at {strained_p.get('status')} "
                    f"({strained_p.get('projected_available_beds')} beds left, {strained_p.get('incoming_count')} incoming). "
                    f"Alternative {alt_id} has {alt_p.get('projected_available_beds')} available projected beds."
                ),
                constraints=[
                    "ALTERNATIVE_HAS_POSITIVE_PROJECTED_BEDS",
                    "ICU_PRESERVED_FOR_P1_TRAUMA",
                    "TRANSPORT_IS_EN_ROUTE",
                ],
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
            curr_h = ents.get("current_hospital_id")
            rec_h = ents.get("recommended_hospital_id")

            summary = f"Divert {ents.get('ambulance_id')} from {curr_h} to {rec_h}."
            reasons = [
                f"Current hospital {curr_h} has only {ents.get('current_projected_beds')} projected beds remaining under incoming surge.",
                f"Alternative center {rec_h} provides {ents.get('target_projected_beds')} projected beds (+{ents.get('capacity_difference')} buffer).",
                c.expected_effect,
            ]
            risks = [
                f"Slight ETA increase of ~{ents.get('estimated_eta_delta_minutes', 2.0):.1f}m for transport unit.",
            ]
            benefit = f"Eliminates emergency room offload saturation risk at {curr_h} and secures immediate bed admission."

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

            severity = "CRITICAL" if c.priority == "HIGH" else "WARNING"

            rec = OptimizationRecommendation(
                recommendation_id=f"REC_{c.candidate_id}",
                decision_type=c.decision_type,
                severity=severity,
                score=c.score,
                explanation=explanation,
                candidate_action=c.affected_entities,
                expires_at_sim_time=c.generated_at_sim_time + 2,  # Valid for 2 sim minutes
                status="NEW",
                original_state_hash=snapshot.snapshot_hash if snapshot else "",
            )
            recs.append(rec)

        return recs
