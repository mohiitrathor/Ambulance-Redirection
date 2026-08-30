"""
RAAH Historical Analytics API Router
====================================

Serves analytical summaries, run records, and audit logs queried from SQLite.
Authoritative live operational queries continue to hit /state/* and RAM.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query

from api.dependencies import manager
from api.persistence import queries
from api.schemas.analytics import (
    RunRecord,
    RunSummary,
    AnalyticsIncident,
    AnalyticsDecision,
    AnalyticsEvent,
)

router = APIRouter()


def _resolve_run_id(requested_run_id: Optional[int]) -> int:
    """Return requested run_id or fallback to current active run ID."""
    if requested_run_id is not None:
        return int(requested_run_id)

    active_id = manager.active_run_id
    if active_id is not None:
        return active_id

    # Fallback to the latest run in SQLite if active_id is unset
    runs = queries.list_runs()
    if runs:
        return runs[0]["run_id"]

    raise HTTPException(
        status_code=404,
        detail="No simulation runs found in historical database.",
    )


@router.get(
    "/runs",
    response_model=List[RunRecord],
    summary="List all simulation runs",
    description="Returns all historical simulation sessions with overall incident and redirection counts.",
)
def get_runs():
    try:
        raw_runs = queries.list_runs()
        return [RunRecord(**r) for r in raw_runs]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to query simulation runs: {exc}")


@router.get(
    "/summary",
    response_model=RunSummary,
    summary="Analytical KPI summary",
    description="Returns aggregate KPI scorecard (counts, priority/severity distribution, average ETA, redirection rate) for a run.",
)
def get_summary(
    run_id: Optional[int] = Query(
        None,
        description="Target simulation run ID. Defaults to current active run.",
    ),
):
    target_id = _resolve_run_id(run_id)
    summary = queries.get_run_summary(target_id)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"Simulation run #{target_id} not found.",
        )
    return RunSummary(**summary)


@router.get(
    "/incidents",
    response_model=List[AnalyticsIncident],
    summary="Historical incident log",
    description="Returns paginated incident dispatches and final outcomes for a simulation run.",
)
def get_incidents(
    run_id: Optional[int] = Query(
        None,
        description="Target simulation run ID. Defaults to current active run.",
    ),
    limit: int = Query(50, ge=1, le=500, description="Page limit."),
    offset: int = Query(0, ge=0, description="Page offset."),
):
    target_id = _resolve_run_id(run_id)
    rows = queries.get_incidents(target_id, limit=limit, offset=offset)
    return [AnalyticsIncident(**r) for r in rows]


@router.get(
    "/decisions",
    response_model=List[AnalyticsDecision],
    summary="Historical redirection decisions",
    description="Returns all redirection decisions (AI autonomous and Operator manual) logged for a simulation run.",
)
def get_decisions(
    run_id: Optional[int] = Query(
        None,
        description="Target simulation run ID. Defaults to current active run.",
    ),
):
    target_id = _resolve_run_id(run_id)
    rows = queries.get_decisions(target_id)
    return [AnalyticsDecision(**r) for r in rows]


@router.get(
    "/events",
    response_model=List[AnalyticsEvent],
    summary="Historical simulation event timeline",
    description="Returns chronological discrete operational events logged for a simulation run.",
)
def get_events(
    run_id: Optional[int] = Query(
        None,
        description="Target simulation run ID. Defaults to current active run.",
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum events to return."),
):
    target_id = _resolve_run_id(run_id)
    rows = queries.get_events(target_id, limit=limit)
    return [AnalyticsEvent(**r) for r in rows]
