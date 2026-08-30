from pydantic import BaseModel
from typing import Any


# ==============================================================
# SCHEDULE EVENT REQUEST
# ==============================================================

class ScheduleEventRequest(BaseModel):
    """Request body for scheduling a new simulation event."""

    time: int
    event_type: str
    data: dict[str, Any] = {}


# ==============================================================
# EVENT RESPONSE
# ==============================================================

class EventResponse(BaseModel):
    """
    Event record matching the Event dataclass fields
    from events.py.
    """

    time: int
    sequence: int
    event_type: str
    data: dict[str, Any]
    processed: bool
