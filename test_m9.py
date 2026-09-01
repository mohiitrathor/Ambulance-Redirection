"""
RAAH M9 Test Suite — Dynamic Fleet Repositioning & Foundation
============================================================

Verifies:
  1. Coverage calculation and 6-zone scoring.
  2. Advisory repositioning recommendations endpoint.
  3. Reposition execution for an available surplus ambulance.
  4. Rejection of EN_ROUTE ambulance repositioning.
  5. Rejection of BUSY ambulance repositioning.
  6. Rejection of MAINTENANCE ambulance repositioning.
  7. Deficit source zone protection (cannot deplete last unit).
  8. Status updated to REPOSITIONING and is_repositioning set.
  9. M8 multi-point route generated with route_type REPOSITIONING.
  10. Vehicle kinematics progression during advance_time().
  11. Vehicle arrives at target staging post exactly.
  12. Vehicle returns cleanly to AVAILABLE.
  13. Active route and repositioning metadata cleaned up.
  14. Emergency call interception of a repositioning unit.
  15. Intercepted unit routes patient transport from CURRENT coordinates.
  16. No spatial teleportation back to origin depot occurs.
  17. Cancel repositioning endpoint works.
  18. Invalid cancellation returns HTTP 404 / 409.
  19. Asynchronous historical persistence of reposition events.
  20. Existing M7 historical analytics & M8 kinematics regression.
"""

import time
from fastapi.testclient import TestClient
from api.main import app
from api.dependencies import manager
from api.persistence.db import get_connection
from routing import routing_engine

client = TestClient(app)


def run_m9_tests():
    print("\n" + "=" * 70)
    print("RAAH M9: DYNAMIC FLEET REPOSITIONING & FOUNDATION TEST SUITE")
    print("=" * 70)

    with client:
        # Reset simulation session
        client.post("/simulation/reset")

        # --------------------------------------------------------------
        # TEST 1: Coverage Calculation across 6 Zones
        # --------------------------------------------------------------
        print("\n[TEST 1] Coverage calculation across 6 zones...")
        cov_res = client.get("/coordination/coverage")
        assert cov_res.status_code == 200, f"Coverage failed: {cov_res.text}"
        cov_data = cov_res.json()
        assert len(cov_data["zones"]) == 6
        expected_zones = {
            "JAIPUR_CENTRAL", "JAIPUR_NORTH", "JAIPUR_WEST",
            "JAIPUR_SOUTH", "JAIPUR_EAST", "JAIPUR_SUBURBAN"
        }
        assert set(cov_data["zones"].keys()) == expected_zones
        print(f"  ✓ 6 zones verified (deficit={cov_data['deficit_count']}, surplus={cov_data['surplus_count']})")

        # --------------------------------------------------------------
        # TEST 2: Advisory Reposition Recommendations Endpoint
        # --------------------------------------------------------------
        print("\n[TEST 2] Advisory reposition recommendations endpoint...")
        rec_res = client.get("/coordination/reposition/recommendations")
        assert rec_res.status_code == 200, f"Recs failed: {rec_res.text}"
        recs = rec_res.json()
        assert isinstance(recs, list)
        print(f"  ✓ Recommendations endpoint returned {len(recs)} advisories")

        # --------------------------------------------------------------
        # TEST 3: Available Surplus Ambulance Can Be Repositioned
        # --------------------------------------------------------------
        print("\n[TEST 3] Repositioning an available surplus ambulance...")
        with manager.lock:
            sim = manager.simulator
            # Find an available ambulance
            avail_id = next(
                aid for aid, amb in sim.state.ambulances.items()
                if amb.status == "AVAILABLE"
            )
            amb_start_pos = (sim.state.ambulances[avail_id].latitude, sim.state.ambulances[avail_id].longitude)

        # Target staging post in North sector: (26.9600, 75.7850)
        target_lat, target_lon = 26.9600, 75.7850
        repo_res = client.post("/coordination/reposition/execute", json={
            "ambulance_id": avail_id,
            "target_lat": target_lat,
            "target_lon": target_lon,
            "reason": "DEFICIT_REBALANCING"
        })
        assert repo_res.status_code == 200, f"Execution failed: {repo_res.text}"
        repo_data = repo_res.json()
        assert repo_data["status"] == "REPOSITIONING"
        assert repo_data["ambulance_id"] == avail_id
        assert repo_data["route_distance_km"] > 0
        assert repo_data["eta_minutes"] > 0
        assert len(repo_data["route_waypoints"]) > 1
        print(f"  ✓ Repositioning started: {avail_id} -> {repo_data['target_zone']} (ETA: {repo_data['eta_minutes']}m)")

        # --------------------------------------------------------------
        # TEST 4: Reject EN_ROUTE Ambulance Repositioning
        # --------------------------------------------------------------
        print("\n[TEST 4] Rejecting EN_ROUTE ambulance repositioning...")
        # Dispatch an incident to create an EN_ROUTE ambulance
        disp_res = client.post("/dispatch/1")
        assert disp_res.status_code == 200
        with manager.lock:
            en_route_amb_id = sim.state.incidents[1].ambulance_id
            assert sim.state.ambulances[en_route_amb_id].status == "EN_ROUTE"

        bad_repo = client.post("/coordination/reposition/execute", json={
            "ambulance_id": en_route_amb_id,
            "target_lat": 26.90,
            "target_lon": 75.80,
        })
        assert bad_repo.status_code == 409
        print(f"  ✓ EN_ROUTE unit {en_route_amb_id} rejected with HTTP 409")

        # --------------------------------------------------------------
        # TEST 5 & 6: Reject BUSY and MAINTENANCE Ambulance Repositioning
        # --------------------------------------------------------------
        print("\n[TEST 5 & 6] Rejecting BUSY and MAINTENANCE ambulance repositioning...")
        with manager.lock:
            busy_amb_id = next(
                aid for aid, amb in sim.state.ambulances.items()
                if aid not in (avail_id, en_route_amb_id)
            )
            sim.state.ambulances[busy_amb_id].status = "BUSY"

            maint_amb_id = next(
                aid for aid, amb in sim.state.ambulances.items()
                if aid not in (avail_id, en_route_amb_id, busy_amb_id)
            )
            sim.state.ambulances[maint_amb_id].status = "MAINTENANCE"

        busy_repo = client.post("/coordination/reposition/execute", json={
            "ambulance_id": busy_amb_id,
            "target_lat": 26.90,
            "target_lon": 75.80,
        })
        assert busy_repo.status_code == 409

        maint_repo = client.post("/coordination/reposition/execute", json={
            "ambulance_id": maint_amb_id,
            "target_lat": 26.90,
            "target_lon": 75.80,
        })
        assert maint_repo.status_code == 409
        print("  ✓ BUSY and MAINTENANCE units rejected with HTTP 409")

        # --------------------------------------------------------------
        # TEST 7: Deficit Source Zone Protection
        # --------------------------------------------------------------
        print("\n[TEST 7] Deficit source zone protection guard...")
        with manager.lock:
            # Artificially set all ambulances in JAIPUR_NORTH to BUSY except one
            north_units = [
                aid for aid, amb in sim.state.ambulances.items()
                if sim.coordinator.coverage_engine.assign_zone(amb.latitude, amb.longitude) == "JAIPUR_NORTH"
            ]
            for uid in north_units[1:]:
                sim.state.ambulances[uid].status = "BUSY"
            sole_north_id = north_units[0]
            sim.state.ambulances[sole_north_id].status = "AVAILABLE"

        deplete_repo = client.post("/coordination/reposition/execute", json={
            "ambulance_id": sole_north_id,
            "target_lat": 26.8550,
            "target_lon": 75.7700,  # South zone
        })
        assert deplete_repo.status_code == 409
        assert "DEFICIT" in deplete_repo.json()["detail"]
        print("  ✓ Protected deficit zone from depleting its sole available ambulance")

        # --------------------------------------------------------------
        # TEST 8 & 9: State Flags & M8 Route Generation
        # --------------------------------------------------------------
        print("\n[TEST 8 & 9] Repositioning state flags and M8 route generation...")
        with manager.lock:
            amb_repo = sim.state.ambulances[avail_id]
            assert amb_repo.status == "REPOSITIONING"
            assert amb_repo.is_repositioning is True
            assert amb_repo.reposition_target is not None
            assert avail_id in sim.active_routes
            route = sim.active_routes[avail_id]
            assert route.route_type == "REPOSITIONING"
            assert len(route.waypoints) >= 6
        print(f"  ✓ Ambulance {avail_id} status=REPOSITIONING, route_type=REPOSITIONING")

        # --------------------------------------------------------------
        # TEST 10: Kinematics Progression During advance_time()
        # --------------------------------------------------------------
        print("\n[TEST 10] Kinematic movement during simulation ticks...")
        with manager.lock:
            p_initial = (amb_repo.latitude, amb_repo.longitude)
            eta_initial = amb_repo.eta_minutes

        client.post("/simulation/tick?minutes=2")

        with manager.lock:
            p_moved = (amb_repo.latitude, amb_repo.longitude)
            eta_moved = amb_repo.eta_minutes

        dist_moved = routing_engine.calculate_straight_line_distance(p_initial, p_moved)
        assert dist_moved > 0.05, f"Ambulance did not physically move: {dist_moved} km"
        assert eta_moved < eta_initial, f"ETA did not decrement: {eta_moved} vs {eta_initial}"
        print(f"  ✓ Moved {dist_moved:.3f} km (ETA: {eta_initial:.1f}m -> {eta_moved:.1f}m)")

        # --------------------------------------------------------------
        # TEST 11, 12, 13: Staging Arrival & Clean Cleanup
        # --------------------------------------------------------------
        print("\n[TEST 11, 12, 13] Complete transit, staging arrival, and state cleanup...")
        # Advance clock to complete remaining transit
        client.post(f"/simulation/tick?minutes={int(eta_moved + 5)}")

        with manager.lock:
            assert amb_repo.status == "AVAILABLE"
            assert amb_repo.is_repositioning is False
            assert amb_repo.reposition_target is None
            assert amb_repo.eta_minutes is None
            assert avail_id not in sim.active_routes
            assert avail_id not in sim.repositioning_data
            # Verify coordinates match target staging post
            dest_dist = routing_engine.calculate_straight_line_distance(
                (amb_repo.latitude, amb_repo.longitude),
                (target_lat, target_lon)
            )
            assert dest_dist < 0.001, f"Did not snap to target: {dest_dist} km"
        print(f"  ✓ Unit {avail_id} arrived at staging post, snapped to destination, status=AVAILABLE")

        # --------------------------------------------------------------
        # TEST 14, 15, 16: Emergency Call Interception from Current Coordinates
        # --------------------------------------------------------------
        print("\n[TEST 14, 15, 16] Emergency call interception mid-transit...")
        # Reset and dispatch a unit on a new repositioning route
        client.post("/simulation/reset")
        with manager.lock:
            sim = manager.simulator
            inter_id = next(
                aid for aid, amb in sim.state.ambulances.items()
                if amb.status == "AVAILABLE"
            )
            origin_depot = (sim.state.ambulances[inter_id].latitude, sim.state.ambulances[inter_id].longitude)

        # Reposition toward suburban post
        client.post("/coordination/reposition/execute", json={
            "ambulance_id": inter_id,
            "target_lat": 26.7950,
            "target_lon": 75.8450,
        })

        # Advance 3 minutes so unit is in-transit away from depot
        client.post("/simulation/tick?minutes=3")

        with manager.lock:
            in_transit_pos = (sim.state.ambulances[inter_id].latitude, sim.state.ambulances[inter_id].longitude)
            assert sim.state.ambulances[inter_id].status == "REPOSITIONING"
            dist_from_depot = routing_engine.calculate_straight_line_distance(origin_depot, in_transit_pos)
            assert dist_from_depot > 0.1
            # Temporarily set other ambulances to BUSY to guarantee inter_id is the unit intercepted
            for aid, amb in sim.state.ambulances.items():
                if aid != inter_id:
                    amb.status = "BUSY"

        # Now trigger a custom emergency call very close to in_transit_pos
        live_intake = client.post("/dispatch/live", json={
            "Sex": "Male",
            "Age": 45,
            "Condition": "Trauma",
            "Arrival_Mode": "Ambulance",
            "Injury_Type": "Fracture",
            "Heart_Rate": 110.0,
            "SpO2": 95.0,
            "Systolic_BP": 140.0,
            "Diastolic_BP": 90.0,
            "Respiratory_Rate": 20.0,
            "Temperature": 37.0,
            "Consciousness": "Alert",
            "Oxygen_Requirement": "No Oxygen",
            "GCS": 15,
            "Pain_Score": 6,
            "Blood_Glucose": 110.0,
            "Respiratory_Distress": 0,
            "Chest_Pain": 0,
            "Bleeding": 0,
            "Seizure": 0,
            "Diabetes": 0,
            "Hypertension": 0,
            "Heart_Disease": 0,
            "Respiratory_Disease": 0,
            "patient_lat": in_transit_pos[0] + 0.005,
            "patient_lon": in_transit_pos[1] + 0.005,
        })
        assert live_intake.status_code == 200, f"Live intake failed: {live_intake.text}"
        intake_data = live_intake.json()
        assigned_amb_id = intake_data["ambulance"]["ambulance_id"]

        with manager.lock:
            assigned_amb = sim.state.ambulances[assigned_amb_id]
            assert assigned_amb_id == inter_id
            assert assigned_amb.status == "EN_ROUTE"
            assert getattr(assigned_amb, "is_repositioning", False) is False
            assert assigned_amb.reposition_target is None

            # Verify the route originated from current location, NOT teleported
            active_rt = sim.active_routes[assigned_amb_id]
            dist_from_transit = routing_engine.calculate_straight_line_distance(
                in_transit_pos,
                (assigned_amb.latitude, assigned_amb.longitude)
            )
            assert dist_from_transit < 0.05, "Vehicle teleported upon interception!"
            print(f"  ✓ Ambulance {inter_id} cleanly intercepted mid-transit without teleportation")

        # --------------------------------------------------------------
        # TEST 17 & 18: Reposition Cancellation
        # --------------------------------------------------------------
        print("\n[TEST 17 & 18] Operator reposition cancellation & error guards...")
        client.post("/simulation/reset")
        with manager.lock:
            sim = manager.simulator
            cancel_cand_id = next(
                aid for aid, amb in sim.state.ambulances.items()
                if amb.status == "AVAILABLE"
            )

        client.post("/coordination/reposition/execute", json={
            "ambulance_id": cancel_cand_id,
            "target_lat": 26.8620,
            "target_lon": 75.8320,
        })

        with manager.lock:
            assert sim.state.ambulances[cancel_cand_id].status == "REPOSITIONING"

        # Cancel repositioning
        cancel_res = client.post(f"/coordination/reposition/cancel/{cancel_cand_id}")
        assert cancel_res.status_code == 200
        with manager.lock:
            assert sim.state.ambulances[cancel_cand_id].status == "AVAILABLE"
            assert cancel_cand_id not in sim.active_routes
        print(f"  ✓ Cancelled repositioning for {cancel_cand_id}; status restored to AVAILABLE")

        # Attempt to cancel an idle ambulance that is not repositioning -> 409
        bad_cancel = client.post(f"/coordination/reposition/cancel/{cancel_cand_id}")
        assert bad_cancel.status_code == 409

        # Attempt to cancel a non-existent ambulance -> 404
        non_existent = client.post("/coordination/reposition/cancel/AMB_NON_EXISTENT")
        assert non_existent.status_code == 404
        print("  ✓ Non-repositioning unit rejected with 409; unknown unit rejected with 404")

        # --------------------------------------------------------------
        # TEST 19: Asynchronous Persistence to SQLite
        # --------------------------------------------------------------
        print("\n[TEST 19] Historical persistence of reposition events...")
        # Allow worker thread queue to drain
        time.sleep(0.5)
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM historical_repositions")
            repo_records = cursor.fetchone()[0]
            assert repo_records >= 1, f"Expected historical_repositions records, got {repo_records}"
            print(f"  ✓ Verified {repo_records} historical_repositions rows written asynchronously to SQLite")
        finally:
            conn.close()

        # --------------------------------------------------------------
        # TEST 20: M7 / M8 Regression Under Active Coordination
        # --------------------------------------------------------------
        print("\n[TEST 20] M7 / M8 regression check...")
        dash_res = client.get("/state/dashboard")
        assert dash_res.status_code == 200
        dash_data = dash_res.json()
        assert "active_incidents" in dash_data
        assert "fleet" in dash_data
        ambs_res = client.get("/state/ambulances")
        assert ambs_res.status_code == 200
        ambs_list = ambs_res.json()
        assert len(ambs_list) > 0
        sample_amb = ambs_list[0]
        assert "is_repositioning" in sample_amb
        print("  ✓ Dashboard, fleet, and ambulance serialization regression clean")

    print("\n" + "=" * 70)
    print("ALL 20 M9 FLEET REPOSITIONING TESTS PASSED SUCCESSFULLY.")
    print("=" * 70)


if __name__ == "__main__":
    run_m9_tests()
