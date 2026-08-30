from dataclasses import dataclass, field
from typing import Any, Callable


# ==============================================================
# EVENT
# ==============================================================

@dataclass(order=True)
class SimulationEvent:

    time: int

    event_type: str = field(
        compare=False
    )

    data: dict[str, Any] = field(
        default_factory=dict,
        compare=False,
    )


# ==============================================================
# EVENT ENGINE
# ==============================================================

class EventEngine:

    def __init__(self):

        self.events = []
        self.handlers = {}

    # ----------------------------------------------------------
    # HANDLERS
    # ----------------------------------------------------------

    def register_handler(
        self,
        event_type: str,
        handler: Callable,
    ):

        self.handlers[
            event_type
        ] = handler

    # ----------------------------------------------------------
    # SCHEDULE
    # ----------------------------------------------------------

    def schedule(
        self,
        time: int,
        event_type: str,
        data=None,
    ):

        event = SimulationEvent(
            time=int(time),
            event_type=str(event_type),
            data=data or {},
        )

        self.events.append(event)
        self.events.sort()

    # ----------------------------------------------------------
    # READY EVENTS
    # ----------------------------------------------------------

    def get_events_at(self, time: int):

        ready = []
        remaining = []

        for event in self.events:

            if event.time <= time:
                ready.append(event)

            else:
                remaining.append(event)

        self.events = remaining

        return ready

    # ----------------------------------------------------------
    # PROCESS
    # ----------------------------------------------------------

    def process(self, time: int):

        results = []

        for event in self.get_events_at(time):

            handler = self.handlers.get(
                event.event_type
            )

            if handler is None:

                results.append({
                    "event": event,
                    "handled": False,
                    "message": (
                        f"No handler registered "
                        f"for {event.event_type}"
                    ),
                })

                continue

            try:

                result = handler(
                    event.data
                )

                results.append({
                    "event": event,
                    "handled": True,
                    "result": result,
                })

            except Exception as error:

                results.append({
                    "event": event,
                    "handled": False,
                    "error": str(error),
                })

        return results

    # ----------------------------------------------------------
    # PENDING
    # ----------------------------------------------------------

    def pending_events(self):

        return list(self.events)