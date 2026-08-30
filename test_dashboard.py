"""
RAAH Command Center Dashboard Integration Test (M4)
===================================================

Verifies:
  1. Static mounting of /dashboard/ and asset delivery.
  2. Local vendored Leaflet and Lucide asset integrity.
  3. UI modules (CSS, JS) served with 200 OK.
  4. End-to-end integration: Start simulation -> Dispatch incident ->
     Inject hospital saturation event -> Verify dynamic redirection ->
     Reset simulation.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from api.main import app
from api.dependencies import manager


def run_dashboard_tests():
    print()
    print("=" * 70)
    print("RAAH M4: DASHBOARD INTEGRATION TEST SUITE")
    print("=" * 70)

    with TestClient(app) as client:

        # ------------------------------------------------------
        # 1. Test Static Mounting of Dashboard
        # ------------------------------------------------------
        print("\n[1] Testing /dashboard/ static mount...")
        resp = client.get("/dashboard/")
        assert resp.status_code == 200, f"Dashboard index failed: {resp.status_code}"
        assert "RAAH" in resp.text
        assert "command-header" in resp.text
        assert "leaflet-map" in resp.text
        print("  -> PASS: /dashboard/ returned 200 OK with HTML shell.")

        # ------------------------------------------------------
        # 2. Test Local Vendored Assets (Offline Check)
        # ------------------------------------------------------
        print("\n[2] Testing locally vendored Leaflet and Lucide assets...")
        leaflet_js = client.get("/dashboard/vendor/leaflet/leaflet.js")
        assert leaflet_js.status_code == 200
        assert len(leaflet_js.content) > 100000

        leaflet_css = client.get("/dashboard/vendor/leaflet/leaflet.css")
        assert leaflet_css.status_code == 200

        lucide_js = client.get("/dashboard/vendor/lucide/lucide.min.js")
        assert lucide_js.status_code == 200
        assert len(lucide_js.content) > 200000
        print("  -> PASS: All vendored assets load locally from disk.")

        # ------------------------------------------------------
        # 3. Test Dashboard Modules (CSS & ES Modules)
        # ------------------------------------------------------
        print("\n[3] Testing tactical CSS and JS modules...")
        for path in [
            "/dashboard/css/command_center.css",
            "/dashboard/css/components.css",
            "/dashboard/js/app.js",
            "/dashboard/js/api.js",
            "/dashboard/js/state.js",
            "/dashboard/js/map.js",
            "/dashboard/js/components/controls.js",
            "/dashboard/js/components/incidents.js",
            "/dashboard/js/components/fleet.js",
            "/dashboard/js/components/hospitals.js",
            "/dashboard/js/components/events.js",
            "/dashboard/js/components/decisions.js",
        ]:
            r = client.get(path)
            assert r.status_code == 200, f"Asset failed: {path} (status {r.status_code})"

        print("  -> PASS: All 12 tactical CSS & JS modules served successfully.")

        # ------------------------------------------------------
        # 4. End-to-End Simulation & Triage Life Cycle
        # ------------------------------------------------------
        print("\n[4] Testing full command center operations cycle...")

        # A. Start Realtime Mode
        start_res = client.post("/simulation/realtime/start", json={"tick_interval_seconds": 0.1, "minutes_per_tick": 1})
        assert start_res.status_code == 200

        # B. Triage & Dispatch Incident 1
        disp_res = client.post("/dispatch/1")
        assert disp_res.status_code == 200
        disp_data = disp_res.json()
        assert disp_data["status"] == "DISPATCH_RECOMMENDED"
        orig_hospital = disp_data["hospital"]["hospital_id"]
        amb_id = disp_data["ambulance"]["ambulance_id"]
        print(f"  -> Dispatched Incident 1: Ambulance {amb_id} -> Hospital {orig_hospital}")

        # C. Verify dashboard reports 1 active incident and en_route ambulance
        dash = client.get("/state/dashboard").json()
        assert len(dash["active_incidents"]) >= 1
        assert dash["fleet"]["en_route"] >= 1

        # D. Inject HOSPITAL_FULL event for assigned hospital
        client.post("/events", json={"time": dash["time"] + 1, "event_type": "HOSPITAL_FULL", "data": {"hospital_id": orig_hospital}})

        # E. Stop realtime and step manually to trigger redirection
        client.post("/simulation/realtime/stop")
        step_res = client.post("/simulation/tick?minutes=2").json()

        # F. Verify redirection occurred and was logged
        decisions = client.get("/redirect/decisions/1").json()
        assert len(decisions) >= 1
        assert decisions[0]["decision"] == "REDIRECTED"
        print(f"  -> Verified Redirection: {decisions[0]['original_hospital']} -> {decisions[0]['new_hospital']} (ETA saved: {decisions[0]['eta_saved']}m)")

        # G. Reset simulation to time = 0
        reset_res = client.post("/simulation/reset")
        assert reset_res.status_code == 200
        assert client.get("/health").json()["time"] == 0
        print("  -> PASS: End-to-end command center life cycle completed and verified.")

    print("\n" + "=" * 70)
    print("ALL M4 DASHBOARD INTEGRATION TESTS PASSED!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_dashboard_tests()
