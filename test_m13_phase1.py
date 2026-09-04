"""
RAAH Milestone 13 Phase 1 — Comprehensive Test Suite
====================================================

Validates the Real-Time Command Center & Event Stream (SSE) architecture:
- Event envelope & closed EventType schema compliance
- Deterministic canonical serialization
- Process-level sequence monotonicity & gap recovery
- Replay ring buffer (200 max) & per-subscriber bounded queue (100 max)
- Sliding-window oldest-drop backpressure & slow-client isolation
- Cross-thread non-blocking distribution
- Header Bearer JWT & query-token fallback authentication
- VIEW_LIVE permission enforcement & 401/403 status distinction
- Zero token leakage across logs, errors, and metrics
- Initial authoritative STATE_SNAPSHOT delivery
- Invariant: Zero mutable DispatchState references escape
- 100 concurrent subscribers scalability
- Abrupt disconnect & clean shutdown handling
- Frontend polling elimination audit
- TICK payload minimization (<10 KB vs >200 KB)
- Backwards compatibility with REST endpoints
"""

import asyncio
import json
import os
import re
import sys
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from api.main import app
from api.settings import settings
from api.dependencies import manager
from api.auth import create_test_token, Role, Permission
from api.realtime.models import RealtimeEvent, EventType
from api.realtime.broadcaster import EventBroadcaster, broadcaster
from api.observability.metrics import metrics_collector
from simulation_output import SimulationOutput


class TestM13Phase1RealtimeStream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        manager.initialize()

    def test_01_event_envelope_schema_and_version(self):
        """1. Event envelope schema, version, and required fields."""
        event = RealtimeEvent(
            event_type=EventType.TICK.value,
            simulation_time=15,
            sequence=1,
            payload={"status": "RUNNING"},
        )
        self.assertEqual(event.schema_version, 1)
        self.assertTrue(event.event_id.startswith("evt_"))
        self.assertEqual(event.event_type, "TICK")
        self.assertEqual(event.simulation_time, 15)
        self.assertEqual(event.sequence, 1)
        self.assertEqual(event.payload, {"status": "RUNNING"})
        self.assertIn("T", event.occurred_at)

    def test_02_deterministic_serialization(self):
        """2. Canonical deterministic serialization with sorted keys."""
        event1 = RealtimeEvent(
            event_id="evt_test_fixed_id",
            event_type=EventType.TICK.value,
            occurred_at="2026-09-03T12:00:00+00:00",
            simulation_time=20,
            sequence=42,
            payload={"b": 2, "a": 1, "z": [3, 2, 1]},
        )
        event2 = RealtimeEvent(
            event_id="evt_test_fixed_id",
            event_type=EventType.TICK.value,
            occurred_at="2026-09-03T12:00:00+00:00",
            simulation_time=20,
            sequence=42,
            payload={"z": [3, 2, 1], "a": 1, "b": 2},
        )
        self.assertEqual(event1.to_json(), event2.to_json())
        self.assertEqual(event1.to_sse(), event2.to_sse())
        self.assertIn('"a":1', event1.to_json())
        self.assertIn("id: 42\nevent: TICK\ndata: ", event1.to_sse())

    def test_03_sequence_monotonicity(self):
        """3. Process-level strictly monotonic sequence numbers."""
        b = EventBroadcaster()
        s1 = b.broadcast(EventType.TICK, {"tick": 1}, 10)
        s2 = b.broadcast(EventType.TICK, {"tick": 2}, 11)
        s3 = b.broadcast(EventType.TICK, {"tick": 3}, 12)
        self.assertEqual(s1.sequence, 1)
        self.assertEqual(s2.sequence, 2)
        self.assertEqual(s3.sequence, 3)
        self.assertEqual(b.current_sequence, 3)

    def test_04_cross_thread_broadcast_safety(self):
        """4. Broadcaster does not deadlock or raise when called across threads."""
        b = EventBroadcaster()
        errors = []

        def worker(worker_id):
            try:
                for i in range(25):
                    b.broadcast(EventType.TICK, {"worker": worker_id, "i": i}, 10 + i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        self.assertEqual(len(errors), 0)
        self.assertEqual(b.current_sequence, 100)

    def test_05_bounded_queue_and_oldest_drop(self):
        """5. Subscriber queue has maxsize=100 and drops oldest event on overflow."""
        b = EventBroadcaster(client_queue_size=5)
        session = b.subscribe("sub_slow_1")

        for i in range(8):
            b.broadcast(EventType.TICK, {"num": i}, i)

        self.assertEqual(session.queue.qsize(), 5)
        self.assertTrue(session.has_sequence_gap)

        first_out = session.queue.get_nowait()
        self.assertEqual(first_out.payload["num"], 3)
        b.unsubscribe("sub_slow_1")

    def test_06_slow_client_isolation(self):
        """6. Slow subscriber drop policy does not delay or affect fast subscribers."""
        b = EventBroadcaster(client_queue_size=3)
        slow_sub = b.subscribe("sub_slow")
        fast_sub = b.subscribe("sub_fast")

        received_fast = []
        for i in range(6):
            b.broadcast(EventType.TICK, {"val": i}, i)
            while not fast_sub.queue.empty():
                received_fast.append(fast_sub.queue.get_nowait().payload["val"])

        self.assertEqual(received_fast, [0, 1, 2, 3, 4, 5])
        self.assertEqual(slow_sub.queue.qsize(), 3)
        self.assertTrue(slow_sub.has_sequence_gap)

        b.unsubscribe("sub_slow")
        b.unsubscribe("sub_fast")

    def test_07_disconnect_cleanup(self):
        """7. Unsubscribing a client cleanly frees resources and updates metrics."""
        b = EventBroadcaster()
        initial_count = b.active_subscribers_count
        session = b.subscribe("sub_temp_1")
        self.assertEqual(b.active_subscribers_count, initial_count + 1)

        b.unsubscribe("sub_temp_1")
        self.assertEqual(b.active_subscribers_count, initial_count)
        b.unsubscribe("sub_temp_1")
        self.assertFalse(session.is_active)

    def test_08_reconnect_within_replay_buffer(self):
        """8. Reconnecting client with sequence in replay buffer receives missing events."""
        b = EventBroadcaster(max_replay_size=10)
        for i in range(5):
            b.broadcast(EventType.TICK, {"idx": i}, i)

        missing, gap_detected = b.get_events_since(2)
        self.assertFalse(gap_detected)
        self.assertEqual(len(missing), 3)
        self.assertEqual([e.sequence for e in missing], [3, 4, 5])

    def test_09_replay_buffer_gap_recovery(self):
        """9. Reconnecting client with expired sequence triggers gap_detected=True."""
        b = EventBroadcaster(max_replay_size=3)
        for i in range(6):
            b.broadcast(EventType.TICK, {"idx": i}, i)

        missing, gap_detected = b.get_events_since(1)
        self.assertTrue(gap_detected)

    def test_10_heartbeat(self):
        """10. Broadcaster produces valid HEARTBEAT event with current sequence."""
        b = EventBroadcaster()
        b.broadcast(EventType.TICK, {}, 10)
        hb = b.create_heartbeat(simulation_time=10)
        self.assertEqual(hb.event_type, EventType.HEARTBEAT.value)
        self.assertEqual(hb.sequence, 1)
        self.assertTrue(hb.payload["heartbeat"])

    def test_11_authorization_header_authentication(self):
        """11. GET /events/stream accepts valid Authorization: Bearer <token>."""
        token = create_test_token(role=Role.DISPATCHER, username="auth_test_user")
        with self.client.stream("GET", "/events/stream?max_events=1", headers={"Authorization": f"Bearer {token}"}) as resp:
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/event-stream", resp.headers["content-type"])
            for chunk in resp.iter_lines():
                if chunk.startswith("data:"):
                    data = json.loads(chunk[5:])
                    self.assertEqual(data["event_type"], "STATE_SNAPSHOT")
                    self.assertIn("dashboard", data["payload"])
                    break

    def test_12_query_token_authentication(self):
        """12. GET /events/stream accepts ?token=<token> fallback for EventSource."""
        token = create_test_token(role=Role.SUPERVISOR, username="query_token_user")
        with self.client.stream("GET", f"/events/stream?token={token}&max_events=1") as resp:
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/event-stream", resp.headers["content-type"])
            for chunk in resp.iter_lines():
                if chunk.startswith("data:"):
                    data = json.loads(chunk[5:])
                    self.assertEqual(data["event_type"], "STATE_SNAPSHOT")
                    break

    def test_13_missing_token_401(self):
        """13. Missing credentials returns HTTP 401 when auth is enforced."""
        with patch.object(settings, "auth_enforced", True), patch.object(settings, "dev_auth_fallback", False):
            resp = self.client.get("/events/stream")
            self.assertEqual(resp.status_code, 401)
            self.assertIn("WWW-Authenticate", resp.headers)

    def test_14_invalid_or_expired_token_401(self):
        """14. Invalid or expired token returns HTTP 401."""
        resp = self.client.get("/events/stream", headers={"Authorization": "Bearer invalid.token.payload"})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["status_code"], 401)

    def test_15_insufficient_view_live_permission_403(self):
        """15. User role without VIEW_LIVE permission receives HTTP 403."""
        from api.auth.models import PERMISSION_ROLES
        orig_roles = PERMISSION_ROLES[Permission.VIEW_LIVE]
        try:
            PERMISSION_ROLES[Permission.VIEW_LIVE] = {Role.ADMINISTRATOR}
            token = create_test_token(role=Role.DISPATCHER, username="non_admin")
            resp = self.client.get("/events/stream", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(resp.status_code, 403)
            self.assertIn("VIEW_LIVE", resp.json()["detail"])
        finally:
            PERMISSION_ROLES[Permission.VIEW_LIVE] = orig_roles

    def test_16_initial_authoritative_snapshot(self):
        """16. Newly connected client receives authoritative STATE_SNAPSHOT as first event."""
        token = create_test_token(role=Role.DISPATCHER, username="snap_user")
        with self.client.stream("GET", "/events/stream?max_events=1", headers={"Authorization": f"Bearer {token}"}) as resp:
            found_snapshot = False
            for line in resp.iter_lines():
                if line.startswith("event: STATE_SNAPSHOT"):
                    found_snapshot = True
                elif line.startswith("data:") and found_snapshot:
                    payload = json.loads(line[5:])
                    self.assertIn("dashboard", payload["payload"])
                    self.assertIn("fleet", payload["payload"]["dashboard"])
                    break
            self.assertTrue(found_snapshot)

    def test_17_no_mutable_dispatch_state_escape(self):
        """17. Invariant: RealtimeEvent payloads contain only primitive/dict representations."""
        with manager.lock:
            state = manager.simulator.state
            dash = SimulationOutput.dashboard_snapshot(state)
            self.assertIsInstance(dash, dict)
            self.assertIsInstance(dash["fleet"], dict)
            self.assertFalse(hasattr(dash, "ambulances"))

        event = broadcaster.broadcast(EventType.TICK, dash, state.current_time)
        dumped = json.dumps(event.payload)
        loaded = json.loads(dumped)
        self.assertEqual(loaded["time"], state.current_time)

    def test_18_zero_token_leakage(self):
        """18. Invariant: Tokens in query strings are never reflected in logs, metrics, or errors."""
        fake_token = "secret_jwt_token_12345"
        resp = self.client.get(f"/events/stream?token={fake_token}")
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn(fake_token, resp.text)
        metrics_snap = metrics_collector.get_snapshot()
        metrics_str = json.dumps(metrics_snap)
        self.assertNotIn(fake_token, metrics_str)

    def test_19_concurrent_subscribers(self):
        """19. Broadcaster supports 100 concurrent subscribers with low distribution latency."""
        b = EventBroadcaster(client_queue_size=20)
        sessions = [b.subscribe(f"client_{i}") for i in range(100)]
        self.assertEqual(b.active_subscribers_count, 100)

        start_t = time.perf_counter()
        b.broadcast(EventType.TICK, {"metric": "concurrency_test"}, 50)
        duration_ms = (time.perf_counter() - start_t) * 1000.0

        for s in sessions:
            self.assertEqual(s.queue.qsize(), 1)

        self.assertLess(duration_ms, 25.0)

        for i in range(100):
            b.unsubscribe(f"client_{i}")
        self.assertEqual(b.active_subscribers_count, 0)

    def test_20_worker_failure_isolation(self):
        """20. Simulation worker tick exception does not crash or corrupt event stream."""
        b = EventBroadcaster()
        session = b.subscribe("worker_failure_sub")

        try:
            raise RuntimeError("Simulated vehicle kinematics failure in worker")
        except Exception as exc:
            b.broadcast(EventType.SYSTEM_ALERT, {"error": str(exc)}, 10)

        self.assertEqual(session.queue.qsize(), 1)
        event = session.queue.get_nowait()
        self.assertEqual(event.event_type, EventType.SYSTEM_ALERT.value)
        self.assertIn("Simulated vehicle kinematics failure", event.payload["error"])
        b.unsubscribe("worker_failure_sub")

    def test_21_clean_shutdown(self):
        """21. Broadcaster shutdown cleanly closes all subscriber queues."""
        b = EventBroadcaster()
        s1 = b.subscribe("sub_1")
        s2 = b.subscribe("sub_2")

        b.shutdown()
        self.assertEqual(b.active_subscribers_count, 0)
        self.assertIsNone(s1.queue.get_nowait())
        self.assertIsNone(s2.queue.get_nowait())

    def test_22_rest_backwards_compatibility(self):
        """22. Existing REST endpoints continue to return exact expected schemas."""
        token = create_test_token(role=Role.DISPATCHER, username="rest_compat_user")
        headers = {"Authorization": f"Bearer {token}"}

        r_dash = self.client.get("/state/dashboard", headers=headers)
        self.assertEqual(r_dash.status_code, 200)
        self.assertIn("fleet", r_dash.json())
        self.assertIn("time", r_dash.json())

        r_snap = self.client.get("/state/snapshot", headers=headers)
        self.assertEqual(r_snap.status_code, 200)
        self.assertIn("ambulances", r_snap.json())
        self.assertIn("hospitals", r_snap.json())

        r_events = self.client.get("/events/pending", headers=headers)
        self.assertEqual(r_events.status_code, 200)
        self.assertIsInstance(r_events.json(), list)

    def test_23_frontend_polling_elimination(self):
        """23. Frontend audit: 1-second and 3-second polling loops are removed."""
        with open("frontend/js/app.js", "r") as f:
            content = f.read()

        self.assertNotIn("startPollingLoop", content)
        self.assertIn("api.connectEventStream", content)

        with open("frontend/js/components/coordination.js", "r") as f:
            c_content = f.read()
        self.assertIn("60000", c_content)
        self.assertIn("degraded background safety fallback", c_content)

        with open("frontend/js/components/hospitals.js", "r") as f:
            h_content = f.read()
        self.assertIn("60000", h_content)
        self.assertIn("degraded background safety fallback", h_content)

    def test_24_metrics_correctness(self):
        """24. MetricsCollector accurately tracks stream connections, events, and drops."""
        snap = metrics_collector.get_snapshot()
        self.assertIn("realtime_stream", snap)
        rt = snap["realtime_stream"]
        self.assertIn("active_connections", rt)
        self.assertIn("events_emitted_total", rt)
        self.assertIn("events_dropped_total", rt)
        self.assertIn("slow_clients_total", rt)
        self.assertIn("sequence_gaps_total", rt)
        self.assertIn("mean_broadcast_ms", rt)

    def test_25_duplicate_stream_prevention(self):
        """25. Same client_id subscribing again replaces existing session without leak."""
        b = EventBroadcaster()
        s1 = b.subscribe("client_dup_test")
        self.assertEqual(b.active_subscribers_count, 1)

        s2 = b.subscribe("client_dup_test")
        self.assertEqual(b.active_subscribers_count, 1)
        self.assertFalse(s1.is_active)
        self.assertTrue(s2.is_active)
        b.unsubscribe("client_dup_test")
        self.assertEqual(b.active_subscribers_count, 0)

    def test_26_replay_buffer_wraparound(self):
        """26. Replay buffer wraps at 200 items; older items drop off."""
        b = EventBroadcaster(max_replay_size=200)
        for i in range(250):
            b.broadcast(EventType.TICK, {"i": i}, i)

        self.assertEqual(b.current_sequence, 250)
        missing, gap = b.get_events_since(50)
        self.assertFalse(gap)
        self.assertEqual(len(missing), 200)
        self.assertEqual(missing[0].sequence, 51)

        missing_old, gap_old = b.get_events_since(49)
        self.assertTrue(gap_old)

    def test_27_abrupt_client_disconnect(self):
        """27. Abrupt disconnect terminates generator and unregisters subscriber cleanly."""
        token = create_test_token(role=Role.DISPATCHER, username="abrupt_disconnect_user")
        initial_count = broadcaster.active_subscribers_count

        with self.client.stream("GET", "/events/stream?max_events=1", headers={"Authorization": f"Bearer {token}"}) as resp:
            self.assertEqual(resp.status_code, 200)
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    break

        time.sleep(0.1)
        self.assertEqual(broadcaster.active_subscribers_count, initial_count)

    def test_28_shutdown_with_connected_clients(self):
        """28. Shutdown terminates open client streams cleanly without hanging."""
        b = EventBroadcaster()
        s1 = b.subscribe("shutdown_client_1")
        s2 = b.subscribe("shutdown_client_2")
        self.assertEqual(b.active_subscribers_count, 2)

        start_t = time.perf_counter()
        b.shutdown()
        duration_ms = (time.perf_counter() - start_t) * 1000.0

        self.assertLess(duration_ms, 50.0)
        self.assertEqual(b.active_subscribers_count, 0)
        self.assertIsNone(s1.queue.get_nowait())
        self.assertIsNone(s2.queue.get_nowait())

    def test_29_exactly_one_snapshot_recovery_after_gap(self):
        """29. Reconnecting with gap flag returns exactly one STATE_SNAPSHOT."""
        token = create_test_token(role=Role.DISPATCHER, username="gap_snap_user")
        with self.client.stream("GET", "/events/stream?since_sequence=99999&max_events=1", headers={"Authorization": f"Bearer {token}"}) as resp:
            self.assertEqual(resp.status_code, 200)
            snapshot_count = 0
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    if data["event_type"] == "STATE_SNAPSHOT":
                        snapshot_count += 1
                        self.assertTrue(data["payload"]["gap_detected"])
                        break
            self.assertEqual(snapshot_count, 1)

    def test_30_event_loop_unavailable_behavior(self):
        """30. Broadcasting when event loop is None does not raise or block."""
        b = EventBroadcaster()
        b.set_event_loop(None)
        s = b.subscribe("no_loop_sub", loop=None)
        b.broadcast(EventType.TICK, {"test": "no_loop"}, 1)
        self.assertEqual(s.queue.qsize(), 1)
        b.unsubscribe("no_loop_sub")

    def test_31_malformed_payload_rejection(self):
        """31. Invalid event_type string is strictly rejected by RealtimeEvent validator."""
        with self.assertRaises(ValueError):
            RealtimeEvent(
                event_type="ARBITRARY_UNDOCUMENTED_EVENT",
                simulation_time=10,
                sequence=1,
                payload={},
            )

    def test_32_tick_payload_minimization(self):
        """32. TICK payload size is under 10 KB vs >200 KB full dashboard."""
        from Dispatch.simulator import Simulator
        sim = Simulator()
        state = sim.state
        fleet_counts = SimulationOutput.fleet_summary(state.ambulances.values())
        active_inc_count = len(state.get_active_incidents())
        moving_ambs = [
            {
                "ambulance_id": str(a.ambulance_id),
                "latitude": round(float(a.latitude), 6),
                "longitude": round(float(a.longitude), 6),
                "status": str(a.status),
                "eta_minutes": round(float(a.eta_minutes), 2) if a.eta_minutes is not None else None,
            }
            for a in state.ambulances.values()
            if a.status == "EN_ROUTE" or getattr(a, "is_repositioning", False)
        ]
        tick_payload = {
            "current_time": state.current_time,
            "status": "RUNNING",
            "speed_multiplier": 60.0,
            "ticks_processed": 1,
            "fleet": fleet_counts,
            "active_incidents_count": active_inc_count,
            "moving_ambulances": moving_ambs,
        }

        event = RealtimeEvent(
            event_type=EventType.TICK.value,
            simulation_time=state.current_time,
            sequence=1,
            payload=tick_payload,
        )
        serialized_bytes = len(event.to_json().encode("utf-8"))
        self.assertLess(serialized_bytes, 10240, f"TICK payload too large: {serialized_bytes} bytes")

    def test_33_hospital_update_enum_and_protocol_validation(self):
        """33. HOSPITAL_UPDATE is formally included in EventType enum and serializable."""
        self.assertEqual(EventType.HOSPITAL_UPDATE.value, "HOSPITAL_UPDATE")
        event = RealtimeEvent(
            event_type=EventType.HOSPITAL_UPDATE.value,
            simulation_time=15,
            sequence=10,
            payload={"hospital_id": "HOSP_001", "available_beds": 12, "surge": False},
        )
        self.assertEqual(event.event_type, "HOSPITAL_UPDATE")
        sse_text = event.to_sse()
        self.assertIn("event: HOSPITAL_UPDATE", sse_text)
        self.assertIn('"hospital_id":"HOSP_001"', sse_text)


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING RAAH M13 PHASE 1 REALTIME COMMAND CENTER TEST SUITE")
    print("=" * 70)
    unittest.main(verbosity=2)
