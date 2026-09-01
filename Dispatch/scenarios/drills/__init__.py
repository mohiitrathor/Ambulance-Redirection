"""
RAAH Disaster Drills & Stress Testing Package (M10 Phase 2)
===========================================================

Exposes curated disaster drills, deterministic scenario generators,
resilience metrics, stress testing execution, and result persistence.
"""

from .library import DrillLibrary, DrillMetadata
from .generators import (
    generate_pileup_scenario,
    generate_dual_mci_scenario,
    generate_hospital_saturation_scenario,
    generate_casualty_surge,
)
from .metrics import DrillMetricsCalculator, ResilienceScore
from .stress import (
    StressRunResult,
    DrillResultStore,
    compute_deterministic_hash,
    run_stress_scenario,
    run_drill,
    run_casualty_surge,
    run_comparison,
)

__all__ = [
    "DrillLibrary",
    "DrillMetadata",
    "generate_pileup_scenario",
    "generate_dual_mci_scenario",
    "generate_hospital_saturation_scenario",
    "generate_casualty_surge",
    "DrillMetricsCalculator",
    "ResilienceScore",
    "StressRunResult",
    "DrillResultStore",
    "compute_deterministic_hash",
    "run_stress_scenario",
    "run_drill",
    "run_casualty_surge",
    "run_comparison",
]
