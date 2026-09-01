"""
RAAH Deterministic Scenario Runner (M10 Phase 1)
================================================

Orchestrates scenario execution against an isolated Simulator instance.
Enforces strictly controlled clocks, deterministic PRNG seeds, and complete
observational recording without bypassing core M8 routing or M9 coordination engines.
"""

import time
import random
import uuid
from typing import Dict, List, Optional, Any
from collections import defaultdict

from simulator import Simulator
from .models import ScenarioDefinition, RunMetadata, ReplayArtifact
from .recorder import ScenarioRecorder


class ScenarioRunner:
    """
    Executes a ScenarioDefinition deterministically against a Simulator instance.
    Maintains clock pacing, triggers scheduled actions, and records timeline events.
    """

    def __init__(self, simulator: Optional[Simulator] = None, seed: Optional[int] = None):
        self.sim = simulator if simulator is not None else Simulator()
        self.seed = seed or 42
        self.rng = random.Random(self.seed)

    def run(
        self,
        scenario: ScenarioDefinition,
        run_id: Optional[str] = None,
    ) -> ReplayArtifact:
        """
        Execute the scenario from clean initial state and produce a ReplayArtifact.
        """
        start_wall_time = time.perf_counter()
        rid = run_id or f"run_{scenario.scenario_id}_{uuid.uuid4().hex[:8]}"

        # 1. Reset simulator to pristine state
        self.sim.load_state()
        self.sim.state.current_time = 0

        # 2. Seed deterministic PRNG
        exec_seed = scenario.config.deterministic_seed
        self.rng = random.Random(exec_seed)

        # 3. Setup recorder
        recorder = ScenarioRecorder()
        recorder.record_event(
            sim_time=0,
            event_type="SCENARIO_START",
            entity_ids={"scenario_id": scenario.scenario_id, "run_id": rid},
            payload={
                "scenario_name": scenario.name,
                "duration_minutes": scenario.config.duration_minutes,
                "tick_minutes": scenario.config.tick_minutes,
                "seed": exec_seed,
            },
        )

        # 4. Initial state snapshot at T=0
        recorder.capture_snapshot(sim_time=0, sim=self.sim)

        # 5. Index scheduled actions by simulation minute
        incidents_by_time = defaultdict(list)
        for inc in scenario.scheduled_incidents:
            incidents_by_time[int(inc.sim_time)].append(inc)

        mcis_by_time = defaultdict(list)
        for m in scenario.scheduled_mcis:
            mcis_by_time[int(m.sim_time)].append(m)

        repositions_by_time = defaultdict(list)
        for r in scenario.scheduled_repositions:
            repositions_by_time[int(r.sim_time)].append(r)

        redirections_by_time = defaultdict(list)
        for d in scenario.scheduled_redirections:
            redirections_by_time[int(d.sim_time)].append(d)

        hosp_events_by_time = defaultdict(list)
        for h in scenario.scheduled_hospital_events:
            hosp_events_by_time[int(h.sim_time)].append(h)

        duration = int(scenario.config.duration_minutes)
        tick_min = float(scenario.config.tick_minutes)
        snap_interval = max(1, int(scenario.config.snapshot_interval_ticks))
        current_tick = 0

        # 6. Step through simulation timeline deterministically
        while self.sim.sim_time < duration:
            t = self.sim.sim_time

            # A. Hospital Events
            for h_ev in hosp_events_by_time.get(t, []):
                hosp = self.sim.state.hospitals.get(h_ev.hospital_id)
                if hosp:
                    if h_ev.event_type == "SET_SATURATED":
                        hosp.current_load = hosp.capacity
                        recorder.record_event(
                            sim_time=t,
                            event_type="HOSPITAL_SATURATED",
                            entity_ids={"hospital_id": h_ev.hospital_id},
                            payload={"message": f"Hospital {h_ev.hospital_id} marked SATURATED."},
                        )
                    elif h_ev.event_type == "RELEASE_SATURATED":
                        hosp.current_load = int(hosp.capacity * 0.5)
                        recorder.record_event(
                            sim_time=t,
                            event_type="HOSPITAL_RESTORED",
                            entity_ids={"hospital_id": h_ev.hospital_id},
                            payload={"message": f"Hospital {h_ev.hospital_id} saturation cleared."},
                        )

            # B. Fleet Repositioning
            for rep in repositions_by_time.get(t, []):
                try:
                    res_repo = self.sim.execute_reposition(
                        ambulance_id=rep.ambulance_id,
                        target_lat=rep.target_lat,
                        target_lon=rep.target_lon,
                        reason=rep.reason,
                    )
                    recorder.record_event(
                        sim_time=t,
                        event_type="REPOSITION_START",
                        entity_ids={"ambulance_id": rep.ambulance_id},
                        payload=res_repo,
                    )
                except Exception as err:
                    recorder.record_event(
                        sim_time=t,
                        event_type="REPOSITION_FAILED",
                        entity_ids={"ambulance_id": rep.ambulance_id},
                        payload={"error": str(err)},
                    )

            # C. Redirections
            for redir in redirections_by_time.get(t, []):
                try:
                    res_redir = self.sim.apply_manual_redirection(
                        incident_id=redir.incident_id,
                        target_hospital_id=redir.target_hospital_id,
                        reason=redir.reason,
                    )
                    recorder.record_event(
                        sim_time=t,
                        event_type="REDIRECTION",
                        entity_ids={
                            "incident_id": redir.incident_id,
                            "target_hospital_id": redir.target_hospital_id,
                        },
                        payload=res_redir if isinstance(res_redir, dict) else {"status": "SUCCESS"},
                    )
                except Exception as err:
                    recorder.record_event(
                        sim_time=t,
                        event_type="REDIRECTION_FAILED",
                        entity_ids={"incident_id": redir.incident_id},
                        payload={"error": str(err)},
                    )

            # D. Scheduled Ordinary Incidents
            for inc in incidents_by_time.get(t, []):
                try:
                    if inc.incident_id is not None:
                        res_inc = self.sim.create_incident(inc.incident_id)
                        actual_id = inc.incident_id
                        sev = res_inc.get("patient", {}).get("severity", "Moderate")
                        pri = res_inc.get("patient", {}).get("priority", 3)
                        amb_id = res_inc.get("ambulance", {}).get("ambulance_id")
                        hosp_id = res_inc.get("hospital", {}).get("hospital_id")
                    elif inc.custom_data:
                        res_inc = self.sim.create_custom_incident(inc.custom_data)
                        actual_id = res_inc.get("incident_id")
                        sev = res_inc.get("patient", {}).get("predicted_severity", "Moderate")
                        pri = res_inc.get("patient", {}).get("priority", "P3")
                        amb_id = res_inc.get("ambulance", {}).get("ambulance_id")
                        hosp_id = res_inc.get("hospital", {}).get("hospital_id")
                    else:
                        # Generate realistic profile
                        c_data = self.sim._generate_mci_casualty_profile(
                            index=current_tick,
                            condition=inc.condition or "Trauma",
                            scene_lat=inc.latitude or 26.9124,
                            scene_lon=inc.longitude or 75.7873,
                        )
                        res_inc = self.sim.create_custom_incident(c_data)
                        actual_id = res_inc.get("incident_id")
                        sev = res_inc.get("patient", {}).get("predicted_severity", "Moderate")
                        pri = res_inc.get("patient", {}).get("priority", "P3")
                        amb_id = res_inc.get("ambulance", {}).get("ambulance_id")
                        hosp_id = res_inc.get("hospital", {}).get("hospital_id")

                    recorder.record_event(
                        sim_time=t,
                        event_type="DISPATCH",
                        entity_ids={
                            "incident_id": actual_id,
                            "ambulance_id": amb_id,
                            "hospital_id": hosp_id,
                        },
                        payload={
                            "severity": sev,
                            "priority": pri,
                            "ambulance_id": amb_id,
                            "hospital_id": hosp_id,
                            "eta_minutes": res_inc.get("ambulance", {}).get("eta_minutes"),
                        },
                    )
                except Exception as err:
                    recorder.record_event(
                        sim_time=t,
                        event_type="DISPATCH_FAILED",
                        entity_ids={"incident_id": inc.incident_id},
                        payload={"error": str(err)},
                    )

            # E. Scheduled Multi-Casualty Incidents (MCI)
            for mci_item in mcis_by_time.get(t, []):
                try:
                    res_mci = self.sim.declare_mci(
                        mci_id=mci_item.mci_id,
                        name=mci_item.name,
                        latitude=mci_item.latitude,
                        longitude=mci_item.longitude,
                        estimated_casualties=mci_item.estimated_casualties,
                        primary_condition=mci_item.primary_condition,
                        notes=mci_item.notes,
                        casualties=mci_item.casualties,
                    )
                    recorder.record_event(
                        sim_time=t,
                        event_type="MCI_DECLARED",
                        entity_ids={"mci_id": res_mci["mci"]["mci_id"]},
                        payload={
                            "name": res_mci["mci"]["name"],
                            "total_casualties": res_mci["mci"]["total_casualties"],
                            "dispatched_count": res_mci["dispatched_count"],
                            "waiting_count": res_mci["waiting_count"],
                            "assigned_ambulances": res_mci["mci"]["assigned_ambulance_ids"],
                            "hospital_distribution": res_mci["mci"]["hospital_distribution"],
                        },
                    )
                    for ch in res_mci.get("child_incidents", []):
                        if ch.get("ambulance_id"):
                            recorder.record_event(
                                sim_time=t,
                                event_type="DISPATCH",
                                entity_ids={
                                    "incident_id": ch["incident_id"],
                                    "ambulance_id": ch["ambulance_id"],
                                    "hospital_id": ch["hospital_id"],
                                    "mci_id": res_mci["mci"]["mci_id"],
                                },
                                payload={
                                    "severity": ch.get("severity", "Moderate"),
                                    "priority": ch.get("priority", 3),
                                    "ambulance_id": ch["ambulance_id"],
                                    "hospital_id": ch["hospital_id"],
                                    "eta_minutes": ch.get("eta_minutes"),
                                },
                            )
                except Exception as err:
                    recorder.record_event(
                        sim_time=t,
                        event_type="MCI_FAILED",
                        entity_ids={"mci_id": mci_item.mci_id},
                        payload={"error": str(err)},
                    )

            # F. Tick Kinematics & Simulator Clock
            # Track arriving ambulances before and after tick
            pre_en_route = {
                aid: amb.hospital_id
                for aid, amb in self.sim.state.ambulances.items()
                if amb.status == "EN_ROUTE" and amb.incident_id is not None
            }

            self.sim.advance_time(tick_min)
            current_tick += 1

            # Detect arrivals
            for aid, hosp_id in pre_en_route.items():
                amb = self.sim.state.ambulances.get(aid)
                if amb and amb.status == "ARRIVED":
                    recorder.record_event(
                        sim_time=self.sim.sim_time,
                        event_type="AMBULANCE_ARRIVED",
                        entity_ids={"ambulance_id": aid, "hospital_id": hosp_id},
                        payload={"message": f"Ambulance {aid} arrived at destination {hosp_id}."},
                    )

            # G. Periodic State Snapshot
            if current_tick % snap_interval == 0:
                recorder.capture_snapshot(sim_time=self.sim.sim_time, sim=self.sim)

        # 7. Final Snapshot & Completion Event
        recorder.capture_snapshot(sim_time=self.sim.sim_time, sim=self.sim)
        recorder.record_event(
            sim_time=self.sim.sim_time,
            event_type="SCENARIO_COMPLETE",
            entity_ids={"scenario_id": scenario.scenario_id, "run_id": rid},
            payload={"final_sim_time": self.sim.sim_time, "total_events": recorder.event_count},
        )

        end_wall_time = time.perf_counter()
        wall_clock_sec = round(end_wall_time - start_wall_time, 4)

        # 8. Assemble RunMetadata and ReplayArtifact
        meta = RunMetadata(
            scenario_id=scenario.scenario_id,
            run_id=rid,
            start_sim_time=0,
            end_sim_time=self.sim.sim_time,
            wall_clock_duration_seconds=wall_clock_sec,
            event_count=recorder.event_count,
            snapshot_count=recorder.snapshot_count,
            completion_status="COMPLETED",
            deterministic_seed=exec_seed,
            replay_format_version="1.0.0",
        )

        final_summary = {
            "total_incidents": len(self.sim.state.incidents),
            "arrived_incidents": sum(1 for i in self.sim.state.incidents.values() if i.status == "ARRIVED"),
            "active_mcis": len(self.sim.coordinator.mci_manager.list_all_mcis()) if hasattr(self.sim, "coordinator") else 0,
            "sim_time": self.sim.sim_time,
        }

        return ReplayArtifact(
            replay_format_version="1.0.0",
            run_metadata=meta,
            scenario_definition=scenario,
            events=recorder.get_events(),
            snapshots=recorder.get_snapshots(),
            final_summary=final_summary,
        )
