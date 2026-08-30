from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ==============================================================
# EVENT
# ==============================================================

@dataclass(order=True)
class Event:
    time: int
    sequence: int
    event_type: str = field(compare=False)
    data: Dict[str, Any] = field(
        default_factory=dict,
        compare=False,
    )
    processed: bool = field(
        default=False,
        compare=False,
    )


# ==============================================================
# EVENT ENGINE
# ==============================================================

class EventEngine:

    def __init__(self):

        self.events: List[Event] = []

        self.handlers: Dict[
            str,
            Callable[[Dict[str, Any]], Any],
        ] = {}

        self._sequence = 0

    # ----------------------------------------------------------
    # REGISTER HANDLER
    # ----------------------------------------------------------

    def register_handler(
        self,
        event_type: str,
        handler: Callable[
            [Dict[str, Any]],
            Any,
        ],
    ):

        self.handlers[
            str(event_type).upper()
        ] = handler

    # ----------------------------------------------------------
    # SCHEDULE EVENT
    # ----------------------------------------------------------

    def schedule(
        self,
        time: int,
        event_type: str,
        data: Optional[
            Dict[str, Any]
        ] = None,
    ):

        event = Event(
            time=int(time),
            sequence=self._sequence,
            event_type=str(
                event_type
            ).upper(),
            data=data or {},
        )

        self._sequence += 1

        self.events.append(event)

        self.events.sort()

        return event

    # ----------------------------------------------------------
    # PROCESS EVENTS
    # ----------------------------------------------------------

    def process(
        self,
        current_time: int,
    ):

        processed = []

        for event in self.events:

            if event.processed:
                continue

            if event.time > current_time:
                continue

            handler = self.handlers.get(
                event.event_type
            )

            if handler is not None:

                try:
                    handler(event.data)

                except Exception as error:

                    # Keep the simulation alive.
                    # The simulator can record the
                    # failure if desired.
                    event.data[
                        "_error"
                    ] = str(error)

            event.processed = True

            processed.append(event)

        return processed

    # ----------------------------------------------------------
    # PENDING EVENTS
    # ----------------------------------------------------------

    def get_pending_events(self):

        return [
            event
            for event in self.events
            if not event.processed
        ]

    # ----------------------------------------------------------
    # ALL EVENTS
    # ----------------------------------------------------------

    def get_events(self):

        return list(self.events)

    # ----------------------------------------------------------
    # CLEAR PROCESSED EVENTS
    # ----------------------------------------------------------

    def clear_processed(self):

        self.events = [
            event
            for event in self.events
            if not event.processed
        ]

    # ----------------------------------------------------------
    # RESET
    # ----------------------------------------------------------

    def reset(self):

        self.events.clear()

        self._sequence = 0

    # ----------------------------------------------------------
    # DEBUG
    # ----------------------------------------------------------

    def print_pending(self):

        print()
        print("=" * 70)
        print("PENDING EVENTS")
        print("=" * 70)

        pending = self.get_pending_events()

        if not pending:

            print("No pending events.")

        else:

            for event in pending:

                print(
                    f"[{event.time:>3} min] "
                    f"{event.event_type} "
                    f"{event.data}"
                )

        print("=" * 70)


# ==============================================================
# BASIC TEST
# ==============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("EVENT ENGINE TEST")
    print("=" * 70)

    engine = EventEngine()

    received = []

    def test_handler(data):

        received.append(data)

        print(
            f"EVENT: "
            f"{data.get('message', 'received')}"
        )

    engine.register_handler(
        "TEST_EVENT",
        test_handler,
    )

    engine.schedule(
        time=3,
        event_type="TEST_EVENT",
        data={
            "message": "First event",
        },
    )

    engine.schedule(
        time=5,
        event_type="TEST_EVENT",
        data={
            "message": "Second event",
        },
    )

    for minute in range(7):

        print()
        print(
            f"TIME: {minute} min"
        )

        events = engine.process(
            minute
        )

        for event in events:

            print(
                f"Processed: "
                f"{event.event_type}"
            )

    print()
    print(
        f"Events received: "
        f"{len(received)}"
    )

    print("=" * 70)