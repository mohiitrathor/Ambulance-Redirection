from events import EventEngine


def test_event_order():

    engine = EventEngine()

    received = []

    def handler(data):

        received.append(
            data["name"]
        )

    engine.register_handler(
        "TEST",
        handler,
    )

    engine.schedule(
        time=5,
        event_type="TEST",
        data={
            "name": "five"
        },
    )

    engine.schedule(
        time=2,
        event_type="TEST",
        data={
            "name": "two"
        },
    )

    engine.schedule(
        time=3,
        event_type="TEST",
        data={
            "name": "three"
        },
    )

    engine.process(2)

    assert received == [
        "two"
    ]

    engine.process(3)

    assert received == [
        "two",
        "three",
    ]

    engine.process(5)

    assert received == [
        "two",
        "three",
        "five",
    ]


def test_future_events_remain_pending():

    engine = EventEngine()

    engine.schedule(
        time=10,
        event_type="TEST",
    )

    engine.process(5)

    assert len(
        engine.pending_events()
    ) == 1


def test_unknown_event_does_not_crash():

    engine = EventEngine()

    engine.schedule(
        time=1,
        event_type="UNKNOWN",
    )

    results = engine.process(1)

    assert len(results) == 1

    assert results[0][
        "handled"
    ] is False


if __name__ == "__main__":

    test_event_order()

    test_future_events_remain_pending()

    test_unknown_event_does_not_crash()

    print(
        "All event tests passed."
    )