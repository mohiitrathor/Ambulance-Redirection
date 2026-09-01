"""
RAAH Disaster Drills & Stress Testing API Router (M10 Phase 2)
==============================================================

Provides endpoints to list curated disaster drills, execute deterministic
stress tests, perform comparative surge benchmarking, and inspect resilience results.
All drill runs execute against isolated Simulator instances and never mutate live state.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any

from Dispatch.scenarios.drills import (
    DrillLibrary,
    DrillResultStore,
    run_drill,
    run_casualty_surge,
    run_comparison,
)
from api.schemas.drills import (
    DrillInfoResponse,
    DrillRunRequest,
    StressRunRequest,
    ComparisonRunRequest,
    StressRunResponse,
    ComparisonRowResponse,
)

drill_store = DrillResultStore()

router = APIRouter(prefix="/drills", tags=["Disaster Drills & Stress Testing"])


@router.get(
    "",
    response_model=List[DrillInfoResponse],
    summary="List all available curated disaster drills",
)
def list_drills():
    drills = DrillLibrary.list_drills()
    return [DrillInfoResponse(**d) for d in drills]


@router.get(
    "/results",
    summary="List metadata for all executed drill & stress test runs",
)
def list_results():
    return drill_store.list_results()


@router.get(
    "/results/{run_id}",
    response_model=StressRunResponse,
    summary="Retrieve complete scorecard and telemetry for a specific drill run",
)
def get_drill_result(run_id: str):
    res = drill_store.get(run_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Drill result '{run_id}' not found.")
    return StressRunResponse(**res.to_dict())


@router.get(
    "/{drill_name}",
    response_model=DrillInfoResponse,
    summary="Get configuration details and default parameters for a drill",
)
def get_drill_info(drill_name: str):
    drill = DrillLibrary.get_drill(drill_name)
    if not drill:
        raise HTTPException(status_code=404, detail=f"Drill '{drill_name}' not found.")
    return DrillInfoResponse(**drill)


@router.post(
    "/run",
    response_model=StressRunResponse,
    summary="Execute a curated disaster drill deterministically",
)
def execute_drill(req: DrillRunRequest):
    drill = DrillLibrary.get_drill(req.drill_name)
    if not drill:
        raise HTTPException(status_code=404, detail=f"Drill '{req.drill_name}' not found.")

    params = req.parameters or {}
    result = run_drill(req.drill_name, seed=req.seed or 42, **params)
    return StressRunResponse(**result.to_dict())


@router.post(
    "/stress",
    response_model=StressRunResponse,
    summary="Execute a parameterized casualty surge stress test",
)
def execute_stress_test(req: StressRunRequest):
    result = run_casualty_surge(
        casualty_count=req.casualty_count,
        seed=req.seed or 42,
        mci_count=req.mci_count or 2,
        duration_minutes=req.duration_minutes or 15,
        hospital_surge=bool(req.hospital_surge),
    )
    return StressRunResponse(**result.to_dict())


@router.post(
    "/compare",
    response_model=List[ComparisonRowResponse],
    summary="Execute comparative casualty surge runs (e.g. 25 vs 50 vs 100 casualties)",
)
def execute_comparison(req: ComparisonRunRequest):
    counts = req.casualty_counts or [25, 50, 100]
    rows = run_comparison(casualty_counts=counts, seed=req.seed or 42)
    return [ComparisonRowResponse(**r) for r in rows]
