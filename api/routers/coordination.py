"""
RAAH Coordination API Router
============================

Exposes endpoints for fleet coverage scoring, idle ambulance repositioning
recommendations, and operator execution/cancellation controls.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List

from api.dependencies import manager
from api.auth import AuthenticatedUser, Permission, require_permission
from api.schemas.coordination import (
    CoverageSummaryResponse,
    ZoneCoverageResponse,
    RepositionAdvisoryResponse,
    RepositionExecuteRequest,
    RepositionResponse,
    HospitalProjectionResponse,
    MCIDeclareRequest,
    MCIDeclareResponse,
    MCIEventResponse,
    MCIChildSummary,
)

router = APIRouter(
    prefix="/coordination",
    tags=["Coordination"],
)


@router.get(
    "/coverage",
    response_model=CoverageSummaryResponse,
    summary="Get citywide operational zone coverage",
)
def get_coverage():
    """
    Return coverage ratios, available units, and deficit/surplus classifications
    across all 6 strategic Jaipur emergency sectors.
    """
    with manager.lock:
        sim = manager.simulator
        coverage_data = sim.coordinator.get_coverage(sim.state.ambulances)
        sim_time = sim.state.current_time

    deficit_cnt = sum(1 for z in coverage_data.values() if z["status"] == "DEFICIT")
    surplus_cnt = sum(1 for z in coverage_data.values() if z["status"] == "SURPLUS")

    zones_typed = {
        zid: ZoneCoverageResponse(**zdata)
        for zid, zdata in coverage_data.items()
    }

    return CoverageSummaryResponse(
        sim_time=sim_time,
        zones=zones_typed,
        deficit_count=deficit_cnt,
        surplus_count=surplus_cnt,
    )


@router.get(
    "/reposition/recommendations",
    response_model=List[RepositionAdvisoryResponse],
    summary="Get advisory reposition recommendations",
)
def get_reposition_recommendations():
    """
    Return active surplus-to-deficit idle ambulance repositioning recommendations (DATA ONLY).
    """
    with manager.lock:
        sim = manager.simulator
        recs = sim.coordinator.get_reposition_recommendations(sim.state.ambulances)

    return [RepositionAdvisoryResponse(**rec) for rec in recs]


@router.post(
    "/reposition/execute",
    response_model=RepositionResponse,
    summary="Execute an approved ambulance repositioning movement",
)
def execute_reposition(
    req: RepositionExecuteRequest,
    user: AuthenticatedUser = Depends(require_permission(Permission.APPROVE_FLEET_REPOSITION)),
):
    """
    Initiate an ambulance repositioning movement toward a staging post in a deficit zone.
    Validates availability, ensures source zone coverage protection, generates
    an M8 kinematic route, and sets vehicle status to REPOSITIONING.
    """
    with manager.lock:
        sim = manager.simulator
        try:
            res = sim.execute_reposition(
                ambulance_id=req.ambulance_id,
                target_lat=req.target_lat,
                target_lon=req.target_lon,
                reason=req.reason or f"COVERAGE_DEFICIT (approved by {user.username})",
            )
        except KeyError as err:
            raise HTTPException(status_code=404, detail=str(err))
        except ValueError as err:
            detail_msg = str(err)
            if "Source zone" in detail_msg or "cannot reposition" in detail_msg or "not AVAILABLE" in detail_msg:
                raise HTTPException(status_code=409, detail=detail_msg)
            raise HTTPException(status_code=400, detail=detail_msg)

    return RepositionResponse(
        status="REPOSITIONING",
        ambulance_id=res["ambulance_id"],
        origin_zone=res["origin_zone"],
        target_zone=res["target_zone"],
        target_coords=res["target_coords"],
        route_distance_km=res["route_distance_km"],
        eta_minutes=res["eta_minutes"],
        route_waypoints=res["route_waypoints"],
        message="Repositioning movement started successfully.",
    )


@router.post(
    "/reposition/cancel/{ambulance_id}",
    response_model=RepositionResponse,
    summary="Cancel active ambulance repositioning",
)
def cancel_reposition(
    ambulance_id: str,
    user: AuthenticatedUser = Depends(require_permission(Permission.APPROVE_FLEET_REPOSITION)),
):
    """
    Halt an actively repositioning ambulance, remove its route, and restore its status to AVAILABLE.
    """
    with manager.lock:
        sim = manager.simulator
        try:
            res = sim.cancel_reposition(ambulance_id=ambulance_id, reason=f"CANCELLED_BY_OPERATOR ({user.username})")
        except KeyError as err:
            raise HTTPException(status_code=404, detail=str(err))
        except ValueError as err:
            raise HTTPException(status_code=409, detail=str(err))

    return RepositionResponse(
        status="AVAILABLE",
        ambulance_id=res["ambulance_id"],
        message="Repositioning cancelled; ambulance restored to AVAILABLE at current position.",
    )


@router.get(
    "/hospital-projections",
    response_model=List[HospitalProjectionResponse],
    summary="Get projected hospital capacity and in-flight load metrics",
)
def get_hospital_projections():
    """
    Return projected remaining capacity, in-flight reservations (general & ICU),
    and utilization metrics across all hospitals.
    """
    with manager.lock:
        sim = manager.simulator
        projections = sim.coordinator.get_hospital_projections(sim.state.hospitals)

    return [HospitalProjectionResponse(**proj) for proj in projections.values()]


# ------------------------------------------------------------------
# MULTI-CASUALTY INCIDENTS (MCI)
# ------------------------------------------------------------------

@router.post(
    "/mci/declare",
    response_model=MCIDeclareResponse,
    summary="Declare a Multi-Casualty Incident and trigger coordinated triage & dispatch",
)
def declare_mci(
    request: MCIDeclareRequest,
    user: AuthenticatedUser = Depends(require_permission(Permission.MCI_CONTROL)),
):
    """
    Declare a major emergency scene, generate child casualties, run individual ML triage,
    and execute atomic multi-ambulance and balanced-hospital allocation.
    """
    with manager.lock:
        sim = manager.simulator
        try:
            res = sim.declare_mci(
                mci_id=request.mci_id,
                name=request.name or "Multi-Casualty Incident",
                latitude=request.latitude,
                longitude=request.longitude,
                estimated_casualties=request.estimated_casualties,
                primary_condition=request.primary_condition or "Trauma",
                description=request.description or "",
                notes=request.notes or "",
                casualties=request.casualties,
            )
        except Exception as err:
            raise HTTPException(status_code=400, detail=f"MCI declaration failed: {err}")

    return MCIDeclareResponse(
        status="MCI_DECLARED",
        mci=MCIEventResponse(**res["mci"]),
        child_incidents=[MCIChildSummary(**c) for c in res["child_incidents"]],
        dispatched_count=res["dispatched_count"],
        waiting_count=res["waiting_count"],
        message=f"MCI '{res['mci']['name']}' declared: {res['dispatched_count']} dispatched, {res['waiting_count']} waiting.",
    )


@router.get(
    "/mci/active",
    response_model=List[MCIEventResponse],
    summary="List all currently active Multi-Casualty Incidents",
)
def get_active_mcis():
    """
    Return all non-resolved MCIs with live casualty counts, assigned ambulances,
    and evacuation progress.
    """
    with manager.lock:
        sim = manager.simulator
        active_list = sim.coordinator.get_active_mcis()

    return [MCIEventResponse(**m) for m in active_list]


@router.get(
    "/mci/{mci_id}",
    response_model=MCIEventResponse,
    summary="Get details of a specific Multi-Casualty Incident",
)
def get_mci_detail(mci_id: str):
    """
    Fetch comprehensive status, child incident IDs, hospital distribution, and priority breakdown.
    """
    with manager.lock:
        sim = manager.simulator
        mci_dict = sim.coordinator.get_mci(mci_id)

    if not mci_dict:
        raise HTTPException(status_code=404, detail=f"MCI with ID '{mci_id}' not found.")

    return MCIEventResponse(**mci_dict)


