"""
RAAH Operational Drift Detection (M11 Phase 4)
==============================================

Detects system-level operational drift across key metrics:
- Average dispatch ETA
- Fleet zone coverage
- Hospital saturation
- Autonomous recommendation success rate
- Benefit realization ratio (predicted vs. actual)
- Unresolved casualty rate
- Recommendation volume
- Stale / expired recommendation rate

Classifies overall drift severity: NORMAL, WATCH, DEGRADED, CRITICAL.
Strictly observational; does NOT automatically alter core dispatch behavior.
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple


class DriftSeverity:
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


@dataclass
class OperationalDrift:
    """
    Quantitative measurement of divergence between historical baseline
    and current rolling operational window.
    """
    severity: str = DriftSeverity.NORMAL
    overall_drift_score: float = 0.0            # 0.0 (no drift) to 100.0 (extreme drift)
    eta_drift_pct: float = 0.0
    coverage_drift_pct: float = 0.0
    hospital_saturation_drift_pct: float = 0.0
    success_rate_drift_pct: float = 0.0
    benefit_realization_drift_pct: float = 0.0
    unresolved_casualty_drift_pct: float = 0.0
    volume_drift_pct: float = 0.0
    stale_rate_drift_pct: float = 0.0
    baseline_metrics: Dict[str, float] = field(default_factory=dict)
    current_metrics: Dict[str, float] = field(default_factory=dict)
    signals: List[str] = field(default_factory=list)
    deterministic_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DriftDetector:
    """
    Compares baseline window metrics against current window metrics
    to compute percentage drifts and classify operational stability.
    """

    # Default healthy baselines for Jaipur EMS network
    DEFAULT_BASELINE: Dict[str, float] = {
        "avg_eta_minutes": 6.5,
        "avg_coverage_score": 0.85,
        "hospital_saturation_pct": 25.0,
        "autonomous_success_rate": 0.95,
        "benefit_realization_ratio": 0.90,
        "unresolved_casualty_pct": 2.0,
        "recommendation_volume_per_10m": 4.0,
        "stale_rate_pct": 5.0,
    }

    def __init__(self, baseline: Optional[Dict[str, float]] = None):
        self.baseline = baseline or dict(self.DEFAULT_BASELINE)

    def detect_drift(
        self,
        current_metrics: Dict[str, float],
        custom_baseline: Optional[Dict[str, float]] = None,
    ) -> OperationalDrift:
        """
        Compute quantitative percentage drift for each operational indicator,
        synthesize signals, and classify overall severity.
        """
        base = custom_baseline or self.baseline
        signals: List[str] = []

        def calc_pct(current_val: float, base_val: float) -> float:
            if abs(base_val) < 1e-6:
                return 0.0 if abs(current_val) < 1e-6 else 100.0
            return round(((current_val - base_val) / base_val) * 100.0, 2)

        # 1. ETA Drift (+ is worse)
        curr_eta = current_metrics.get("avg_eta_minutes", base.get("avg_eta_minutes", 6.5))
        base_eta = base.get("avg_eta_minutes", 6.5)
        eta_drift = calc_pct(curr_eta, base_eta)
        if eta_drift >= 25.0:
            signals.append(f"Significant ETA degradation: +{eta_drift:.1f}% ({curr_eta:.1f}m vs baseline {base_eta:.1f}m)")

        # 2. Coverage Drift (- is worse)
        curr_cov = current_metrics.get("avg_coverage_score", base.get("avg_coverage_score", 0.85))
        base_cov = base.get("avg_coverage_score", 0.85)
        cov_drift = calc_pct(curr_cov, base_cov)
        if cov_drift <= -15.0:
            signals.append(f"Zone coverage deficit: {cov_drift:.1f}% ({curr_cov:.2f} vs {base_cov:.2f})")

        # 3. Hospital Saturation Drift (+ is worse)
        curr_sat = current_metrics.get("hospital_saturation_pct", base.get("hospital_saturation_pct", 25.0))
        base_sat = base.get("hospital_saturation_pct", 25.0)
        sat_drift = calc_pct(curr_sat, base_sat)
        if sat_drift >= 30.0:
            signals.append(f"Hospital network saturation surge: +{sat_drift:.1f}%")

        # 4. Autonomous Success Rate Drift (- is worse)
        curr_succ = current_metrics.get("autonomous_success_rate", base.get("autonomous_success_rate", 0.95))
        base_succ = base.get("autonomous_success_rate", 0.95)
        succ_drift = calc_pct(curr_succ, base_succ)
        if succ_drift <= -5.0:
            signals.append(f"Autonomous action success drop: {succ_drift:.1f}% ({curr_succ:.1%} vs {base_succ:.1%})")

        # 5. Benefit Realization Ratio (- is worse)
        curr_ratio = current_metrics.get("benefit_realization_ratio", base.get("benefit_realization_ratio", 0.90))
        base_ratio = base.get("benefit_realization_ratio", 0.90)
        ratio_drift = calc_pct(curr_ratio, base_ratio)
        if ratio_drift <= -20.0:
            signals.append(f"Benefit realization under-delivery: {ratio_drift:.1f}%")

        # 6. Unresolved Casualty Drift (+ is worse)
        curr_cas = current_metrics.get("unresolved_casualty_pct", base.get("unresolved_casualty_pct", 2.0))
        base_cas = base.get("unresolved_casualty_pct", 2.0)
        cas_drift = calc_pct(curr_cas, base_cas)
        if cas_drift >= 25.0:
            signals.append(f"Unresolved casualty backlog surge: +{cas_drift:.1f}%")

        # 7. Volume Drift (+ or - could indicate regime shift)
        curr_vol = current_metrics.get("recommendation_volume_per_10m", base.get("recommendation_volume_per_10m", 4.0))
        base_vol = base.get("recommendation_volume_per_10m", 4.0)
        vol_drift = calc_pct(curr_vol, base_vol)

        # 8. Stale Rate Drift (+ is worse)
        curr_stale = current_metrics.get("stale_rate_pct", base.get("stale_rate_pct", 5.0))
        base_stale = base.get("stale_rate_pct", 5.0)
        stale_drift = calc_pct(curr_stale, base_stale)
        if stale_drift >= 50.0:
            signals.append(f"Stale recommendation rate surge: +{stale_drift:.1f}%")

        # Compute overall drift score (0–100)
        # Weight critical signals: ETA, Coverage, Saturation, Success, Casualties
        drift_magnitude = (
            max(0.0, eta_drift) * 0.25 +
            max(0.0, -cov_drift) * 0.20 +
            max(0.0, sat_drift) * 0.15 +
            max(0.0, -succ_drift) * 0.20 +
            max(0.0, cas_drift) * 0.20
        )
        overall_score = round(min(100.0, max(0.0, drift_magnitude)), 2)

        # Classify Severity
        if overall_score >= 30.0 or eta_drift >= 30.0 or cas_drift >= 30.0 or succ_drift <= -12.0:
            severity = DriftSeverity.CRITICAL
        elif overall_score >= 18.0 or eta_drift >= 18.0 or succ_drift <= -8.0 or cov_drift <= -15.0:
            severity = DriftSeverity.DEGRADED
        elif overall_score >= 8.0 or len(signals) >= 1:
            severity = DriftSeverity.WATCH
        else:
            severity = DriftSeverity.NORMAL

        if not signals:
            signals.append("Operational indicators within nominal baseline bounds.")

        # Compute deterministic hash
        hash_payload = {
            "severity": severity,
            "overall_drift_score": overall_score,
            "eta_drift_pct": eta_drift,
            "coverage_drift_pct": cov_drift,
            "hospital_saturation_drift_pct": sat_drift,
            "success_rate_drift_pct": succ_drift,
            "unresolved_casualty_drift_pct": cas_drift,
        }
        encoded = json.dumps(hash_payload, sort_keys=True).encode("utf-8")
        det_hash = hashlib.sha256(encoded).hexdigest()[:24]

        return OperationalDrift(
            severity=severity,
            overall_drift_score=overall_score,
            eta_drift_pct=eta_drift,
            coverage_drift_pct=cov_drift,
            hospital_saturation_drift_pct=sat_drift,
            success_rate_drift_pct=succ_drift,
            benefit_realization_drift_pct=ratio_drift,
            unresolved_casualty_drift_pct=cas_drift,
            volume_drift_pct=vol_drift,
            stale_rate_drift_pct=stale_drift,
            baseline_metrics={k: round(v, 3) for k, v in base.items()},
            current_metrics={k: round(v, 3) for k, v in current_metrics.items()},
            signals=signals,
            deterministic_hash=det_hash,
        )
