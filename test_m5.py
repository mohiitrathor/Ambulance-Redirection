"""
RAAH Milestone 5 Verification Test Suite
========================================

Tests:
  A. Sequential live dispatch:
     Dispatch Incident A. Confirm ambulance is EN_ROUTE.
     Dispatch Incident B (which shares candidate fleet).
     Assert Incident B receives a different ambulance (no double-booking).
  B. Hospital saturation avoidance:
     Mark selected hospital full in live state.
     Dispatch another incident.
     Assert full hospital is not selected.
  C. Critical ICU constraint:
     Remove ICU availability from candidate hospital in live state.
     Dispatch a Critical incident.
     Assert that hospital is not selected.
  D. Custom intake (POST /dispatch/live):
     Submit valid request using the actual 24-feature ML model contract.
     Verify:
     - ML severity prediction
     - priority
     - ambulance assignment
     - hospital assignment
     - live state mutation
  E. Invalid intake:
     Verify invalid categorical values, missing required fields,
     out-of-range vitals, and invalid coordinates are rejected with HTTP 422.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from api.main import app
from api.dependencies import manager


def run_m5_tests():
    print()
    print("=" * 70)
    print("RAAH M5: LIVE STATE CONVERGENCE & CUSTOM INTAKE TEST SUITE")
    print("=" * 70)

    with TestClient(app) as client:

        # Reset simulator to pristine state
        client.post("/simulation/reset")

        # ------------------------------------------------------
        # TEST A: Sequential Live Dispatch (No Double Booking)
        # ------------------------------------------------------
        print("\n[TEST A] Sequential live dispatch (ambulance double-booking guard)...")
        # Incident 1
        res1 = client.post("/dispatch/1")
        assert res1.status_code == 200
        data1 = res1.json()
        amb_id_1 = data1["ambulance"]["ambulance_id"]
        print(f"  -> Dispatched Incident 1: assigned {amb_id_1}")

        # Verify ambulance is EN_ROUTE in live state
        sim = manager.simulator
        with manager.lock:
            assert sim.state.ambulances[amb_id_1].status == "EN_ROUTE"
            assert sim.state.ambulances[amb_id_1].incident_id == 1

        # Incident 11 shares nearby Jaipur coordinates and similar scenarios
        # We will dispatch incident 11 and verify it gets a different ambulance
        res2 = client.post("/dispatch/11")
        assert res2.status_code == 200
        data2 = res2.json()
        amb_id_2 = data2["ambulance"]["ambulance_id"]
        print(f"  -> Dispatched Incident 11: assigned {amb_id_2}")

        assert amb_id_1 != amb_id_2, f"Double-booking detected! Both received {amb_id_1}"
        with manager.lock:
            assert sim.state.ambulances[amb_id_2].status == "EN_ROUTE"
            assert sim.state.ambulances[amb_id_2].incident_id == 11
        print("  -> PASS: Incident 1 and Incident 11 assigned distinct ambulances.")

        # ------------------------------------------------------
        # TEST B: Hospital Saturation Bypass
        # ------------------------------------------------------
        print("\n[TEST B] Live hospital saturation bypass...")
        # Check what hospital incident 100 would choose if unconstrained
        # Mark that hospital full in live state
        hosp_1 = data1["hospital"]["hospital_id"]
        with manager.lock:
            sim.state.hospitals[hosp_1].current_load = sim.state.hospitals[hosp_1].capacity
            assert sim.state.hospitals[hosp_1].is_full is True

        # Now dispatch incident 2
        res3 = client.post("/dispatch/2")
        assert res3.status_code == 200
        data3 = res3.json()
        hosp_3 = data3["hospital"]["hospital_id"]
        print(f"  -> Hospital {hosp_1} marked FULL. Incident 2 assigned to {hosp_3}")
        assert hosp_3 != hosp_1, f"Live full hospital {hosp_1} was erroneously assigned!"
        print("  -> PASS: Saturated hospital excluded from new live dispatch.")

        # Reset simulator
        client.post("/simulation/reset")

        # ------------------------------------------------------
        # TEST C: Critical ICU Constraint
        # ------------------------------------------------------
        print("\n[TEST C] Critical ICU constraint in live state...")
        # Dispatch incident 50 (Critical severity in synthetic dataset)
        # Find which hospital is assigned
        res_crit = client.post("/dispatch/50")
        assert res_crit.status_code == 200
        crit_data = res_crit.json()
        crit_hosp = crit_data["hospital"]["hospital_id"]
        print(f"  -> Incident 50 (Critical) assigned hospital: {crit_hosp}")

        # Reset and exhaust ICU on that hospital
        client.post("/simulation/reset")
        with manager.lock:
            sim = manager.simulator
            sim.state.hospitals[crit_hosp].current_icu_load = sim.state.hospitals[crit_hosp].icu_capacity
            assert sim.state.hospitals[crit_hosp].available_icu == 0

        # Dispatch incident 50 again
        res_crit2 = client.post("/dispatch/50")
        assert res_crit2.status_code == 200
        crit_data2 = res_crit2.json()
        crit_hosp2 = crit_data2["hospital"]["hospital_id"]
        print(f"  -> Hospital {crit_hosp} zero ICU. Incident 50 assigned to: {crit_hosp2}")
        assert crit_hosp2 != crit_hosp, f"Hospital {crit_hosp} with 0 ICU was selected for Critical incident!"
        print("  -> PASS: Hospital with exhausted ICU excluded for Critical incident.")

        # ------------------------------------------------------
        # TEST D: Custom Emergency Call Intake (POST /dispatch/live)
        # ------------------------------------------------------
        print("\n[TEST D] Custom dynamic emergency call intake (POST /dispatch/live)...")
        valid_custom_call = {
            # 6 Categoricals
            "Sex": "Male",
            "Condition": "Cardiac",
            "Oxygen_Requirement": "Oxygen Mask",
            "Consciousness": "Drowsy",
            "Injury_Type": "No Injury",
            "Arrival_Mode": "Ambulance",
            # 18 Numerics
            "Age": 68,
            "Heart_Rate": 138.0,
            "SpO2": 84.5,
            "Systolic_BP": 85.0,
            "Diastolic_BP": 50.0,
            "Respiratory_Rate": 34.0,
            "Temperature": 37.8,
            "GCS": 11,
            "Pain_Score": 9,
            "Blood_Glucose": 220.0,
            "Respiratory_Distress": 1,
            "Chest_Pain": 1,
            "Bleeding": 0,
            "Seizure": 0,
            "Diabetes": 1,
            "Hypertension": 1,
            "Heart_Disease": 1,
            "Respiratory_Disease": 0,
            # Coordinates
            "patient_lat": 26.9124,
            "patient_lon": 75.7873,
        }

        live_res = client.post("/dispatch/live", json=valid_custom_call)
        assert live_res.status_code == 200, f"Live dispatch failed: {live_res.text}"
        live_data = live_res.json()

        assert live_data["status"] == "DISPATCH_RECOMMENDED"
        assert live_data["incident_id"] >= 100000
        assert live_data["patient"]["predicted_severity"] in ["Critical", "Emergency", "Moderate", "Low", "Non-Urgent"]
        assert live_data["patient"]["priority"].startswith("P")
        assert live_data["ambulance"]["ambulance_id"].startswith("AMB_")
        assert live_data["ambulance"]["eta_minutes"] > 0
        assert live_data["hospital"]["hospital_id"].startswith("HOSP_")

        custom_id = live_data["incident_id"]
        custom_amb = live_data["ambulance"]["ambulance_id"]
        custom_hosp = live_data["hospital"]["hospital_id"]
        print(f"  -> Custom Call Intake Success:")
        print(f"     Incident ID:        {custom_id}")
        print(f"     ML Severity:        {live_data['patient']['predicted_severity']} ({live_data['patient']['priority']})")
        print(f"     Confidence:         {live_data['patient']['confidence']}")
        print(f"     Assigned Ambulance: {custom_amb} (ETA: {live_data['ambulance']['eta_minutes']} min)")
        print(f"     Assigned Hospital:  {custom_hosp} (Distance: {live_data['hospital']['distance_km']} km)")

        # Verify live state mutated
        with manager.lock:
            sim = manager.simulator
            assert custom_id in sim.state.incidents
            assert sim.state.incidents[custom_id].status == "DISPATCHED"
            assert sim.state.ambulances[custom_amb].status == "EN_ROUTE"
            assert sim.state.ambulances[custom_amb].incident_id == custom_id
        print("  -> PASS: Custom intake triaged via ML and live state mutated successfully.")

        # ------------------------------------------------------
        # TEST E: Input Validation & Contract Rejection
        # ------------------------------------------------------
        print("\n[TEST E] Input validation and malformed intake rejection...")

        # E1: Invalid categorical value
        bad_cat = dict(valid_custom_call)
        bad_cat["Condition"] = "SpaceSickness"
        r_bad_cat = client.post("/dispatch/live", json=bad_cat)
        assert r_bad_cat.status_code == 422
        print("  -> PASS: Invalid categorical value ('SpaceSickness') rejected with 422.")

        # E2: Missing required field
        missing_field = dict(valid_custom_call)
        del missing_field["Heart_Rate"]
        r_missing = client.post("/dispatch/live", json=missing_field)
        assert r_missing.status_code == 422
        print("  -> PASS: Missing required numeric field ('Heart_Rate') rejected with 422.")

        # E3: Out of range vitals
        bad_vitals = dict(valid_custom_call)
        bad_vitals["SpO2"] = 150.0 # oxygen sat cannot exceed 100%
        r_vitals = client.post("/dispatch/live", json=bad_vitals)
        assert r_vitals.status_code == 422
        print("  -> PASS: Out-of-bounds vitals (SpO2=150) rejected with 422.")

        # E4: Out of range coordinates
        bad_coords = dict(valid_custom_call)
        bad_coords["patient_lat"] = 120.0 # lat cannot exceed 90 degrees
        r_coords = client.post("/dispatch/live", json=bad_coords)
        assert r_coords.status_code == 422
        print("  -> PASS: Invalid coordinates (lat=120) rejected with 422.")

        # Reset simulator
        client.post("/simulation/reset")

    print("\n" + "=" * 70)
    print("ALL M5 LIVE CONVERGENCE & CUSTOM INTAKE TESTS PASSED!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_m5_tests()
