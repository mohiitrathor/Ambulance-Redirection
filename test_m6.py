"""
RAAH Milestone 6 Verification Test Suite
========================================

Verifies:
  1. Dynamic emergency intake through POST /dispatch/live.
  2. Incident detail data availability (vitals, ML triage, fleet, facility).
  3. Manual redirection using a DYNAMICALLY discovered valid alternative hospital.
  4. Evaluate reroute (POST /redirect/check/{id}) does NOT mutate live state.
  5. Execute reroute (POST /redirect/apply/{id}) DOES mutate live state correctly.
  6. Operator decision record contains '[OPERATOR]' in reason.
  7. Invalid incident -> HTTP 404.
  8. Arrived/non-en-route incident -> HTTP 400.
  9. Saturated/unavailable target hospital -> HTTP 409.
  10. Automatic alternative selection when target hospital is omitted.
  11. Concurrent manual redirection while real-time simulation is running.
  12. State consistency & zero deadlocks under concurrent real-time simulation.
  13. Zero occurrences of window.prompt(), window.alert(), or window.confirm() in frontend/.
"""

import sys
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from api.main import app
from api.dependencies import manager


def run_m6_tests():
    print()
    print("=" * 70)
    print("RAAH M6: ADVANCED COMMAND CENTER & OPERATOR CONTROLS TEST SUITE")
    print("=" * 70)

    with TestClient(app) as client:

        # Reset simulator to pristine state
        client.post("/simulation/reset")

        # ------------------------------------------------------
        # TEST 1: Dynamic Emergency Intake (POST /dispatch/live)
        # ------------------------------------------------------
        print("\n[TEST 1] Testing dynamic emergency call intake contract...")
        custom_payload = {
            "Sex": "Female",
            "Age": 58,
            "Condition": "Cardiac",
            "Arrival_Mode": "Ambulance",
            "Injury_Type": "No Injury",
            "Heart_Rate": 128.0,
            "SpO2": 88.0,
            "Systolic_BP": 90.0,
            "Diastolic_BP": 60.0,
            "Respiratory_Rate": 28.0,
            "Temperature": 37.4,
            "Consciousness": "Drowsy",
            "Oxygen_Requirement": "Oxygen Mask",
            "GCS": 13,
            "Pain_Score": 8,
            "Blood_Glucose": 180.0,
            "Respiratory_Distress": 1,
            "Chest_Pain": 1,
            "Bleeding": 0,
            "Seizure": 0,
            "Diabetes": 1,
            "Hypertension": 1,
            "Heart_Disease": 1,
            "Respiratory_Disease": 0,
            "patient_lat": 26.9124,
            "patient_lon": 75.7873,
        }

        resp = client.post("/dispatch/live", json=custom_payload)
        assert resp.status_code == 200, f"Dispatch failed: {resp.text}"
        live_data = resp.json()

        assert live_data["status"] == "DISPATCH_RECOMMENDED"
        assert live_data["patient"]["predicted_severity"] in ["Critical", "Emergency", "Moderate", "Low", "Non-Urgent"]
        assert live_data["ambulance"]["ambulance_id"].startswith("AMB_")
        assert live_data["hospital"]["hospital_id"].startswith("HOSP_")
        custom_incident_id = live_data["incident_id"]
        initial_hosp = live_data["hospital"]["hospital_id"]
        amb_id = live_data["ambulance"]["ambulance_id"]
        print(f"  -> PASS: Live emergency call triaged. Incident #{custom_incident_id}: {amb_id} -> {initial_hosp}")

        # ------------------------------------------------------
        # TEST 2: Incident Detail Data Availability
        # ------------------------------------------------------
        print("\n[TEST 2] Testing incident detail telemetry availability...")
        inc_resp = client.get(f"/state/incidents/{custom_incident_id}")
        assert inc_resp.status_code == 200
        inc_data = inc_resp.json()
        assert inc_data["incident_id"] == custom_incident_id
        assert inc_data["ambulance_id"] == amb_id
        assert inc_data["hospital_id"] == initial_hosp

        amb_resp = client.get(f"/state/ambulances/{amb_id}")
        assert amb_resp.status_code == 200
        assert amb_resp.json()["status"] == "EN_ROUTE"

        hosp_resp = client.get(f"/state/hospitals/{initial_hosp}")
        assert hosp_resp.status_code == 200
        print("  -> PASS: All incident, ambulance, and facility telemetry verified.")

        # ------------------------------------------------------
        # TEST 3 & 4: Evaluate Reroute Does NOT Mutate State
        # ------------------------------------------------------
        print("\n[TEST 3 & 4] Testing Evaluate Reroute (read-only evaluation)...")
        eval_resp = client.post(f"/redirect/check/{custom_incident_id}")
        assert eval_resp.status_code == 200
        eval_data = eval_resp.json()
        assert "redirect" in eval_data

        # Verify state was NOT mutated
        sim = manager.simulator
        with manager.lock:
            assert sim.state.incidents[custom_incident_id].hospital_id == initial_hosp
            assert sim.state.ambulances[amb_id].hospital_id == initial_hosp
            assert sim.state.incidents[custom_incident_id].status == "DISPATCHED"
        print("  -> PASS: Evaluate reroute completed cleanly without mutating live state.")

        # ------------------------------------------------------
        # TEST 5 & 6: Execute Reroute DOES Mutate State & Logs [OPERATOR]
        # (Using a DYNAMICALLY discovered valid alternative hospital)
        # ------------------------------------------------------
        print("\n[TEST 5 & 6] Testing manual reroute execution with dynamic hospital selection...")
        with manager.lock:
            # Dynamically discover a valid alternative hospital with available capacity
            candidate_hosp = None
            for h in sim.state.hospitals.values():
                if h.hospital_id != initial_hosp and not h.is_full and h.available_beds > 5 and h.available_icu > 2:
                    candidate_hosp = h.hospital_id
                    break

        assert candidate_hosp is not None, "Could not find a valid alternative hospital in live state."
        print(f"  -> Dynamically selected candidate hospital: {candidate_hosp} (current: {initial_hosp})")

        # Execute manual redirection
        apply_res = client.post(
            f"/redirect/apply/{custom_incident_id}",
            json={
                "target_hospital_id": candidate_hosp,
                "reason": "Dispatcher traffic re-route",
            },
        )
        assert apply_res.status_code == 200, f"Apply reroute failed: {apply_res.text}"
        decision = apply_res.json()

        assert decision["incident_id"] == custom_incident_id
        assert decision["original_hospital"] == initial_hosp
        assert decision["new_hospital"] == candidate_hosp
        assert "[OPERATOR]" in decision["reason"]
        print(f"  -> Decision logged: {decision['reason']} | {decision['original_hospital']} -> {decision['new_hospital']}")

        # Verify live state mutated correctly
        with manager.lock:
            assert sim.state.incidents[custom_incident_id].hospital_id == candidate_hosp
            assert sim.state.incidents[custom_incident_id].status == "REDIRECTED"
            assert sim.state.ambulances[amb_id].hospital_id == candidate_hosp
        print("  -> PASS: Live state mutated, route destination updated, and [OPERATOR] logged.")

        # ------------------------------------------------------
        # TEST 7: Invalid Incident ID Guard (HTTP 404)
        # ------------------------------------------------------
        print("\n[TEST 7] Testing invalid incident ID guard...")
        bad_inc = client.post("/redirect/apply/999999", json={"reason": "Invalid"})
        assert bad_inc.status_code == 404
        print("  -> PASS: Non-existent incident rejected with HTTP 404.")

        # ------------------------------------------------------
        # TEST 8: Arrived / Non-EN_ROUTE Guard (HTTP 400)
        # ------------------------------------------------------
        print("\n[TEST 8] Testing non-en-route ambulance guard...")
        with manager.lock:
            sim.state.ambulances[amb_id].status = "ARRIVED"

        arrived_res = client.post(
            f"/redirect/apply/{custom_incident_id}",
            json={"target_hospital_id": candidate_hosp},
        )
        assert arrived_res.status_code == 400
        assert "must be EN_ROUTE" in arrived_res.json()["detail"]
        print("  -> PASS: Arrived ambulance redirection rejected with HTTP 400.")

        # Restore status for subsequent tests
        with manager.lock:
            sim.state.ambulances[amb_id].status = "EN_ROUTE"

        # ------------------------------------------------------
        # TEST 9: Saturated / Unavailable Target Hospital Guard (HTTP 409)
        # ------------------------------------------------------
        print("\n[TEST 9] Testing saturated target hospital guard...")
        # Find another candidate and saturate it
        with manager.lock:
            saturated_target = None
            for h in sim.state.hospitals.values():
                if h.hospital_id != candidate_hosp and not h.is_full:
                    saturated_target = h.hospital_id
                    h.current_load = h.capacity  # Saturated
                    assert h.is_full is True
                    break

        assert saturated_target is not None
        sat_res = client.post(
            f"/redirect/apply/{custom_incident_id}",
            json={"target_hospital_id": saturated_target},
        )
        assert sat_res.status_code == 409
        print("  -> PASS: Saturated hospital rejected with HTTP 409.")

        # ------------------------------------------------------
        # TEST 10: Automatic Alternative Selection (Omitted Target)
        # ------------------------------------------------------
        print("\n[TEST 10] Testing automatic alternative selection when target hospital is omitted...")
        # Dispatch a fresh incident 20
        res_auto = client.post("/dispatch/20")
        assert res_auto.status_code == 200
        auto_hosp = res_auto.json()["hospital"]["hospital_id"]

        # Mark current hospital full so engine must redirect
        with manager.lock:
            sim.state.hospitals[auto_hosp].current_load = sim.state.hospitals[auto_hosp].capacity

        apply_auto = client.post(
            "/redirect/apply/20",
            json={"reason": "Emergency evacuation reroute"},
        )
        assert apply_auto.status_code == 200
        auto_decision = apply_auto.json()
        assert auto_decision["new_hospital"] != auto_hosp
        assert "[OPERATOR]" in auto_decision["reason"]
        print(f"  -> PASS: Automatic alternative selected: {auto_hosp} -> {auto_decision['new_hospital']}.")

        # ------------------------------------------------------
        # TEST 11 & 12: Concurrent Redirection While Real-Time Runs
        # ------------------------------------------------------
        print("\n[TEST 11 & 12] Testing concurrent operator actions under real-time simulation...")
        # Start real-time simulation
        start_res = client.post("/simulation/realtime/start", json={"tick_interval_seconds": 0.05, "minutes_per_tick": 1})
        assert start_res.status_code == 200

        # Dispatch an incident while real-time simulation runs
        disp_rt = client.post("/dispatch/5")
        assert disp_rt.status_code == 200
        rt_inc_id = 5
        orig_rt_hosp = disp_rt.json()["hospital"]["hospital_id"]

        # Dynamically discover another hospital
        with manager.lock:
            rt_alt_hosp = None
            for h in sim.state.hospitals.values():
                if h.hospital_id != orig_rt_hosp and not h.is_full and h.available_beds > 5:
                    rt_alt_hosp = h.hospital_id
                    break

        # Concurrently perform manual redirection
        t0 = time.perf_counter()
        apply_rt = client.post(
            f"/redirect/apply/{rt_inc_id}",
            json={"target_hospital_id": rt_alt_hosp, "reason": "Concurrent operator reroute"},
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0

        assert apply_rt.status_code == 200
        assert apply_rt.json()["new_hospital"] == rt_alt_hosp

        # Let simulation run a few more ticks
        time.sleep(0.2)

        # Stop simulation
        client.post("/simulation/realtime/stop")

        # Verify state is consistent and not corrupted
        with manager.lock:
            assert sim.state.incidents[rt_inc_id].hospital_id == rt_alt_hosp
            assert sim.state.incidents[rt_inc_id].status == "REDIRECTED"
        assert manager.is_realtime_running is False
        print(f"  -> PASS: Concurrent manual redirection completed in {latency_ms:.2f}ms without deadlocks.")

        # ------------------------------------------------------
        # TEST 13: Zero Browser Dialogs Anywhere in frontend/
        # ------------------------------------------------------
        print("\n[TEST 13] Auditing frontend/ codebase for zero prompt(), alert(), or confirm()...")
        frontend_dir = ROOT / "frontend"
        dialog_regex = re.compile(r"\b(window\.)?(alert|prompt|confirm)\s*\(")

        violations = []
        for file_path in frontend_dir.rglob("*"):
            if file_path.suffix in [".js", ".html"] and "vendor" not in file_path.parts:
                text = file_path.read_text(encoding="utf-8")
                # Remove single-line comments before checking
                lines = text.splitlines()
                for line_no, line in enumerate(lines, start=1):
                    clean_line = line.strip()
                    if clean_line.startswith("//") or clean_line.startswith("*"):
                        continue
                    if dialog_regex.search(clean_line):
                        violations.append(f"{file_path.relative_to(ROOT)}:{line_no} -> {clean_line}")

        assert len(violations) == 0, f"Found browser dialog violations:\n" + "\n".join(violations)
        print("  -> PASS: Confirmed 0 occurrences of prompt(), alert(), or confirm() in frontend/.")

        # Reset simulator
        client.post("/simulation/reset")

    print("\n" + "=" * 70)
    print("ALL M6 ADVANCED COMMAND CENTER TESTS PASSED!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_m6_tests()
