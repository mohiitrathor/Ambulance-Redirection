from fastapi import APIRouter, HTTPException, Query

from api.dependencies import manager
from simulation_output import SimulationOutput
from api.schemas.state import DashboardResponse
from api.schemas.simulation import (
    RealtimeStartRequest,
    RealtimeStatusResponse,
    RealtimeControlResponse,
)


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
    summary="Advance simulation time manually",
    description=(
        "Advance the simulation clock by N minutes (default 1). "
        "Only available when real-time simulation mode is STOPPED. "
        "Returns 409 Conflict if real-time mode is currently running."
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

    if manager.is_realtime_running:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot manually tick while real-time simulation "
                "is running. Stop real-time mode first."
            ),
        )

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
        "Safely stops any active real-time simulation thread, "
        "destroys the current Simulator, and creates a fresh "
        "instance with clean world state at time = 0."
    ),
)
def simulation_reset():

    manager.reset()

    return {
        "status": "reset",
        "time": 0,
    }


# ==============================================================
# POST /simulation/realtime/start
# ==============================================================

@router.post(
    "/realtime/start",
    response_model=RealtimeControlResponse,
    summary="Start real-time background simulation",
    description=(
        "Starts the background wall-clock simulation loop. "
        "Advances the simulation by minutes_per_tick every "
        "tick_interval_seconds. Returns 409 Conflict if already running."
    ),
)
def simulation_realtime_start(
    request: RealtimeStartRequest = RealtimeStartRequest(),
):

    try:

        result = manager.start_realtime(
            tick_interval_seconds=request.tick_interval_seconds,
            minutes_per_tick=request.minutes_per_tick,
        )

        return result

    except RuntimeError as error:

        raise HTTPException(
            status_code=409,
            detail=str(error),
        )


# ==============================================================
# POST /simulation/realtime/stop
# ==============================================================

@router.post(
    "/realtime/stop",
    response_model=RealtimeControlResponse,
    summary="Stop real-time background simulation",
    description=(
        "Stops the background real-time simulation loop cleanly. "
        "Waits for the background thread to finish its active tick. "
        "Idempotent: safe to call if already stopped."
    ),
)
def simulation_realtime_stop():

    return manager.stop_realtime()


# ==============================================================
# GET /simulation/realtime/status
# ==============================================================

@router.get(
    "/realtime/status",
    response_model=RealtimeStatusResponse,
    summary="Get real-time simulation status",
    description=(
        "Returns telemetry for the background real-time simulation "
        "including running status, tick rate, speed multiplier, "
        "processed ticks, and error state."
    ),
)
def simulation_realtime_status():

    return manager.get_realtime_status()
