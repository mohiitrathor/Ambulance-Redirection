"""
RAAH Milestone 13 Phase 2 Acceptance Test Suite
===============================================
Validates:
1. Backend quick dispatch (POST /dispatch/{incident_id}) broadcasts INCIDENT_DISPATCHED.
2. Backend manual step (POST /simulation/tick) broadcasts TICK with moving_ambulances.
3. Realtime event contracts for Command Center: moving_ambulances, dispatches, redirections.
4. Frontend structure: Stream status pill, Activity Feed, Keyed Leaflet map markers, CSS styles.
5. Store non-destructive operations and stream synchronization state.
"""

import asyncio
import json
import os
import sys
import unittest

# Ensure root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from api.main import app
from api.dependencies import manager
from api.auth import create_test_token, Role
from api.realtime.broadcaster import broadcaster
from api.realtime.models import EventType, RealtimeEvent


class TestM13Phase2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        manager.initialize()
        cls.token = create_test_token(role=Role.ADMINISTRATOR, username="admin_commander")
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    def setUp(self):
        manager.reset()

    def test_01_quick_dispatch_broadcasts_incident_dispatched(self):
        """Quick dispatch (POST /dispatch/{incident_id}) must broadcast INCIDENT_DISPATCHED to subscribers."""
        received_events = []
        client_id = "test_quick_dispatch_sub"
        
        async def sub_listener():
            session = broadcaster.subscribe(client_id)
            try:
                while True:
                    ev = await session.queue.get()
                    received_events.append(ev)
                    if ev.event_type == EventType.INCIDENT_DISPATCHED.value:
                        break
            finally:
                broadcaster.unsubscribe(client_id)

        async def run_test():
            task = asyncio.create_task(sub_listener())
            await asyncio.sleep(0.02)
            
            resp = self.client.post("/dispatch/1", headers=self.headers)
            self.assertEqual(resp.status_code, 200, f"Quick dispatch failed: {resp.text}")
            data = resp.json()
            self.assertEqual(data.get("incident_id"), 1)
            
            await asyncio.wait_for(task, timeout=1.0)

        asyncio.run(run_test())
        
        dispatched_events = [e for e in received_events if e.event_type == EventType.INCIDENT_DISPATCHED.value]
        self.assertGreaterEqual(len(dispatched_events), 1, "Expected at least 1 INCIDENT_DISPATCHED event")
        payload = dispatched_events[0].payload
        self.assertEqual(payload.get("incident_id"), 1)
        self.assertTrue("ambulance_id" in payload or "ambulance" in payload)
        self.assertTrue("hospital_id" in payload or "hospital" in payload)

    def test_02_manual_tick_broadcasts_tick_event(self):
        """Manual step (POST /simulation/tick) must broadcast TICK event with moving_ambulances."""
        # Dispatch an incident so there is an active moving unit
        self.client.post("/dispatch/1", headers=self.headers)
        
        received_events = []
        client_id = "test_manual_tick_sub"
        
        async def sub_listener():
            session = broadcaster.subscribe(client_id)
            try:
                while True:
                    ev = await session.queue.get()
                    received_events.append(ev)
                    if ev.event_type == EventType.TICK.value:
                        break
            finally:
                broadcaster.unsubscribe(client_id)

        async def run_test():
            task = asyncio.create_task(sub_listener())
            await asyncio.sleep(0.02)
            
            resp = self.client.post("/simulation/tick", headers=self.headers)
            self.assertEqual(resp.status_code, 200, f"Simulation tick failed: {resp.text}")
            
            await asyncio.wait_for(task, timeout=1.0)

        asyncio.run(run_test())
        
        tick_events = [e for e in received_events if e.event_type == EventType.TICK.value]
        self.assertGreaterEqual(len(tick_events), 1, "Expected at least 1 TICK event")
        tick = tick_events[0]
        self.assertIn(tick.payload.get("status"), ["RUNNING", "STOPPED", "PAUSED"])
        self.assertIn("current_time", tick.payload)
        self.assertIn("moving_ambulances", tick.payload)
        self.assertIsInstance(tick.payload["moving_ambulances"], list)

    def test_03_command_center_html_structure(self):
        """Verify frontend/index.html includes Stream status pill and Activity feed container."""
        index_path = os.path.join(os.path.dirname(__file__), "frontend", "index.html")
        self.assertTrue(os.path.exists(index_path), "frontend/index.html not found")
        
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn('id="stream-status-pill"', content)
        self.assertIn('id="stream-status-text"', content)
        self.assertIn('id="stream-seq-badge"', content)
        self.assertIn('id="event-feed-container"', content)
        self.assertIn('id="leaflet-map"', content)

    def test_04_connection_status_component_exists(self):
        """Verify connection_status.js component exists and defines setupConnectionStatus."""
        cs_path = os.path.join(os.path.dirname(__file__), "frontend", "js", "components", "connection_status.js")
        self.assertTrue(os.path.exists(cs_path), "frontend/js/components/connection_status.js not found")
        
        with open(cs_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("setupConnectionStatus", content)
        self.assertIn("stream-connected", content)
        self.assertIn("stream-reconnecting", content)
        self.assertIn("stream-syncing", content)
        self.assertIn("stream-disconnected", content)

    def test_05_tactical_map_keyed_markers(self):
        """Verify TacticalMap implements keyed non-destructive marker updates."""
        map_path = os.path.join(os.path.dirname(__file__), "frontend", "js", "map.js")
        self.assertTrue(os.path.exists(map_path), "frontend/js/map.js not found")
        
        with open(map_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("this.incidentsLayer", content)
        self.assertIn("this.incidentMarkers", content)
        self.assertIn("this.activeAmbulanceMarkers", content)
        self.assertIn("this.routeLines", content)
        self.assertIn(".setLatLng(", content)
        self.assertIn("incident-marker-pin", content)
        self.assertIn("focusIncident", content)

    def test_06_state_non_destructive_methods(self):
        """Verify frontend/js/state.js exposes non-destructive mutation methods."""
        state_path = os.path.join(os.path.dirname(__file__), "frontend", "js", "state.js")
        self.assertTrue(os.path.exists(state_path), "frontend/js/state.js not found")
        
        with open(state_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("updateHospital", content)
        self.assertIn("updateAmbulances", content)
        self.assertIn("addOrUpdateIncident", content)
        self.assertIn("removeIncident", content)
        self.assertIn("setConnectionStatus", content)
        self.assertIn("addActivityEntry", content)
        self.assertIn("streamConnection", content)
        self.assertIn("activityFeed", content)

    def test_07_events_component_supports_activity_feed(self):
        """Verify frontend/js/components/events.js renders rich activity feed with badges and links."""
        events_path = os.path.join(os.path.dirname(__file__), "frontend", "js", "components", "events.js")
        self.assertTrue(os.path.exists(events_path), "frontend/js/components/events.js not found")
        
        with open(events_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("activityFeed", content)
        self.assertIn("event-badge", content)
        self.assertIn("event-time-pill", content)
        self.assertIn("event-link", content)

    def test_08_css_components_style_definitions(self):
        """Verify frontend/css/components.css includes incident pins, status pills, and badges."""
        css_path = os.path.join(os.path.dirname(__file__), "frontend", "css", "components.css")
        self.assertTrue(os.path.exists(css_path), "frontend/css/components.css not found")
        
        with open(css_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn(".incident-marker-pin", content)
        self.assertIn(".incident-marker-pin.p1", content)
        self.assertIn(".status-pill.stream-connected", content)
        self.assertIn(".status-pill.stream-reconnecting", content)
        self.assertIn(".status-pill.stream-syncing", content)
        self.assertIn(".status-pill.stream-disconnected", content)
        self.assertIn(".event-badge.badge-dispatch", content)
        self.assertIn(".event-badge.badge-redirect", content)

    def test_09_app_bootstrap_wires_realtime_components(self):
        """Verify frontend/js/app.js imports and wires setupConnectionStatus and stream handlers."""
        app_path = os.path.join(os.path.dirname(__file__), "frontend", "js", "app.js")
        self.assertTrue(os.path.exists(app_path), "frontend/js/app.js not found")
        
        with open(app_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("setupConnectionStatus", content)
        self.assertIn("store.setConnectionStatus", content)
        self.assertIn("store.updateAmbulances", content)
        self.assertIn("store.addOrUpdateIncident", content)
        self.assertIn("store.addActivityEntry", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
