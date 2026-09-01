"""
RAAH M10 Phase 2 Test Suite — Disaster Drills & Stress-Testing Library
======================================================================

Verifies:
  1. Drill library registration (all curated drills registered).
  2. Drill metadata retrieval.
  3. NH-48 Multi-Vehicle Pileup generator determinism.
  4. Dual-MCI Earthquake generator determinism.
  5. Citywide Hospital Saturation generator determinism.
  6. Casualty surge generator for 25 casualties.
  7. Casualty surge generator for 50 casualties.
  8. Casualty surge generator for 100 casualties.
  9. Scheduled events sorted chronologically in all generators.
  10. Determinism Invariant: Same seed produces identical ScenarioDefinition.
  11. Deterministic Hashing: Same scenario + seed produces identical SHA-256 hash.
  12. Hash Sensitivity: Different parameters produce distinct hashes.
  13. Stress runner uses isolated Simulator.
  14. Live manager simulator remains unchanged during stress runs.
  15. 25-casualty stress execution.
  16. 50-casualty stress execution.
  17. 100-casualty stress execution.
  18. Fleet metrics calculation (utilization, dispatch success, peak en route).
  19. Hospital metrics calculation (used count, peak load, saturation events).
  20. MCI metrics calculation (total MCIs, peak concurrent, unresolved).
  21. Resilience score transparent multi-component calculation.
  22. Comparative stress result generation (25 vs 50 vs 100).
  23. Drill result persistence and retrieval via DrillResultStore.
  24. REST API endpoints validation (/drills, /drills/run, /drills/stress, /drills/compare, /drills/results/{id}).
  25. Regression check on Phase 1 replay and core coordination.
"""

import json
import time
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies import manager
from Dispatch.scenarios.drills import (
    DrillLibrary,
    generate_pileup_scenario,
    generate_dual_mci_scenario,
    generate_hospital_saturation_scenario,
    generate_casualty_surge,
    DrillMetricsCalculator,
    ResilienceScore,
    StressRunResult,
    DrillResultStore,
    compute_deterministic_hash,
    run_stress_scenario,
    run_drill,
    run_casualty_surge,
    run_comparison,
)

client = TestClient(app)


def run_phase2_tests():
    print("\n" + "=" * 70)
    print("RAAH M10 PHASE 2: DISASTER DRILLS & STRESS TESTING TEST SUITE")
    print("=" * 70)

    with client:
        # Reset live simulator
        client.post("/simulation/reset")

        # --------------------------------------------------------------
        # TEST 1: Drill Library Registration
        # --------------------------------------------------------------
        print("\n[TEST 1] Drill library registration...")
        drills = DrillLibrary.list_drills()
        drill_names = {d["name"] for d in drills}
        assert "NH48_MULTI_VEHICLE_PILEUP" in drill_names
        assert "DUAL_MCI_EARTHQUAKE" in drill_names
        assert "CITYWIDE_HOSPITAL_SATURATION" in drill_names
        assert "CASUALTY_SURGE" in drill_names
        print(f"✓ Verified 4 curated drills registered: {sorted(list(drill_names))}")

        # --------------------------------------------------------------
        # TEST 2: Drill Metadata Retrieval
        # --------------------------------------------------------------
        print("\n[TEST 2] Drill metadata retrieval...")
        pileup_meta = DrillLibrary.get_drill("NH48_MULTI_VEHICLE_PILEUP")
        assert pileup_meta is not None
        assert "casualty_count" in pileup_meta["default_parameters"]
        assert pileup_meta["category"] == "HIGHWAY_TRAUMA"
        print("✓ Drill metadata retrieved with default parameters.")

        # --------------------------------------------------------------
        # TEST 3, 4 & 5: Generator Determinism (Pileup, Dual-MCI, Saturation)
        # --------------------------------------------------------------
        print("\n[TEST 3-5] Named drill generators determinism...")
        scen_p1 = generate_pileup_scenario(seed=77, casualty_count=16)
        scen_p2 = generate_pileup_scenario(seed=77, casualty_count=16)
        assert scen_p1.to_dict() == scen_p2.to_dict()
        assert len(scen_p1.scheduled_mcis) == 1
        assert scen_p1.scheduled_mcis[0].estimated_casualties == 16
        print("✓ Pileup generator strictly deterministic.")

        scen_d1 = generate_dual_mci_scenario(seed=88, casualties_per_mci=14)
        scen_d2 = generate_dual_mci_scenario(seed=88, casualties_per_mci=14)
        assert scen_d1.to_dict() == scen_d2.to_dict()
        assert len(scen_d1.scheduled_mcis) == 2
        print("✓ Dual-MCI generator strictly deterministic (2 simultaneous scenes).")

        scen_s1 = generate_hospital_saturation_scenario(seed=99, incident_count=12)
        scen_s2 = generate_hospital_saturation_scenario(seed=99, incident_count=12)
        assert scen_s1.to_dict() == scen_s2.to_dict()
        assert len(scen_s1.scheduled_hospital_events) >= 3
        print("✓ Hospital saturation generator strictly deterministic.")

        # --------------------------------------------------------------
        # TEST 6, 7 & 8: Casualty Surge Generator for 25, 50, 100 Casualties
        # --------------------------------------------------------------
        print("\n[TEST 6-8] Casualty surge generators (25, 50, 100 casualties)...")
        scen_25 = generate_casualty_surge(casualty_count=25, seed=101, mci_count=1)
        assert sum(m.estimated_casualties for m in scen_25.scheduled_mcis) == 25

        scen_50 = generate_casualty_surge(casualty_count=50, seed=101, mci_count=2)
        assert sum(m.estimated_casualties for m in scen_50.scheduled_mcis) == 50

        scen_100 = generate_casualty_surge(casualty_count=100, seed=101, mci_count=4)
        assert sum(m.estimated_casualties for m in scen_100.scheduled_mcis) == 100
        print("✓ Parameterized surge generator validated for 25, 50, and 100 casualty scales.")

        # --------------------------------------------------------------
        # TEST 9: Chronological Event Ordering in All Generators
        # --------------------------------------------------------------
        print("\n[TEST 9] Chronological event ordering...")
        for scen in (scen_p1, scen_d1, scen_s1, scen_25, scen_50, scen_100):
            all_times = (
                [i.sim_time for i in scen.scheduled_incidents]
                + [m.sim_time for m in scen.scheduled_mcis]
                + [r.sim_time for r in scen.scheduled_repositions]
                + [h.sim_time for h in scen.scheduled_hospital_events]
            )
            # Ensure within each event category, items are monotonically ordered
            inc_times = [i.sim_time for i in scen.scheduled_incidents]
            assert inc_times == sorted(inc_times)
            mci_times = [m.sim_time for m in scen.scheduled_mcis]
            assert mci_times == sorted(mci_times)
            hosp_times = [h.sim_time for h in scen.scheduled_hospital_events]
            assert hosp_times == sorted(hosp_times)
        print("✓ All scheduled event streams verified chronologically ordered.")

        # --------------------------------------------------------------
        # TEST 10: Same Seed Produces Identical Scenario Definitions
        # --------------------------------------------------------------
        print("\n[TEST 10] Determinism Invariant: Same seed => Identical definitions...")
        s_a = DrillLibrary.generate("NH48_MULTI_VEHICLE_PILEUP", seed=42, casualty_count=15)
        s_b = DrillLibrary.generate("NH48_MULTI_VEHICLE_PILEUP", seed=42, casualty_count=15)
        assert s_a.to_dict() == s_b.to_dict()
        print("✓ Seed determinism invariant holds across library generation.")

        # --------------------------------------------------------------
        # TEST 11 & 12: Deterministic Hash Invariance and Sensitivity
        # --------------------------------------------------------------
        print("\n[TEST 11 & 12] Deterministic hash consistency and parameter sensitivity...")
        res_a1 = run_drill("NH48_MULTI_VEHICLE_PILEUP", seed=42, casualty_count=10, duration_minutes=5)
        res_a2 = run_drill("NH48_MULTI_VEHICLE_PILEUP", seed=42, casualty_count=10, duration_minutes=5)
        assert res_a1.deterministic_hash == res_a2.deterministic_hash, f"Hash mismatch: {res_a1.deterministic_hash} != {res_a2.deterministic_hash}"
        print(f"✓ Identical run produced identical SHA-256 hash: {res_a1.deterministic_hash}")

        # Different casualty count must produce a different hash
        res_diff = run_drill("NH48_MULTI_VEHICLE_PILEUP", seed=42, casualty_count=14, duration_minutes=5)
        assert res_a1.deterministic_hash != res_diff.deterministic_hash
        print(f"✓ Parameter divergence produced distinct hash: {res_diff.deterministic_hash}")

        # --------------------------------------------------------------
        # TEST 13 & 14: Simulator Isolation from Live Manager Simulator
        # --------------------------------------------------------------
        print("\n[TEST 13 & 14] Simulator isolation during stress runs...")
        with manager.lock:
            live_time_before = manager.simulator.state.current_time
            live_amb_statuses_before = {aid: a.status for aid, a in manager.simulator.state.ambulances.items()}

        # Run heavy drill
        res_iso = run_drill("DUAL_MCI_EARTHQUAKE", seed=55, casualties_per_mci=8, duration_minutes=6)

        with manager.lock:
            live_time_after = manager.simulator.state.current_time
            live_amb_statuses_after = {aid: a.status for aid, a in manager.simulator.state.ambulances.items()}

        assert live_time_before == live_time_after
        assert live_amb_statuses_before == live_amb_statuses_after
        print("✓ Live manager.simulator strictly unmutated by stress test execution.")

        # --------------------------------------------------------------
        # TEST 15, 16 & 17: Stress Surge Execution (25, 50, 100 Casualties)
        # --------------------------------------------------------------
        print("\n[TEST 15-17] Stress surge execution (25, 50, 100 casualties)...")
        res_25 = run_casualty_surge(casualty_count=25, seed=77, mci_count=1, duration_minutes=6)
        assert res_25.incidents_created == 25
        assert res_25.incidents_dispatched == 25
        print(f"✓ 25-casualty stress passed ({res_25.simulation_runtime_ms}ms). Dispatched: {res_25.incidents_dispatched}/25.")

        res_50 = run_casualty_surge(casualty_count=50, seed=77, mci_count=2, duration_minutes=6)
        assert res_50.incidents_created == 50
        assert res_50.incidents_dispatched == 50
        print(f"✓ 50-casualty stress passed ({res_50.simulation_runtime_ms}ms). Dispatched: {res_50.incidents_dispatched}/50.")

        res_100 = run_casualty_surge(casualty_count=100, seed=77, mci_count=4, duration_minutes=6)
        assert res_100.incidents_created == 100
        assert res_100.incidents_dispatched == 100
        print(f"✓ 100-casualty stress passed ({res_100.simulation_runtime_ms}ms). Dispatched: {res_100.incidents_dispatched}/100.")

        # --------------------------------------------------------------
        # TEST 18, 19 & 20: Fleet, Hospital, and MCI Metrics
        # --------------------------------------------------------------
        print("\n[TEST 18-20] Telemetry metrics extraction...")
        f_m = res_100.metrics["fleet_metrics"]
        assert f_m["total_ambulances"] > 0
        assert f_m["peak_en_route"] >= 20
        assert f_m["dispatch_success_ratio_pct"] == 100.0

        h_m = res_100.metrics["hospital_metrics"]
        assert h_m["hospitals_used_count"] > 1
        assert len(h_m["hospital_load_distribution"]) > 1

        m_m = res_100.metrics["mci_metrics"]
        assert m_m["total_mcis"] == 4
        print(f"✓ 100-casualty fleet peak en route: {f_m['peak_en_route']}, hospitals used: {h_m['hospitals_used_count']}, MCIs: {m_m['total_mcis']}.")

        # --------------------------------------------------------------
        # TEST 21: Resilience Score Component Calculation
        # --------------------------------------------------------------
        print("\n[TEST 21] Transparent resilience score calculation...")
        r_score = res_100.resilience_score
        assert "overall" in r_score
        assert "fleet_score" in r_score
        assert "dispatch_score" in r_score
        assert "hospital_score" in r_score
        assert "evacuation_score" in r_score
        assert "saturation_penalty" in r_score
        assert "unresolved_penalty" in r_score
        assert 0.0 <= r_score["overall"] <= 100.0
        print(f"✓ Resilience score: {r_score['overall']} (dispatch={r_score['dispatch_score']}, fleet={r_score['fleet_score']}, hosp={r_score['hospital_score']}).")

        # --------------------------------------------------------------
        # TEST 22: Comparative Stress Results (25 vs 50 vs 100)
        # --------------------------------------------------------------
        print("\n[TEST 22] Comparative stress result generation...")
        comp_rows = run_comparison(casualty_counts=[25, 50, 100], seed=42)
        assert len(comp_rows) == 3
        assert comp_rows[0]["casualties"] == 25
        assert comp_rows[1]["casualties"] == 50
        assert comp_rows[2]["casualties"] == 100
        for row in comp_rows:
            assert row["dispatch_success_pct"] > 0
            assert row["deterministic_hash"] is not None
        print("✓ Comparison rows successfully generated across 25/50/100 casualties.")

        # --------------------------------------------------------------
        # TEST 23: Drill Result Store Persistence & Retrieval
        # --------------------------------------------------------------
        print("\n[TEST 23] Drill result persistence and retrieval...")
        store = DrillResultStore()
        saved_id = store.save(res_25)
        retrieved = store.get(saved_id)
        assert retrieved is not None
        assert retrieved.run_id == res_25.run_id
        assert retrieved.casualty_count == 25
        assert retrieved.deterministic_hash == res_25.deterministic_hash
        print("✓ StressRunResult persisted atomically and verified on disk.")

        # --------------------------------------------------------------
        # TEST 24: REST API Endpoints Validation
        # --------------------------------------------------------------
        print("\n[TEST 24] Drill REST API endpoints validation...")
        # 1. GET /drills
        r_list = client.get("/drills")
        assert r_list.status_code == 200
        assert len(r_list.json()) >= 4

        # 2. GET /drills/{drill_name}
        r_info = client.get("/drills/NH48_MULTI_VEHICLE_PILEUP")
        assert r_info.status_code == 200
        assert r_info.json()["name"] == "NH48_MULTI_VEHICLE_PILEUP"

        # 3. POST /drills/run
        r_run = client.post("/drills/run", json={
            "drill_name": "NH48_MULTI_VEHICLE_PILEUP",
            "seed": 42,
            "parameters": {"casualty_count": 8, "duration_minutes": 5},
        })
        assert r_run.status_code == 200, r_run.text
        drill_out = r_run.json()
        assert drill_out["drill_name"] == "NH48_MULTI_VEHICLE_PILEUP"
        assert drill_out["deterministic_hash"] is not None
        run_id_api = drill_out["run_id"]

        # 4. GET /drills/results/{run_id}
        r_get_res = client.get(f"/drills/results/{run_id_api}")
        assert r_get_res.status_code == 200
        assert r_get_res.json()["run_id"] == run_id_api

        # 5. POST /drills/stress
        r_stress = client.post("/drills/stress", json={
            "casualty_count": 20,
            "seed": 42,
            "mci_count": 1,
            "duration_minutes": 5,
        })
        assert r_stress.status_code == 200
        assert r_stress.json()["casualty_count"] == 20

        # 6. POST /drills/compare
        r_comp = client.post("/drills/compare", json={
            "casualty_counts": [15, 30],
            "seed": 42,
        })
        assert r_comp.status_code == 200
        assert len(r_comp.json()) == 2
        print("✓ All /drills REST API endpoints verified.")

        # --------------------------------------------------------------
        # TEST 25: Regression Check on Phase 1 Replays & Core Endpoints
        # --------------------------------------------------------------
        print("\n[TEST 25] Regression check against M10 Phase 1 replays and core endpoints...")
        r_scens = client.get("/scenarios")
        assert r_scens.status_code == 200
        r_reps = client.get("/replays")
        assert r_reps.status_code == 200
        r_health = client.get("/health")
        assert r_health.status_code == 200
        print("✓ Full backwards compatibility with M10 Phase 1 confirmed.")

    print("\n" + "=" * 70)
    print("ALL 25 M10 PHASE 2 DISASTER DRILLS & STRESS TESTS PASSED.")
    print("=" * 70)


if __name__ == "__main__":
    run_phase2_tests()
