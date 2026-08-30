from fastapi import APIRouter

from api.dependencies import manager
from api.schemas.events import (
    ScheduleEventRequest,
    EventResponse,
)


# ==============================================================
# ROUTER
# ==============================================================

router = APIRouter()


# ==============================================================
# GET /events/pending
# ==============================================================

@router.get(
    "/pending",
    response_model=list[EventResponse],
    summary="List pending events",
    description=(
        "Returns all scheduled events that have "
        "not yet been processed."
    ),
)
def get_pending_events():

    sim = manager.simulator
    lock = manager.lock

    with lock:

        pending = sim.events.get_pending_events()

        results = [
            EventResponse(
                time=event.time,
                sequence=event.sequence,
                event_type=event.event_type,
                data=event.data,
                processed=event.processed,
            )
            for event in pending
        ]

    return results


# ==============================================================
# POST /events
# ==============================================================

@router.post(
    "",
    response_model=EventResponse,
    summary="Schedule a new event",
    description=(
        "Schedule a simulation event at a specific "
        "timestamp. The event will be processed when "
        "simulation time reaches or passes that timestamp."
    ),
)
def schedule_event(request: ScheduleEventRequest):

    sim = manager.simulator
    lock = manager.lock

    with lock:

        event = sim.events.schedule(
            time=request.time,
            event_type=request.event_type,
            data=request.data,
        )

    return EventResponse(
        time=event.time,
        sequence=event.sequence,
        event_type=event.event_type,
        data=event.data,
        processed=event.processed,
    )
