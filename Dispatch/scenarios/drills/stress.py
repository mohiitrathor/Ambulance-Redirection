"""
RAAH Disaster Drill & Stress Testing Engine (M10 Phase 2)
=========================================================

Executes curated disaster drills and parameterized casualty surge stress tests
using the deterministic ScenarioRunner. Computes operational performance metrics,
evaluates resilience scores, calculates canonical deterministic hashes, and stores
portable drill results atomically under data/drills/.
"""

import json
import hashlib
import time
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any

from Dispatch.scenarios.models import ScenarioDefinition, ReplayArtifact
from Dispatch.scenarios.runner import ScenarioRunner
from .library import DrillLibrary
from .metrics import DrillMetricsCalculator, ResilienceScore
from .generators import generate_casualty_surge

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DRILLS_DIR = ROOT / "data" / "drills"


def _atomic_write_json(file_path: Path, data: Dict[str, Any]):
    """Atomically write a JSON file via a temporary file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, file_path)


def compute_deterministic_hash(replay: ReplayArtifact) -> str:
    """
    Computes a canonical SHA-256 hash of the normalized operational event stream.
    Strictly excludes nondeterministic fields (wall-clock timestamps, run_ids, memory addresses).
    Guarantees that identical scenario execution produces identical hashes.
    """
    normalized_events = []
    for ev in replay.events:
        # Strip transient / non-deterministic properties
        clean_entities = {k: v for k, v in sorted(ev.get("entity_ids", {}).items()) if k != "run_id"}
        clean_payload = {k: v for k, v in sorted(ev.get("payload", {}).items()) if k not in ("timestamp", "created_at")}

        normalized_events.append({
            "sim_time": ev.get("sim_time", 0),
            "event_type": ev.get("event_type", ""),
            "entity_ids": clean_entities,
            "payload": clean_payload,
        })

    canonical_json = json.dumps(normalized_events, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:24]


@dataclass
class StressRunResult:
    """Unified telemetry and resilience scorecard for a disaster drill or stress test."""
    scenario_id: str
    run_id: str
    drill_name: Optional[str]
    seed: int
    casualty_count: int
    total_simulation_minutes: int
    incidents_created: int
    incidents_dispatched: int
    incidents_waiting: int
    incidents_arrived: int
    ambulance_utilization: float
    hospital_saturation_events: int
    icu_saturation_events: int
    max_concurrent_en_route: int
    max_concurrent_mci: int
    average_response_eta: float
    average_transport_eta: float
    unresolved_incidents: int
    unresolved_mcis: int
    simulation_runtime_ms: float
    deterministic_hash: str
    metrics: Dict[str, Any]
    resilience_score: Dict[str, Any]
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StressRunResult":
        return cls(**data)


class DrillResultStore:
    """Atomically persists and retrieves StressRunResult artifacts under data/drills/."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.dir = Path(storage_dir or DEFAULT_DRILLS_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, result: StressRunResult) -> str:
        rid = str(result.run_id)
        path = self.dir / f"{rid}.json"
        _atomic_write_json(path, result.to_dict())
        return rid

    def get(self, run_id: str) -> Optional[StressRunResult]:
        path = self.dir / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return StressRunResult.from_dict(data)
        except Exception:
            return None

    def list_results(self) -> List[Dict[str, Any]]:
        results = []
        for p in self.dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append({
                    "run_id": data.get("run_id"),
                    "scenario_id": data.get("scenario_id"),
                    "drill_name": data.get("drill_name"),
                    "casualty_count": data.get("casualty_count"),
                    "resilience_score": data.get("resilience_score", {}).get("overall", 0.0),
                    "deterministic_hash": data.get("deterministic_hash"),
                    "created_at": data.get("created_at"),
                })
            except Exception:
                continue
        results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return results


def run_stress_scenario(
    scenario: ScenarioDefinition,
    run_id: Optional[str] = None,
    drill_name: Optional[str] = None,
) -> StressRunResult:
    """
    Executes a ScenarioDefinition deterministically using ScenarioRunner,
    evaluates full performance telemetry, and calculates the resilience scorecard.
    """
    t_start = time.perf_counter()
    rid = run_id or f"drill_{scenario.scenario_id}_{int(time.time()*1000)}"

    runner = ScenarioRunner(seed=scenario.config.deterministic_seed)
    replay = runner.run(scenario, run_id=rid)

    t_end = time.perf_counter()
    duration_ms = round((t_end - t_start) * 1000.0, 2)

    # Calculate metrics
    computed_metrics = DrillMetricsCalculator.compute(replay)
    f_metrics = computed_metrics["fleet_metrics"]
    i_metrics = computed_metrics["incident_metrics"]
    h_metrics = computed_metrics["hospital_metrics"]
    m_metrics = computed_metrics["mci_metrics"]
    r_score = computed_metrics["resilience_score"]

    det_hash = compute_deterministic_hash(replay)

    cas_count = scenario.metadata.get("casualty_count", i_metrics["total_casualties"])

    result = StressRunResult(
        scenario_id=scenario.scenario_id,
        run_id=rid,
        drill_name=drill_name or scenario.metadata.get("drill_type"),
        seed=scenario.config.deterministic_seed,
        casualty_count=cas_count,
        total_simulation_minutes=scenario.config.duration_minutes,
        incidents_created=i_metrics["total_casualties"],
        incidents_dispatched=i_metrics["dispatched_casualties"],
        incidents_waiting=i_metrics["waiting_casualties"],
        incidents_arrived=i_metrics["arrived_casualties"],
        ambulance_utilization=f_metrics["utilization_ratio_pct"],
        hospital_saturation_events=h_metrics["hospitals_reaching_full_count"],
        icu_saturation_events=h_metrics["hospitals_reaching_icu_full_count"],
        max_concurrent_en_route=f_metrics["peak_en_route"],
        max_concurrent_mci=m_metrics["peak_concurrent_mcis"],
        average_response_eta=f_metrics["average_dispatch_eta_minutes"],
        average_transport_eta=i_metrics["average_transport_eta"],
        unresolved_incidents=i_metrics["unresolved_casualties"],
        unresolved_mcis=m_metrics["unresolved_mci_casualties"],
        simulation_runtime_ms=duration_ms,
        deterministic_hash=det_hash,
        metrics=computed_metrics,
        resilience_score=r_score,
        created_at=replay.run_metadata.created_at,
    )

    # Persist drill result
    store = DrillResultStore()
    store.save(result)

    return result


def run_drill(drill_name: str, seed: int = 42, **kwargs) -> StressRunResult:
    """Instantiate and execute a named drill from DrillLibrary."""
    scenario = DrillLibrary.generate(drill_name, seed=seed, **kwargs)
    return run_stress_scenario(scenario, drill_name=drill_name)


def run_casualty_surge(casualty_count: int, seed: int = 42, **kwargs) -> StressRunResult:
    """Run a parameterized casualty surge stress test."""
    scenario = generate_casualty_surge(casualty_count=casualty_count, seed=seed, **kwargs)
    return run_stress_scenario(scenario, drill_name="CASUALTY_SURGE")


def run_comparison(
    casualty_counts: Optional[List[int]] = None,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    Executes multiple independent casualty surge scenarios and produces
    comparative resilience and throughput evaluation rows.
    """
    counts = casualty_counts or [25, 50, 100]
    rows = []

    for count in counts:
        res = run_casualty_surge(casualty_count=count, seed=seed)
        rows.append({
            "scenario": f"Casualty Surge ({count})",
            "casualties": count,
            "dispatch_success_pct": res.metrics["fleet_metrics"]["dispatch_success_ratio_pct"],
            "avg_eta_minutes": res.average_response_eta,
            "unresolved_count": res.unresolved_incidents,
            "hospital_saturation_count": res.hospital_saturation_events,
            "resilience_score": res.resilience_score["overall"],
            "runtime_ms": res.simulation_runtime_ms,
            "deterministic_hash": res.deterministic_hash,
            "run_id": res.run_id,
        })

    return rows
