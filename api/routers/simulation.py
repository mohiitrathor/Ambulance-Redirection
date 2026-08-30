from fastapi import APIRouter, Query

from api.dependencies import manager
from simulation_output import SimulationOutput
from api.schemas.state import DashboardResponse


# ==============================================================
# ROUTER
# ==============================================================

router = APIRouter()


# ==============================================================
# POST /simulation/tick
# ==============================================================

@router.post(
    "/tick",
    response_model=DashboardResponse,
    summary="Advance simulation time",
    description=(
        "Advance the simulation clock by N minutes "
        "(default 1). Processes scheduled events and "
        "evaluates redirection for all active incidents."
    ),
)
def simulation_tick(
    minutes: int = Query(
        default=1,
        ge=1,
        le=60,
        description="Number of minutes to advance.",
    ),
):

    sim = manager.simulator
    lock = manager.lock

    with lock:

        sim.advance_time(minutes)
        sim.process_events()
        sim.check_redirections()

        data = SimulationOutput.dashboard_snapshot(
            sim.state
        )

    return data


# ==============================================================
# POST /simulation/reset
# ==============================================================

@router.post(
    "/reset",
    summary="Reset simulation",
    description=(
        "Destroy the current Simulator and create "
        "a fresh one with clean world state."
    ),
)
def simulation_reset():

    manager.reset()

    return {"status": "reset"}
