"""
RAAH Decision Scorer (M11 Phase 1)
==================================

Explainable composite scoring model evaluating candidate decisions across
clinical safety, fleet coverage, hospital capacity, ETA efficiency, and operational risk.
"""

from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ScoringWeights:
    """Configurable weights for multi-objective optimization scoring."""
    clinical_safety: float = 0.30
    fleet_coverage: float = 0.25
    hospital_capacity: float = 0.20
    eta_impact: float = 0.15
    operational_risk: float = 0.10  # Penalty factor


class DecisionScorer:
    """Computes transparent, explainable composite scores for decision candidates."""

    def __init__(self, weights: Optional[ScoringWeights] = None):
        self.weights = weights or ScoringWeights()

    def score_candidate(
        self,
        decision_type: str,
        clinical_safety: float,
        fleet_coverage: float,
        hospital_capacity: float,
        eta_impact: float,
        operational_risk: float,
    ) -> Tuple[float, Dict[str, float], str]:
        """
        Compute normalized composite score [0.0, 1.0], breakdown dict, and human-readable explanation.
        """
        w = self.weights
        c_safety = max(0.0, min(1.0, float(clinical_safety)))
        c_cov = max(0.0, min(1.0, float(fleet_coverage)))
        c_hosp = max(0.0, min(1.0, float(hospital_capacity)))
        c_eta = max(0.0, min(1.0, float(eta_impact)))
        c_risk = max(0.0, min(1.0, float(operational_risk)))

        raw_score = (
            w.clinical_safety * c_safety
            + w.fleet_coverage * c_cov
            + w.hospital_capacity * c_hosp
            + w.eta_impact * c_eta
            - w.operational_risk * c_risk
        )

        final_score = round(max(0.0, min(1.0, raw_score)), 3)

        breakdown = {
            "clinical_safety": round(c_safety, 3),
            "fleet_coverage": round(c_cov, 3),
            "hospital_capacity": round(c_hosp, 3),
            "eta_impact": round(c_eta, 3),
            "operational_risk": round(c_risk, 3),
            "raw_composite": round(raw_score, 3),
            "final_score": final_score,
        }

        explanation = (
            f"Composite Score: {final_score:.2f} = "
            f"(Safety: {c_safety:.2f} × {w.clinical_safety}) + "
            f"(Coverage: {c_cov:.2f} × {w.fleet_coverage}) + "
            f"(Hospital: {c_hosp:.2f} × {w.hospital_capacity}) + "
            f"(ETA: {c_eta:.2f} × {w.eta_impact}) - "
            f"(Risk Penalty: {c_risk:.2f} × {w.operational_risk})"
        )

        return final_score, breakdown, explanation
