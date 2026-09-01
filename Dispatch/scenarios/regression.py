"""
RAAH Continuous Regression Drill Engine & Baseline Manager (M10 Phase 4)
========================================================================

Executes standardized disaster drill suites against established operational baselines.
Evaluates tolerance thresholds (ETA regression, resilience drop, unresolved casualties,
dispatch success drop), tracks candidate vs baseline versions, and produces deterministic
regression reports.

STRICT INVARIANTS:
- Does NOT mutate live manager.simulator or live DispatchState.
- Operates on isolated ScenarioRunner instances.
- Reuses curated drills from Dispatch.scenarios.drills.library without code duplication.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
import os
import subprocess
from datetime import datetime, timezone

from Dispatch.scenarios.runner import ScenarioRunner
from Dispatch.scenarios.models import ReplayArtifact
from Dispatch.scenarios.analysis import ReplayAnalyzer
from Dispatch.scenarios.drills.library import DrillLibrary
from Dispatch.scenarios.drills.generators import (
    generate_pileup_scenario,
    generate_dual_mci_scenario,
    generate_hospital_saturation_scenario,
    generate_casualty_surge,
)
from Dispatch.scenarios.drills.stress import compute_deterministic_hash


@dataclass
class RegressionTolerances:
    """Configurable tolerance thresholds for regression evaluation."""
    max_eta_regression_pct: float = 10.0      # max allowable % increase in average ETA
    max_resilience_drop: float = 2.0         # max allowable drop in resilience score points
    max_unresolved_increase: int = 0         # max allowable increase in unresolved casualties
    max_dispatch_success_drop_pct: float = 2.0  # max allowable % drop in dispatch success ratio


@dataclass
class RegressionCase:
    """Definition of a standard regression test case."""
    case_id: str
    scenario_id: str
    seed: int = 42
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegressionResult:
    """Evaluation result for an individual regression case."""
    case_id: str
    scenario_id: str
    seed: int
    status: str                         # "PASS", "WARN", "FAIL"
    baseline_resilience: float
    current_resilience: float
    delta_resilience: float
    baseline_eta: float
    current_eta: float
    delta_eta: float
    baseline_dispatch_success_pct: float
    current_dispatch_success_pct: float
    delta_dispatch_success_pct: float
    baseline_unresolved: int
    current_unresolved: int
    delta_unresolved: int
    deterministic_hash: str
    baseline_hash: Optional[str] = None
    hash_matched: bool = True
    violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegressionReport:
    """Suite-level regression report comparing candidate to baseline."""
    run_id: str
    baseline_version: str
    candidate_version: str
    started_at: str
    completed_at: str
    total_cases: int
    passed_cases: int
    warned_cases: int
    failed_cases: int
    overall_status: str                 # "PASS", "WARN", "FAIL"
    cases: List[RegressionResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "baseline_version": self.baseline_version,
            "candidate_version": self.candidate_version,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "warned_cases": self.warned_cases,
            "failed_cases": self.failed_cases,
            "overall_status": self.overall_status,
            "cases": [c.to_dict() for c in self.cases],
        }


_REPO_ROOT = Path(__file__).resolve().parents[2]


class RegressionStore:
    """Manages persistence of regression baselines and run results."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or (_REPO_ROOT / "data" / "regression"))
        self.runs_dir = self.base_dir / "runs"
        self.baseline_file = self.base_dir / "baseline.json"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def get_baseline(self) -> Optional[Dict[str, Any]]:
        """Retrieve stored baseline if present."""
        if not self.baseline_file.exists():
            return None
        try:
            return json.loads(self.baseline_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_baseline(self, baseline_data: Dict[str, Any]) -> None:
        """Explicitly write or update the official regression baseline."""
        self.baseline_file.write_text(json.dumps(baseline_data, indent=2), encoding="utf-8")

    def save_run(self, report: RegressionReport) -> None:
        """Persist a regression run report."""
        target = self.runs_dir / f"{report.run_id}.json"
        target.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    def list_runs(self) -> List[Dict[str, Any]]:
        """List historical regression run summaries."""
        results = []
        for p in sorted(self.runs_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                results.append({
                    "run_id": data.get("run_id"),
                    "completed_at": data.get("completed_at"),
                    "overall_status": data.get("overall_status"),
                    "total_cases": data.get("total_cases"),
                    "passed_cases": data.get("passed_cases"),
                    "failed_cases": data.get("failed_cases"),
                })
            except Exception:
                continue
        return results

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        target = self.runs_dir / f"{run_id}.json"
        if not target.exists():
            return None
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return None


class RegressionSuite:
    """Executes the standard disaster drill regression catalog."""

    STANDARD_CASES: List[RegressionCase] = [
        RegressionCase(case_id="REG_PILEUP", scenario_id="NH48_MULTI_VEHICLE_PILEUP", seed=42),
        RegressionCase(case_id="REG_EARTHQUAKE", scenario_id="DUAL_MCI_EARTHQUAKE", seed=42),
        RegressionCase(case_id="REG_SATURATION", scenario_id="CITYWIDE_HOSPITAL_SATURATION", seed=42),
        RegressionCase(case_id="REG_SURGE_25", scenario_id="CASUALTY_SURGE_25", seed=42, parameters={"casualty_count": 25}),
        RegressionCase(case_id="REG_SURGE_50", scenario_id="CASUALTY_SURGE_50", seed=42, parameters={"casualty_count": 50}),
        RegressionCase(case_id="REG_SURGE_100", scenario_id="CASUALTY_SURGE_100", seed=42, parameters={"casualty_count": 100}),
    ]

    def __init__(self, tolerances: Optional[RegressionTolerances] = None, store: Optional[RegressionStore] = None):
        self.tolerances = tolerances or RegressionTolerances()
        self.store = store or RegressionStore()

    @staticmethod
    def get_repository_version() -> str:
        """Retrieve git commit SHA or fallback gracefully."""
        try:
            out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL)
            return out.decode("utf-8").strip()
        except Exception:
            return "unknown_commit"

    def execute_case(self, case: RegressionCase) -> ReplayArtifact:
        """Generate and execute a scenario using an isolated ScenarioRunner."""
        sid = case.scenario_id
        seed = case.seed

        if sid == "NH48_MULTI_VEHICLE_PILEUP":
            scen = generate_pileup_scenario(seed=seed, duration_minutes=10)
        elif sid == "DUAL_MCI_EARTHQUAKE":
            scen = generate_dual_mci_scenario(seed=seed, duration_minutes=10)
        elif sid == "CITYWIDE_HOSPITAL_SATURATION":
            scen = generate_hospital_saturation_scenario(seed=seed, duration_minutes=10)
        elif sid.startswith("CASUALTY_SURGE"):
            count = case.parameters.get("casualty_count", 25)
            scen = generate_casualty_surge(casualty_count=count, seed=seed, duration_minutes=10)
        else:
            scen = generate_casualty_surge(casualty_count=20, seed=seed, duration_minutes=10)

        runner = ScenarioRunner(seed=seed)
        run_id = f"reg_{case.case_id.lower()}_{seed}_{int(datetime.now().timestamp())}"
        artifact = runner.run(scen, run_id=run_id)
        return artifact

    def run_suite(self, run_id: Optional[str] = None) -> RegressionReport:
        """Run all standard regression cases and evaluate against baseline."""
        run_id = run_id or f"reg_suite_{int(datetime.now().timestamp())}"
        start_time = datetime.now(timezone.utc).isoformat()
        baseline_data = self.store.get_baseline() or {}
        baseline_version = baseline_data.get("version", "initial_baseline")
        candidate_version = self.get_repository_version()

        case_results: List[RegressionResult] = []

        for case in self.STANDARD_CASES:
            artifact = self.execute_case(case)
            analysis = ReplayAnalyzer.analyze(artifact)

            det_hash = analysis.deterministic_hash
            r_score = analysis.resilience_score.get("overall", 100.0)
            avg_eta = analysis.fleet_metrics.get("average_dispatch_eta_minutes", 0.0)
            disp_success = analysis.fleet_metrics.get("dispatch_success_ratio_pct", 100.0)
            unresolved = analysis.unresolved_incidents + analysis.unresolved_mcis

            # Baseline lookup
            b_case = baseline_data.get("cases", {}).get(case.case_id, {})
            b_resilience = b_case.get("resilience_score", r_score)
            b_eta = b_case.get("average_eta_minutes", avg_eta)
            b_disp_success = b_case.get("dispatch_success_pct", disp_success)
            b_unresolved = b_case.get("unresolved_casualties", unresolved)
            b_hash = b_case.get("deterministic_hash")

            delta_r = round(r_score - b_resilience, 2)
            delta_eta = round(avg_eta - b_eta, 2)
            delta_disp = round(disp_success - b_disp_success, 2)
            delta_unres = unresolved - b_unresolved

            violations = []
            status = "PASS"

            # Check 1: Resilience drop
            if delta_r < -self.tolerances.max_resilience_drop:
                violations.append(f"Resilience score dropped by {-delta_r:.2f} (allowed: -{self.tolerances.max_resilience_drop})")
                status = "FAIL"

            # Check 2: Unresolved increase
            if delta_unres > self.tolerances.max_unresolved_increase:
                violations.append(f"Unresolved casualties increased by +{delta_unres} (allowed: 0)")
                status = "FAIL"

            # Check 3: Dispatch success drop
            if delta_disp < -self.tolerances.max_dispatch_success_drop_pct:
                violations.append(f"Dispatch success dropped by {-delta_disp:.2f}% (allowed: -{self.tolerances.max_dispatch_success_drop_pct}%)")
                status = "FAIL"

            # Check 4: ETA regression (Warning or Fail)
            if b_eta > 0 and ((avg_eta - b_eta) / b_eta) * 100.0 > self.tolerances.max_eta_regression_pct:
                violations.append(f"Average ETA rose from {b_eta:.2f}m to {avg_eta:.2f}m (> {self.tolerances.max_eta_regression_pct}% regression)")
                if status != "FAIL":
                    status = "WARN"

            hash_matched = (b_hash is None) or (b_hash == det_hash)

            case_results.append(RegressionResult(
                case_id=case.case_id,
                scenario_id=case.scenario_id,
                seed=case.seed,
                status=status,
                baseline_resilience=b_resilience,
                current_resilience=r_score,
                delta_resilience=delta_r,
                baseline_eta=b_eta,
                current_eta=avg_eta,
                delta_eta=delta_eta,
                baseline_dispatch_success_pct=b_disp_success,
                current_dispatch_success_pct=disp_success,
                delta_dispatch_success_pct=delta_disp,
                baseline_unresolved=b_unresolved,
                current_unresolved=unresolved,
                delta_unresolved=delta_unres,
                deterministic_hash=det_hash,
                baseline_hash=b_hash,
                hash_matched=hash_matched,
                violations=violations,
            ))

        passed = sum(1 for c in case_results if c.status == "PASS")
        warned = sum(1 for c in case_results if c.status == "WARN")
        failed = sum(1 for c in case_results if c.status == "FAIL")

        overall = "FAIL" if failed > 0 else ("WARN" if warned > 0 else "PASS")
        report = RegressionReport(
            run_id=run_id,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
            started_at=start_time,
            completed_at=datetime.now(timezone.utc).isoformat(),
            total_cases=len(case_results),
            passed_cases=passed,
            warned_cases=warned,
            failed_cases=failed,
            overall_status=overall,
            cases=case_results,
        )

        self.store.save_run(report)
        return report

    def create_baseline(self, description: str = "Standard Regression Baseline") -> Dict[str, Any]:
        """Execute all standard cases and establish them as the official baseline."""
        version = self.get_repository_version()
        created_at = datetime.now(timezone.utc).isoformat()
        cases_dict: Dict[str, Any] = {}

        for case in self.STANDARD_CASES:
            artifact = self.execute_case(case)
            analysis = ReplayAnalyzer.analyze(artifact)
            r_score = analysis.resilience_score.get("overall", 100.0)
            avg_eta = analysis.fleet_metrics.get("average_dispatch_eta_minutes", 0.0)
            disp_success = analysis.fleet_metrics.get("dispatch_success_ratio_pct", 100.0)
            unresolved = analysis.unresolved_incidents + analysis.unresolved_mcis

            cases_dict[case.case_id] = {
                "case_id": case.case_id,
                "scenario_id": case.scenario_id,
                "seed": case.seed,
                "resilience_score": round(r_score, 2),
                "average_eta_minutes": round(avg_eta, 2),
                "dispatch_success_pct": round(disp_success, 2),
                "unresolved_casualties": unresolved,
                "deterministic_hash": analysis.deterministic_hash,
            }

        baseline = {
            "version": version,
            "created_at": created_at,
            "description": description,
            "cases": cases_dict,
        }
        self.store.save_baseline(baseline)
        return baseline
