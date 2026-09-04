"""
RAAH Thread-Safe Real-Time Event Broadcaster
============================================

Manages active Server-Sent Events (SSE) subscribers, enforces bounded queues,
provides monotonic sequence numbering, ring-buffer event replay for reconnects,
sliding-window drop on queue saturation, and safe cross-thread distribution.

INVARIANTS:
1. DispatchState remains the sole live state authority.
2. The broadcaster is an immutable projection/notification distributor only.
3. Slow clients CANNOT block DispatchState, the simulation worker, or other clients.
4. No mutable references to DispatchState escape into event payloads or queues.
"""

import asyncio
import collections
import logging
import threading
import time
from typing import Dict, List, Optional, Set, Tuple, Any

from api.realtime.models import RealtimeEvent, EventType
from api.observability.metrics import metrics_collector

logger = logging.getLogger("raah.realtime.broadcaster")


class SubscriberSession:
    """
    Encapsulates an active client stream subscriber session.
    Allocates an isolated bounded queue and tracks delivery state.
    """

    def __init__(
        self,
        client_id: str,
        username: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        max_queue_size: int = 100,
    ):
        self.client_id: str = client_id
        self.username: str = username
        self.loop: Optional[asyncio.AbstractEventLoop] = loop
        self.max_queue_size: int = max_queue_size
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.has_sequence_gap: bool = False
        self.created_at: float = time.time()
        self.is_active: bool = True

    def put_event_threadsafe(self, event: RealtimeEvent):
        """
        Thread-safe insertion into the subscriber's asyncio.Queue.
        If queue is full, evicts oldest event to enforce bounded memory and
        marks sequence gap so client knows to perform REST re-anchoring.
        """
        if not self.is_active:
            return

        def _do_put():
            if not self.is_active:
                return
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except (asyncio.QueueEmpty, Exception):
                    pass
                self.has_sequence_gap = True
                metrics_collector.record_event_dropped()
                metrics_collector.record_slow_client()
                logger.warning(
                    "Subscriber '%s' queue saturated (depth=%d). Evicted oldest event to preserve backpressure boundary.",
                    self.client_id,
                    self.max_queue_size,
                    extra={"client_id": self.client_id, "user": self.username},
                )

            try:
                self.queue.put_nowait(event)
            except Exception as exc:
                logger.error("Failed to push event to subscriber '%s': %s", self.client_id, exc)

        if self.loop is not None and self.loop.is_running():
            try:
                # If we're already running inside the loop thread
                current_loop = None
                try:
                    current_loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass

                if current_loop is self.loop:
                    _do_put()
                else:
                    self.loop.call_soon_threadsafe(_do_put)
            except Exception as exc:
                logger.warning("Error scheduling event push to subscriber '%s': %s", self.client_id, exc)
        else:
            _do_put()

    def close(self):
        """Mark session closed and send termination sentinel."""
        self.is_active = False
        def _terminate():
            try:
                self.queue.put_nowait(None)
            except Exception:
                pass

        if self.loop is not None and self.loop.is_running():
            try:
                self.loop.call_soon_threadsafe(_terminate)
            except Exception:
                pass
        else:
            _terminate()


class EventBroadcaster:
    """
    Thread-safe, bounded real-time event distribution engine.
    """

    def __init__(self, max_replay_size: int = 200, client_queue_size: int = 100):
        self._lock = threading.Lock()
        self._sequence: int = 0
        self._replay_buffer: collections.deque = collections.deque(maxlen=max_replay_size)
        self._subscribers: Dict[str, SubscriberSession] = {}
        self._client_queue_size: int = client_queue_size
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_shutdown: bool = False
        self._last_broadcast_time: float = time.time()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the active asyncio event loop for cross-thread scheduling."""
        with self._lock:
            self._event_loop = loop

    @property
    def current_sequence(self) -> int:
        with self._lock:
            return self._sequence

    @property
    def active_subscribers_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def subscribe(
        self,
        client_id: str,
        username: str = "anonymous",
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> SubscriberSession:
        """
        Register a new subscriber and return its dedicated bounded session.
        """
        with self._lock:
            if self._is_shutdown:
                raise RuntimeError("Cannot subscribe to EventBroadcaster: shutting down.")

            # Clean up any existing session with this client_id (prevents duplicate streams)
            existing = self._subscribers.pop(client_id, None)
            if existing:
                existing.close()

            active_loop = loop or self._event_loop
            try:
                if active_loop is None:
                    active_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            session = SubscriberSession(
                client_id=client_id,
                username=username,
                loop=active_loop,
                max_queue_size=self._client_queue_size,
            )
            self._subscribers[client_id] = session

            metrics_collector.record_stream_connected()
            logger.info(
                "Realtime subscriber connected: client_id='%s' user='%s' (active=%d)",
                client_id,
                username,
                len(self._subscribers),
                extra={"client_id": client_id, "user": username},
            )
            return session

    def unsubscribe(self, client_id: str):
        """
        Deregister a subscriber and clean up its resources.
        """
        with self._lock:
            session = self._subscribers.pop(client_id, None)
            if session:
                session.close()
                metrics_collector.record_stream_disconnected()
                logger.info(
                    "Realtime subscriber disconnected: client_id='%s' (remaining=%d)",
                    client_id,
                    len(self._subscribers),
                    extra={"client_id": client_id},
                )

    def broadcast(
        self,
        event_type: EventType | str,
        payload: Dict[str, Any],
        simulation_time: int,
    ) -> RealtimeEvent:
        """
        Construct, sequence, buffer, and distribute an immutable event.
        Guaranteed non-blocking across threads.
        """
        start_t = time.perf_counter()
        t_type = event_type.value if isinstance(event_type, EventType) else str(event_type)

        with self._lock:
            if self._is_shutdown:
                logger.debug("Broadcast ignored: broadcaster is shut down.")
                return None

            self._sequence += 1
            seq = self._sequence

            event = RealtimeEvent(
                event_type=t_type,
                simulation_time=int(simulation_time),
                sequence=seq,
                payload=payload,
            )

            # Keep in replay buffer (never keep HEARTBEAT in replay buffer)
            if t_type != EventType.HEARTBEAT.value:
                self._replay_buffer.append(event)

            self._last_broadcast_time = time.time()
            subscribers_snapshot = list(self._subscribers.values())

        # Distribute outside broadcaster lock
        for sub in subscribers_snapshot:
            sub.put_event_threadsafe(event)

        dur_ms = (time.perf_counter() - start_t) * 1000.0
        metrics_collector.record_event_emitted(t_type, dur_ms)
        return event

    def get_events_since(self, since_sequence: int) -> Tuple[List[RealtimeEvent], bool]:
        """
        Retrieve events for reconnect.
        Returns (events_to_replay, gap_detected).
        If gap_detected is True, events_to_replay may be empty or incomplete,
        and caller MUST emit an authoritative STATE_SNAPSHOT.
        """
        with self._lock:
            if since_sequence == self._sequence:
                # Client is exactly up to date
                return ([], False)

            if since_sequence > self._sequence:
                # Client sequence is in future or from previous process run: gap detected
                metrics_collector.record_sequence_gap()
                return ([], True)

            if not self._replay_buffer:
                # Buffer empty or reset
                metrics_collector.record_sequence_gap()
                return ([], True)

            oldest_in_buffer = self._replay_buffer[0].sequence
            if since_sequence < oldest_in_buffer - 1 or since_sequence < 0:
                # Gap detected: requested sequence has dropped off the ring buffer
                metrics_collector.record_sequence_gap()
                return ([], True)

            # Replay missing events
            missing = [e for e in self._replay_buffer if e.sequence > since_sequence]
            metrics_collector.record_reconnect(len(missing))
            return (missing, False)

    def create_heartbeat(self, simulation_time: int = 0) -> RealtimeEvent:
        """
        Construct a non-sequenced keep-alive heartbeat event for idle connections.
        """
        with self._lock:
            seq = self._sequence

        return RealtimeEvent(
            event_type=EventType.HEARTBEAT.value,
            simulation_time=simulation_time,
            sequence=seq,
            payload={"timestamp": time.time(), "heartbeat": True},
        )

    def shutdown(self):
        """
        Gracefully terminate all active subscriber sessions.
        """
        with self._lock:
            self._is_shutdown = True
            sessions = list(self._subscribers.values())
            self._subscribers.clear()

        for session in sessions:
            session.close()

        logger.info("EventBroadcaster shutdown completed. Closed %d subscriber sessions.", len(sessions))


# Global Singleton Broadcaster Instance
broadcaster = EventBroadcaster()
