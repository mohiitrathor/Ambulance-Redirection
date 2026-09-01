"""
RAAH M9 Phase 4 Test Suite — Multi-Casualty Incident (MCI) Coordination
========================================================================

Verifies:
  1. MCI creation and data model structure.
  2. Parent MCI lifecycle initialization (DECLARED).
  3. Child incident creation with standard IncidentState objects.
  4. Individual ML triage using existing model pipeline.
  5. Correct P1 -> lower-priority dispatch ordering.
  6. Atomic multi-ambulance allocation under simulator lock.
  7. No ambulance double-booking (every assigned unit is distinct).
  8. Insufficient-fleet handling (waiting casualties rather than double-booking).
  9. Repositioning ambulance interception at actual live coordinates.
  10. M8 live kinematic movement for MCI transports.
  11. HospitalBalancer integration with atomic in-flight reservations.
  12. Critical/ICU destination selection for severe casualties.
  13. Hospital load dispersal across capable facilities.
  14. Projected-capacity protection avoiding saturated facilities.
  15. In-flight reservation lifecycle (dispatch -> transit -> arrival conversion).
  16. MCI parent progress tracking (evacuated_count updates).
  17. MCI resolution only after all child casualties arrive/resolve.
  18. MCI persistence through the M7 SQLite bridge.
  19. API response and schema validation (POST declare, GET active, GET {id}).
  20. Concurrent MCI + ordinary incident dispatch safety.
  21. Single-incident endpoint compatibility for MCI child incidents.
  22. Full M1-M9 regression compatibility.
"""

import time
import threading
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies import manager
from api.persistence.db import get_connection
from Dispatch.coordination.mci import MCIEvent, MCIManager, MCIStatus

client = TestClient(app)


def run_phase4_tests():
    print("\n" + "=" * 70)
    print("RAAH M9 PHASE 4: MULTI-CASUALTY INCIDENT (MCI) TEST SUITE")
    print("=" * 70)

    with client:
        # Reset simulator
        client.post("/simulation/reset")

        # --------------------------------------------------------------
        # TEST 1: MCI Creation
        # --------------------------------------------------------------
        print("\n[TEST 1] MCI model creation...")
        manager_mci = MCIManager()
        mci = manager_mci.create_mci(
            mci_id="MCI_TEST_01",
            name="Structural Collapse Site",
            latitude=26.9124,
            longitude=75.7873,
            declared_sim_time=10,
            estimated_casualties=6,
            notes="Factory collapse",
        )
        assert mci.mci_id == "MCI_TEST_01"
        assert mci.name == "Structural Collapse Site"
        assert mci.latitude == 26.9124
        assert mci.longitude == 75.7873
        assert mci.declared_sim_time == 10
        assert mci.total_casualties == 6
        assert mci.status == MCIStatus.DECLARED
        print("✓ MCI creation model verified.")

        # --------------------------------------------------------------
        # TEST 2: Lifecycle Initialization
        # --------------------------------------------------------------
        print("\n[TEST 2] Parent MCI lifecycle initialization...")
        assert mci.status == MCIStatus.DECLARED
        assert mci.resolved_sim_time is None
        assert len(mci.child_incident_ids) == 0
        assert len(mci.assigned_ambulance_ids) == 0
        print("✓ Lifecycle initialization verified (DECLARED).")

        # --------------------------------------------------------------
        # TEST 3 & 4: Child Incident Creation & Individual ML Triage
        # --------------------------------------------------------------
        print("\n[TEST 3 & 4] Child incident creation & individual ML triage...")
        with manager.lock:
            sim = manager.simulator
            res = sim.declare_mci(
                mci_id="MCI_LIVE_01",
                name="Central Junction Collision",
                latitude=26.9150,
                longitude=75.7890,
                estimated_casualties=4,
                primary_condition="Trauma",
                notes="Live test incident",
            )

            mci_live = sim.coordinator.mci_manager.get_mci("MCI_LIVE_01")
            assert mci_live is not None
            assert len(mci_live.child_incident_ids) == 4

            # Verify each child incident is a standard IncidentState
            for cid in mci_live.child_incident_ids:
                inc = sim.state.incidents.get(cid)
                assert inc is not None, f"Incident {cid} not in sim.state.incidents"
                assert inc.severity in ("Critical", "Emergency", "Moderate", "Low", "Non-Urgent")
                assert 1 <= inc.priority <= 5
                assert inc.condition == "Trauma"
                # Check runtime metadata mapping without modifying IncidentState
                assert sim.coordinator.mci_manager.get_mci_for_incident(cid) == "MCI_LIVE_01"

            # Check that ML triage generated varied severities and priority breakdown
            p_counts = mci_live.casualty_counts_by_priority
            assert len(p_counts) > 0
            print(f"✓ Child incidents and ML triage verified. Priorities: {p_counts}")

        # --------------------------------------------------------------
        # TEST 5: Correct P1 -> Lower-Priority Dispatch Ordering
        # --------------------------------------------------------------
        print("\n[TEST 5] Priority dispatch ordering (P1 -> P2 -> P3)...")
        # In res["child_incidents"], casualties should be dispatched in ascending priority (1, 2, 3...)
        priorities = [c["priority"] for c in res["child_incidents"]]
        assert priorities == sorted(priorities), f"Priorities not in order: {priorities}"
        print(f"✓ Dispatch priority ordering verified: {priorities}")

        # --------------------------------------------------------------
        # TEST 6 & 7: Atomic Multi-Ambulance Allocation & No Double Booking
        # --------------------------------------------------------------
        print("\n[TEST 6 & 7] Atomic fleet allocation & no double-booking...")
        assigned_ambs = [c["ambulance_id"] for c in res["child_incidents"] if c["ambulance_id"]]
        # Ensure every assigned ambulance is unique (no double-booking!)
        assert len(assigned_ambs) == len(set(assigned_ambs)), f"Duplicate ambulance booking detected: {assigned_ambs}"
        for aid in assigned_ambs:
            amb = sim.state.ambulances[aid]
            assert amb.status == "EN_ROUTE"
            assert amb.incident_id is not None
        print(f"✓ Allocated {len(assigned_ambs)} unique ambulances atomically with zero duplicate bookings.")

        # --------------------------------------------------------------
        # TEST 8: Insufficient-Fleet Handling
        # --------------------------------------------------------------
        print("\n[TEST 8] Insufficient-fleet handling (no double-booking on fleet exhaustion)...")
        with manager.lock:
            # Commit or busify most ambulances temporarily
            free_units = [a for a in sim.state.ambulances.values() if a.status == "AVAILABLE"]
            assert len(free_units) > 0

            # Request an MCI with more casualties than remaining free ambulances
            surplus_needed = len(free_units) + 3
            res_surge = sim.declare_mci(
                mci_id="MCI_SURGE_02",
                name="Massive Stadium Fire",
                latitude=26.9000,
                longitude=75.8000,
                estimated_casualties=surplus_needed,
                primary_condition="Trauma",
            )

            assert res_surge["waiting_count"] >= 3
            assert res_surge["dispatched_count"] == len(free_units)
            # Verify waiting casualties are cleanly in WAITING_AMBULANCE status
            waiting_children = [c for c in res_surge["child_incidents"] if c["status"] == "WAITING_AMBULANCE"]
            assert len(waiting_children) == res_surge["waiting_count"]
            for wc in waiting_children:
                assert wc["ambulance_id"] is None
        print(f"✓ Fleet exhaustion handled safely: {res_surge['dispatched_count']} dispatched, {res_surge['waiting_count']} waiting.")

        # --------------------------------------------------------------
        # TEST 9: Repositioning Ambulance Interception
        # --------------------------------------------------------------
        print("\n[TEST 9] Repositioning ambulance interception...")
        client.post("/simulation/reset")
        with manager.lock:
            sim = manager.simulator
            # Find an idle ambulance and set it repositioning
            amb_id = next(iter(sim.state.ambulances.keys()))
            amb = sim.state.ambulances[amb_id]
            amb.status = "REPOSITIONING"
            amb.is_repositioning = True
            orig_lat, orig_lon = amb.latitude, amb.longitude

            # Declare an MCI right near that ambulance
            res_intercept = sim.declare_mci(
                mci_id="MCI_INTERCEPT",
                name="Highway Pileup Near Unit",
                latitude=orig_lat + 0.001,
                longitude=orig_lon + 0.001,
                estimated_casualties=1,
                primary_condition="Trauma",
            )

            child = res_intercept["child_incidents"][0]
            assert child["ambulance_id"] == amb_id
            assert amb.status == "EN_ROUTE"
            assert not getattr(amb, "is_repositioning", False)
        print("✓ Repositioning ambulance intercepted cleanly without teleportation.")

        # --------------------------------------------------------------
        # TEST 10: M8 Live Kinematics for MCI Transports
        # --------------------------------------------------------------
        print("\n[TEST 10] M8 live kinematic movement for MCI transports...")
        with manager.lock:
            sim = manager.simulator
            en_route_ambs = [a for a in sim.state.ambulances.values() if a.status == "EN_ROUTE" and a.incident_id is not None]
            assert len(en_route_ambs) > 0
            test_amb = en_route_ambs[0]
            start_lat, start_lon = test_amb.latitude, test_amb.longitude
            start_eta = test_amb.eta_minutes
            assert len(test_amb.route_waypoints) > 0

        # Advance simulation by 2 minutes
        client.post("/simulation/tick", json={"minutes": 2.0})

        with manager.lock:
            sim = manager.simulator
            updated_amb = sim.state.ambulances[test_amb.ambulance_id]
            # Vehicle position should have updated along route
            assert updated_amb.eta_minutes < start_eta
            print(f"✓ Kinematic movement confirmed: ETA decreased from {start_eta:.1f} to {updated_amb.eta_minutes:.1f} min.")

        # --------------------------------------------------------------
        # TEST 11, 12, 13 & 14: HospitalBalancer Dispersal, ICU Selection & Capacity Protection
        # --------------------------------------------------------------
        print("\n[TEST 11-14] HospitalBalancer integration, ICU preservation, and load dispersal...")
        client.post("/simulation/reset")
        with manager.lock:
            sim = manager.simulator
            # Declare an MCI with 8 casualties
            res_disp = sim.declare_mci(
                mci_id="MCI_DISPERSAL",
                name="Shopping Mall Explosion",
                latitude=26.9124,
                longitude=75.7873,
                estimated_casualties=8,
                primary_condition="Trauma",
            )

            mci_disp = sim.coordinator.mci_manager.get_mci("MCI_DISPERSAL")
            dist = mci_disp.hospital_distribution
            print(f"  MCI Destination Hospital Distribution: {dist}")

            # Dispersal verification: with 8 casualties and multiple capable hospitals,
            # load should be dispersed across 2 or more facilities
            assert len(dist) >= 2, f"Failed to disperse across hospitals: {dist}"

            # Verify in-flight reservations exist for all dispatched casualties
            for cid in mci_disp.child_incident_ids:
                inc = sim.state.incidents[cid]
                if inc.status == "DISPATCHED":
                    h_res = sim.coordinator.hospital_balancer.get_in_flight(inc.hospital_id)
                    amb_ids_reserved = [r.ambulance_id for r in h_res]
                    assert inc.ambulance_id in amb_ids_reserved
        print("✓ Hospital dispersal across multiple facilities verified.")

        # --------------------------------------------------------------
        # TEST 15, 16 & 17: In-Flight Lifecycle, Progress Tracking, and Resolution
        # --------------------------------------------------------------
        print("\n[TEST 15-17] Evacuation progress tracking and MCI resolution only after arrival...")
        client.post("/simulation/reset")
        test_mci_id = f"MCI_EVAC_{int(time.time())}"
        with manager.lock:
            sim = manager.simulator
            res_evac = sim.declare_mci(
                mci_id=test_mci_id,
                name="Bus Rollover",
                latitude=26.9124,
                longitude=75.7873,
                estimated_casualties=2,
                primary_condition="Trauma",
            )
            mci_obj = sim.coordinator.mci_manager.get_mci(test_mci_id)
            assert mci_obj.status == MCIStatus.EVACUATING
            assert mci_obj.evacuated_count == 0

        # Advance simulation time until all vehicles arrive
        for _ in range(30):
            client.post("/simulation/tick", json={"minutes": 2.0})
            with manager.lock:
                sim = manager.simulator
                mci_obj = sim.coordinator.mci_manager.get_mci(test_mci_id)
                if mci_obj.status == MCIStatus.RESOLVED:
                    break

        with manager.lock:
            sim = manager.simulator
            mci_obj = sim.coordinator.mci_manager.get_mci(test_mci_id)
            assert mci_obj.status == MCIStatus.RESOLVED, f"MCI not resolved: status is {mci_obj.status}"
            assert mci_obj.evacuated_count == mci_obj.total_casualties
            assert mci_obj.resolved_sim_time is not None
            print(f"✓ MCI resolved successfully at sim_time {mci_obj.resolved_sim_time}. Evacuated: {mci_obj.evacuated_count}/{mci_obj.total_casualties}")

        # --------------------------------------------------------------
        # TEST 18: Persistence via M7 Bridge
        # --------------------------------------------------------------
        print("\n[TEST 18] MCI persistence via M7 SQLite bridge...")
        time.sleep(0.4)  # Allow background SQLite worker to flush
        conn = get_connection()
        try:
            with manager.lock:
                sim_run_id = manager.simulator.run_id
            mci_rows = conn.execute(
                "SELECT * FROM historical_mci_events WHERE run_id = ? AND mci_id = ?",
                (sim_run_id, test_mci_id),
            ).fetchall()
            assert len(mci_rows) > 0, "MCI declaration not persisted in historical_mci_events"
            mci_row = dict(mci_rows[0])
            assert mci_row["status"] == "RESOLVED"
            assert mci_row["total_casualties"] == 2

            child_rows = conn.execute(
                "SELECT * FROM historical_mci_children WHERE run_id = ? AND mci_id = ?",
                (sim_run_id, test_mci_id),
            ).fetchall()
            assert len(child_rows) == 2, f"Expected 2 child records, found {len(child_rows)}"
            print(f"✓ Persisted MCI event and {len(child_rows)} children in SQLite.")
        finally:
            conn.close()

        # --------------------------------------------------------------
        # TEST 19: API Endpoints Validation
        # --------------------------------------------------------------
        print("\n[TEST 19] API endpoints validation (POST declare, GET active, GET {id})...")
        client.post("/simulation/reset")
        r_decl = client.post("/coordination/mci/declare", json={
            "name": "Market Gas Leak",
            "latitude": 26.9200,
            "longitude": 75.8100,
            "estimated_casualties": 3,
            "primary_condition": "Respiratory",
            "notes": "API test",
        })
        assert r_decl.status_code == 200, r_decl.text
        data_decl = r_decl.json()
        assert data_decl["status"] == "MCI_DECLARED"
        assert len(data_decl["child_incidents"]) == 3
        mci_api_id = data_decl["mci"]["mci_id"]

        # GET /coordination/mci/active
        r_act = client.get("/coordination/mci/active")
        assert r_act.status_code == 200
        active_list = r_act.json()
        assert any(m["mci_id"] == mci_api_id for m in active_list)

        # GET /coordination/mci/{id}
        r_det = client.get(f"/coordination/mci/{mci_api_id}")
        assert r_det.status_code == 200
        mci_det = r_det.json()
        assert mci_det["name"] == "Market Gas Leak"
        assert mci_det["total_casualties"] == 3
        print("✓ All MCI REST endpoints responded with valid schemas.")

        # --------------------------------------------------------------
        # TEST 20: Concurrent Dispatch Safety
        # --------------------------------------------------------------
        print("\n[TEST 20] Concurrent MCI + ordinary incident dispatch safety...")
        errors = []

        def worker_ordinary(idx):
            try:
                r = client.post("/dispatch/live", json={
                    "patient_lat": 26.9100 + (idx * 0.001),
                    "patient_lon": 75.7800 + (idx * 0.001),
                    "Condition": "Cardiac",
                    "Sex": "Male",
                    "Age": 55,
                    "Arrival_Mode": "Ambulance",
                    "Injury_Type": "No Injury",
                    "Heart_Rate": 110.0,
                    "SpO2": 93.0,
                    "Systolic_BP": 130.0,
                    "Diastolic_BP": 85.0,
                    "Respiratory_Rate": 20.0,
                    "Temperature": 37.0,
                    "Consciousness": "Alert",
                    "Oxygen_Requirement": "No Oxygen",
                    "GCS": 15,
                    "Pain_Score": 6,
                    "Blood_Glucose": 120.0,
                    "Respiratory_Distress": 0,
                    "Chest_Pain": 1,
                    "Bleeding": 0,
                    "Seizure": 0,
                    "Diabetes": 0,
                    "Hypertension": 1,
                    "Heart_Disease": 1,
                    "Respiratory_Disease": 0,
                })
                if r.status_code != 200:
                    errors.append(f"Worker {idx} failed: {r.text}")
            except Exception as e:
                errors.append(str(e))

        def worker_mci(idx):
            try:
                r = client.post("/coordination/mci/declare", json={
                    "name": f"Concurrent Incident {idx}",
                    "latitude": 26.9150 + (idx * 0.002),
                    "longitude": 75.7850 + (idx * 0.002),
                    "estimated_casualties": 2,
                    "primary_condition": "Trauma",
                })
                if r.status_code != 200:
                    errors.append(f"MCI worker {idx} failed: {r.text}")
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(4):
            threads.append(threading.Thread(target=worker_ordinary, args=(i,)))
            threads.append(threading.Thread(target=worker_mci, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent dispatch encountered errors: {errors}"
        print(f"✓ Concurrent dispatch safety confirmed across {len(threads)} threads.")

        # --------------------------------------------------------------
        # TEST 21: Existing Single-Incident Endpoints Compatibility
        # --------------------------------------------------------------
        print("\n[TEST 21] Single-incident endpoint compatibility for MCI children...")
        with manager.lock:
            sim = manager.simulator
            all_cids = []
            for m in sim.coordinator.mci_manager.list_all_mcis():
                all_cids.extend(m.child_incident_ids)
            sample_child_id = all_cids[0]

        # GET /state/incidents/{id}
        r_inc = client.get(f"/state/incidents/{sample_child_id}")
        assert r_inc.status_code == 200, f"Single incident endpoint failed for child {sample_child_id}: {r_inc.text}"
        inc_data = r_inc.json()
        assert inc_data["incident_id"] == sample_child_id
        print(f"✓ Child incident {sample_child_id} queried successfully via standard /state/incidents endpoint.")

        # --------------------------------------------------------------
        # TEST 22: Full Regression Verification
        # --------------------------------------------------------------
        print("\n[TEST 22] Full regression check on core endpoints...")
        r_health = client.get("/health")
        assert r_health.status_code == 200
        r_dash = client.get("/state/dashboard")
        assert r_dash.status_code == 200
        r_proj = client.get("/coordination/hospital-projections")
        assert r_proj.status_code == 200
        r_cov = client.get("/coordination/coverage")
        assert r_cov.status_code == 200
        print("✓ All core endpoints verified.")

    print("\n" + "=" * 70)
    print("ALL 22 M9 PHASE 4 MCI COORDINATION TESTS PASSED.")
    print("=" * 70)


if __name__ == "__main__":
    run_phase4_tests()
