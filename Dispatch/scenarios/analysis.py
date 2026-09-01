"""
RAAH Operational Replay & Scenario Analysis Engine (M10 Phase 3)
================================================================

Provides comprehensive operational analysis over recorded ReplayArtifacts:
- Normalized chronological timeline generation with stable event ordering
- Deep event inspection (dispatch, redirection, repositioning, MCI, hospital)
- System resilience and throughput analysis
- Scenario A vs Scenario B delta comparison
- Stress-test comparative evaluation (25 / 50 / 100 casualties)
- Before/After snapshot delta analysis
- Structured drill report generation (JSON and Markdown)
- Deterministic analysis hashing

STRICT INVARIANT:
Completely observational. Never mutates live Simulator or DispatchState.
Operates exclusively on serialized Scenario/Replay data.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import hashlib
import json
import os
from copy import deepcopy

from .models import ReplayArtifact
from .replay import ReplayEngine
from .drills.metrics import DrillMetricsCalculator, ResilienceScore
from .drills.stress import compute_deterministic_hash


def _generate_event_description(e_type: str, entity_ids: Dict[str, Any], payload: Dict[str, Any]) -> str:
    """Generate concise human-readable description for an operational event."""
    if e_type == "DISPATCH":
        aid = entity_ids.get("ambulance_id", "AMB")
        iid = entity_ids.get("incident_id", "INC")
        hid = entity_ids.get("hospital_id", "HOSP")
        eta = payload.get("eta_minutes", 0)
        pri = payload.get("priority", "P?")
        return f"Unit {aid} dispatched to Incident #{iid} ({pri}) -> {hid} (ETA {eta}m)"

    elif e_type == "AMBULANCE_ARRIVED":
        aid = entity_ids.get("ambulance_id", "AMB")
        hid = entity_ids.get("hospital_id", "HOSP")
        return f"Ambulance {aid} arrived at destination hospital {hid}"

    elif e_type == "REDIRECTION":
        aid = entity_ids.get("ambulance_id", "AMB")
        iid = entity_ids.get("incident_id", "INC")
        old_h = payload.get("previous_hospital_id", entity_ids.get("hospital_id", "HOSP_OLD"))
        new_h = payload.get("new_hospital_id", entity_ids.get("target_hospital_id", "HOSP_NEW"))
        eta_saved = payload.get("eta_saved", 0)
        return f"Redirection: Unit {aid} #{iid} diverted {old_h} -> {new_h} (Saved {eta_saved}m)"

    elif e_type == "REPOSITION_START":
        aid = entity_ids.get("ambulance_id", "AMB")
        reason = payload.get("reason", "ZONE_DEFICIT")
        return f"Repositioning started: Unit {aid} moving for {reason}"

    elif e_type == "REPOSITION_COMPLETE":
        aid = entity_ids.get("ambulance_id", "AMB")
        return f"Repositioning completed: Unit {aid} stationed at target post"

    elif e_type == "MCI_DECLARED":
        mid = entity_ids.get("mci_id", "MCI")
        cas = payload.get("total_casualties", 0)
        disp = payload.get("dispatched_count", 0)
        return f"MCI Declared: {mid} with {cas} casualties ({disp} units assigned)"

    elif e_type == "MCI_RESOLVED":
        mid = entity_ids.get("mci_id", "MCI")
        return f"MCI Resolved: {mid} all casualties evacuated"

    elif e_type == "HOSPITAL_SATURATED":
        hid = entity_ids.get("hospital_id", "HOSP")
        return f"Hospital Saturated: Facility {hid} reached 100% capacity"

    elif e_type == "HOSPITAL_RESTORED":
        hid = entity_ids.get("hospital_id", "HOSP")
        return f"Hospital Restored: Facility {hid} cleared emergency saturation"

    elif e_type == "SCENARIO_START":
        sid = entity_ids.get("scenario_id", "SCENARIO")
        return f"Scenario {sid} execution commenced"

    elif e_type == "SCENARIO_COMPLETE":
        sid = entity_ids.get("scenario_id", "SCENARIO")
        return f"Scenario {sid} execution completed successfully"

    return f"Event {e_type}: {entity_ids}"


@dataclass
class ReplayEventSummary:
    event_index: int
    sim_time: int
    event_type: str
    entity_ids: Dict[str, Any]
    description: str
    payload: Dict[str, Any]
    detail: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayTimeline:
    scenario_id: str
    run_id: str
    start_time: int
    end_time: int
    duration: int
    event_count: int
    snapshot_count: int
    events: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayAnalysis:
    scenario_id: str
    run_id: str
    duration: int
    total_events: int
    dispatch_count: int
    arrival_count: int
    redirection_count: int
    reposition_count: int
    mci_count: int
    hospital_saturation_count: int
    peak_en_route: int
    peak_repositioning: int
    peak_incoming_reservations: int
    unresolved_incidents: int
    unresolved_mcis: int
    fleet_metrics: Dict[str, Any]
    incident_metrics: Dict[str, Any]
    hospital_metrics: Dict[str, Any]
    mci_metrics: Dict[str, Any]
    resilience_score: Dict[str, Any]
    deterministic_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReplayAnalyzer:
    """Analytical operations over ReplayArtifact data."""

    @classmethod
    def build_timeline(
        cls,
        artifact: ReplayArtifact,
        event_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> ReplayTimeline:
        """
        Build a chronologically ordered, stably sorted operational timeline.
        Allows filtering by event_type and/or entity_id.
        """
        raw_events = artifact.events or []
        snapshots = artifact.snapshots or []

        # Stable sort by (sim_time, event_id)
        sorted_events = sorted(
            raw_events,
            key=lambda e: (e.get("sim_time", 0), e.get("event_id", 0))
        )

        timeline_items = []
        for idx, ev in enumerate(sorted_events):
            e_type = ev.get("event_type", "")
            e_ids = ev.get("entity_ids", {})
            payload = ev.get("payload", {})
            t = ev.get("sim_time", 0)

            # Filter by event_type if specified
            if event_type and e_type != event_type:
                continue

            # Filter by entity_id if specified (searches any matching entity_id or payload reference)
            if entity_id:
                eid_str = str(entity_id)
                matches = False
                for v in e_ids.values():
                    if str(v) == eid_str:
                        matches = True
                        break
                if not matches:
                    for k in ("ambulance_id", "hospital_id", "incident_id", "mci_id"):
                        if str(payload.get(k, "")) == eid_str:
                            matches = True
                            break
                if not matches:
                    continue

            desc = _generate_event_description(e_type, e_ids, payload)
            item = ReplayEventSummary(
                event_index=idx,
                sim_time=t,
                event_type=e_type,
                entity_ids=e_ids,
                description=desc,
                payload=payload,
                detail=cls._build_event_detail(e_type, e_ids, payload),
            )
            timeline_items.append(item.to_dict())

        start_t = 0
        end_t = 0
        if snapshots:
            start_t = snapshots[0].get("sim_time", 0)
            end_t = snapshots[-1].get("sim_time", 0)
        elif raw_events:
            start_t = sorted_events[0].get("sim_time", 0)
            end_t = sorted_events[-1].get("sim_time", 0)

        dur = (artifact.run_metadata.end_sim_time - artifact.run_metadata.start_sim_time) if getattr(artifact.run_metadata, "end_sim_time", None) is not None else (end_t - start_t)

        return ReplayTimeline(
            scenario_id=artifact.run_metadata.scenario_id,
            run_id=artifact.run_metadata.run_id,
            start_time=start_t,
            end_time=end_t,
            duration=dur,
            event_count=len(timeline_items),
            snapshot_count=len(snapshots),
            events=timeline_items,
        )

    @classmethod
    def _build_event_detail(cls, e_type: str, e_ids: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        """Construct structured specialized details for specific operational event types."""
        if e_type == "DISPATCH":
            return {
                "ambulance_id": e_ids.get("ambulance_id") or payload.get("ambulance_id"),
                "incident_id": e_ids.get("incident_id"),
                "hospital_id": e_ids.get("hospital_id") or payload.get("hospital_id"),
                "severity": payload.get("severity"),
                "priority": payload.get("priority"),
                "eta_minutes": payload.get("eta_minutes"),
                "route_distance_km": payload.get("route_distance_km"),
            }
        elif e_type == "REDIRECTION":
            return {
                "ambulance_id": e_ids.get("ambulance_id"),
                "incident_id": e_ids.get("incident_id"),
                "previous_hospital_id": payload.get("previous_hospital_id", e_ids.get("hospital_id")),
                "new_hospital_id": payload.get("new_hospital_id", e_ids.get("target_hospital_id")),
                "previous_eta_minutes": payload.get("previous_eta"),
                "new_eta_minutes": payload.get("new_eta"),
                "eta_saved_minutes": payload.get("eta_saved"),
                "reason": payload.get("reason"),
            }
        elif e_type in ("REPOSITION_START", "REPOSITION_COMPLETE"):
            return {
                "ambulance_id": e_ids.get("ambulance_id"),
                "origin_zone": payload.get("origin_zone"),
                "target_zone": payload.get("target_zone"),
                "target_coords": payload.get("target_coords"),
                "reason": payload.get("reason"),
                "status": "IN_TRANSIT" if e_type == "REPOSITION_START" else "STATIONED",
            }
        elif e_type in ("MCI_DECLARED", "MCI_RESOLVED"):
            return {
                "mci_id": e_ids.get("mci_id"),
                "name": payload.get("name"),
                "total_casualties": payload.get("total_casualties"),
                "dispatched_count": payload.get("dispatched_count"),
                "waiting_count": payload.get("waiting_count"),
                "assigned_ambulances": payload.get("assigned_ambulances", []),
                "hospital_distribution": payload.get("hospital_distribution", {}),
            }
        elif e_type in ("HOSPITAL_SATURATED", "HOSPITAL_RESTORED"):
            return {
                "hospital_id": e_ids.get("hospital_id"),
                "event": "SATURATED" if e_type == "HOSPITAL_SATURATED" else "RESTORED",
            }
        return dict(payload)

    @classmethod
    def get_event_detail(cls, artifact: ReplayArtifact, event_index: int) -> Optional[Dict[str, Any]]:
        """Retrieve detailed inspector payload for a specific event by index."""
        raw_events = artifact.events or []
        sorted_events = sorted(
            raw_events,
            key=lambda e: (e.get("sim_time", 0), e.get("event_id", 0))
        )
        if 0 <= event_index < len(sorted_events):
            ev = sorted_events[event_index]
            e_type = ev.get("event_type", "")
            e_ids = ev.get("entity_ids", {})
            payload = ev.get("payload", {})
            desc = _generate_event_description(e_type, e_ids, payload)
            summary = ReplayEventSummary(
                event_index=event_index,
                sim_time=ev.get("sim_time", 0),
                event_type=e_type,
                entity_ids=e_ids,
                description=desc,
                payload=payload,
                detail=cls._build_event_detail(e_type, e_ids, payload),
            )
            return summary.to_dict()
        return None

    @classmethod
    def analyze(cls, artifact: ReplayArtifact) -> ReplayAnalysis:
        """Calculate complete operational performance metrics and resilience scorecard."""
        metrics_dict = DrillMetricsCalculator.compute(artifact)
        f_m = metrics_dict["fleet_metrics"]
        i_m = metrics_dict["incident_metrics"]
        h_m = metrics_dict["hospital_metrics"]
        m_m = metrics_dict["mci_metrics"]
        r_score = metrics_dict["resilience_score"]

        events = artifact.events or []
        dispatch_cnt = sum(1 for e in events if e.get("event_type") == "DISPATCH")
        arrival_cnt = sum(1 for e in events if e.get("event_type") == "AMBULANCE_ARRIVED")
        redir_cnt = sum(1 for e in events if e.get("event_type") == "REDIRECTION")
        repo_cnt = sum(1 for e in events if e.get("event_type") == "REPOSITION_START")
        mci_cnt = sum(1 for e in events if e.get("event_type") == "MCI_DECLARED")
        sat_cnt = sum(1 for e in events if e.get("event_type") == "HOSPITAL_SATURATED")

        det_hash = compute_deterministic_hash(artifact)
        dur = (artifact.run_metadata.end_sim_time - artifact.run_metadata.start_sim_time) if getattr(artifact.run_metadata, "end_sim_time", None) is not None else (artifact.snapshots[-1]["sim_time"] if artifact.snapshots else 0)

        return ReplayAnalysis(
            scenario_id=artifact.run_metadata.scenario_id,
            run_id=artifact.run_metadata.run_id,
            duration=dur,
            total_events=len(events),
            dispatch_count=dispatch_cnt,
            arrival_count=arrival_cnt,
            redirection_count=redir_cnt,
            reposition_count=repo_cnt,
            mci_count=mci_cnt,
            hospital_saturation_count=sat_cnt,
            peak_en_route=f_m.get("peak_en_route", 0),
            peak_repositioning=f_m.get("peak_repositioning", 0),
            peak_incoming_reservations=h_m.get("max_simultaneous_incoming_reservations", 0),
            unresolved_incidents=i_m.get("unresolved_casualties", 0),
            unresolved_mcis=m_m.get("unresolved_mci_casualties", 0),
            fleet_metrics=f_m,
            incident_metrics=i_m,
            hospital_metrics=h_m,
            mci_metrics=m_m,
            resilience_score=r_score,
            deterministic_hash=det_hash,
        )

    @classmethod
    def compare_scenarios(cls, artifact_a: ReplayArtifact, artifact_b: ReplayArtifact) -> Dict[str, Any]:
        """
        Compare two scenarios or runs (Scenario A vs Scenario B) and compute
        telemetry differences (deltas).
        """
        ana_a = cls.analyze(artifact_a).to_dict()
        ana_b = cls.analyze(artifact_b).to_dict()

        f_a = ana_a["fleet_metrics"]
        f_b = ana_b["fleet_metrics"]
        i_a = ana_a["incident_metrics"]
        i_b = ana_b["incident_metrics"]
        h_a = ana_a["hospital_metrics"]
        h_b = ana_b["hospital_metrics"]
        r_a = ana_a["resilience_score"]
        r_b = ana_b["resilience_score"]

        delta = {
            "total_casualties": i_b.get("total_casualties", 0) - i_a.get("total_casualties", 0),
            "dispatch_success_pct": round(f_b.get("dispatch_success_ratio_pct", 0) - f_a.get("dispatch_success_ratio_pct", 0), 2),
            "average_eta_minutes": round(f_b.get("average_dispatch_eta_minutes", 0) - f_a.get("average_dispatch_eta_minutes", 0), 2),
            "unresolved_casualties": i_b.get("unresolved_casualties", 0) - i_a.get("unresolved_casualties", 0),
            "hospital_saturation_events": h_b.get("hospitals_reaching_full_count", 0) - h_a.get("hospitals_reaching_full_count", 0),
            "icu_saturation_events": h_b.get("hospitals_reaching_icu_full_count", 0) - h_a.get("hospitals_reaching_icu_full_count", 0),
            "peak_fleet_utilization_pct": round(f_b.get("utilization_ratio_pct", 0) - f_a.get("utilization_ratio_pct", 0), 2),
            "peak_concurrent_mci": ana_b["mci_metrics"].get("peak_concurrent_mcis", 0) - ana_a["mci_metrics"].get("peak_concurrent_mcis", 0),
            "resilience_score": round(r_b.get("overall", 0) - r_a.get("overall", 0), 2),
            "duration_minutes": ana_b.get("duration", 0) - ana_a.get("duration", 0),
        }

        # Explanation for operator
        reasons = []
        if delta["resilience_score"] < 0:
            if delta["unresolved_casualties"] > 0:
                reasons.append(f"Higher casualty load left {delta['unresolved_casualties']} additional unresolved patients.")
            if delta["hospital_saturation_events"] > 0:
                reasons.append(f"{delta['hospital_saturation_events']} more hospitals reached complete capacity.")
            if delta["average_eta_minutes"] > 0:
                reasons.append(f"Average response ETA increased by {delta['average_eta_minutes']} minutes.")
        elif delta["resilience_score"] > 0:
            reasons.append(f"Scenario B achieved superior dispatch and bed preservation (+{delta['resilience_score']} resilience).")
        else:
            reasons.append("Both scenarios exhibited equivalent operational throughput.")

        return {
            "scenario_a": {
                "scenario_id": ana_a["scenario_id"],
                "run_id": ana_a["run_id"],
                "casualties": i_a.get("total_casualties"),
                "dispatch_success_pct": f_a.get("dispatch_success_ratio_pct"),
                "average_eta_minutes": f_a.get("average_dispatch_eta_minutes"),
                "unresolved": i_a.get("unresolved_casualties"),
                "hospital_saturation_count": h_a.get("hospitals_reaching_full_count"),
                "peak_fleet_utilization_pct": f_a.get("utilization_ratio_pct"),
                "resilience_score": r_a.get("overall"),
                "deterministic_hash": ana_a["deterministic_hash"],
            },
            "scenario_b": {
                "scenario_id": ana_b["scenario_id"],
                "run_id": ana_b["run_id"],
                "casualties": i_b.get("total_casualties"),
                "dispatch_success_pct": f_b.get("dispatch_success_ratio_pct"),
                "average_eta_minutes": f_b.get("average_dispatch_eta_minutes"),
                "unresolved": i_b.get("unresolved_casualties"),
                "hospital_saturation_count": h_b.get("hospitals_reaching_full_count"),
                "peak_fleet_utilization_pct": f_b.get("utilization_ratio_pct"),
                "resilience_score": r_b.get("overall"),
                "deterministic_hash": ana_b["deterministic_hash"],
            },
            "delta": delta,
            "performance_explanation": " ".join(reasons),
        }

    @classmethod
    def compare_snapshots_before_after(
        cls,
        artifact: ReplayArtifact,
        time_a: int,
        time_b: int,
    ) -> Dict[str, Any]:
        """
        Compare observable operational state between two simulation timestamps T_a and T_b
        using ReplayEngine state reconstruction.
        """
        engine = ReplayEngine(artifact)

        engine.seek(time_a)
        state_a = deepcopy(engine.get_state())

        engine.seek(time_b)
        state_b = deepcopy(engine.get_state())

        # Telemetry extracted from state
        def _extract_telemetry(state: Dict[str, Any]) -> Dict[str, Any]:
            ambs = state.get("ambulances", [])
            hosps = state.get("hospitals", [])
            incs = state.get("incidents", [])
            mcis = state.get("active_mcis", [])
            cov = state.get("coverage_summary", {})

            avail_amb = sum(1 for a in ambs if a.get("status") == "AVAILABLE")
            en_route_amb = sum(1 for a in ambs if a.get("status") == "EN_ROUTE")
            repo_amb = sum(1 for a in ambs if a.get("is_repositioning") or a.get("status") == "REPOSITIONING")
            arrived_amb = sum(1 for a in ambs if a.get("status") == "ARRIVED")

            waiting_inc = sum(1 for i in incs if i.get("status") in ("PENDING_DISPATCH", "WAITING_AMBULANCE") or not i.get("ambulance_id"))
            total_beds = sum(h.get("capacity", 0) for h in hosps)
            avail_beds = sum(h.get("available_beds", 0) for h in hosps)
            avail_icu = sum(h.get("available_icu", 0) for h in hosps)
            used_beds = total_beds - avail_beds
            hosp_util = round((used_beds / max(1, total_beds)) * 100.0, 2)

            return {
                "sim_time": state.get("sim_time", 0),
                "available_ambulances": avail_amb,
                "en_route_ambulances": en_route_amb,
                "repositioning_ambulances": repo_amb,
                "arrived_ambulances": arrived_amb,
                "waiting_incidents": waiting_inc,
                "active_mcis_count": len(mcis),
                "hospital_utilization_pct": hosp_util,
                "available_icu_beds": avail_icu,
                "coverage_deficits": cov.get("deficit_zones_count", 0),
            }

        tel_a = _extract_telemetry(state_a)
        tel_b = _extract_telemetry(state_b)

        delta = {
            "available_ambulances": tel_b["available_ambulances"] - tel_a["available_ambulances"],
            "en_route_ambulances": tel_b["en_route_ambulances"] - tel_a["en_route_ambulances"],
            "repositioning_ambulances": tel_b["repositioning_ambulances"] - tel_a["repositioning_ambulances"],
            "arrived_ambulances": tel_b["arrived_ambulances"] - tel_a["arrived_ambulances"],
            "waiting_incidents": tel_b["waiting_incidents"] - tel_a["waiting_incidents"],
            "active_mcis_count": tel_b["active_mcis_count"] - tel_a["active_mcis_count"],
            "hospital_utilization_pct": round(tel_b["hospital_utilization_pct"] - tel_a["hospital_utilization_pct"], 2),
            "available_icu_beds": tel_b["available_icu_beds"] - tel_a["available_icu_beds"],
            "coverage_deficits": tel_b["coverage_deficits"] - tel_a["coverage_deficits"],
        }

        return {
            "time_a": tel_a,
            "time_b": tel_b,
            "delta": delta,
        }

    @classmethod
    def generate_report(cls, artifact: ReplayArtifact, format: str = "json") -> Dict[str, Any]:
        """
        Generate a comprehensive, structured disaster drill evaluation report.
        Supports structured JSON dictionary and exportable Markdown formatting.
        """
        analysis = cls.analyze(artifact)
        timeline = cls.build_timeline(artifact)
        meta = artifact.run_metadata

        # Key events summary (critical events)
        important_events = [
            e for e in timeline.events
            if e["event_type"] in ("MCI_DECLARED", "MCI_RESOLVED", "HOSPITAL_SATURATED", "REPOSITION_START", "REDIRECTION")
        ]

        report_dict = {
            "report_title": f"RAAH Operational Replay & Drill Analysis: {meta.scenario_id}",
            "scenario_metadata": meta.to_dict(),
            "deterministic_hash": analysis.deterministic_hash,
            "resilience_score": analysis.resilience_score,
            "performance_summary": {
                "duration_minutes": analysis.duration,
                "total_events": analysis.total_events,
                "dispatches": analysis.dispatch_count,
                "arrivals": analysis.arrival_count,
                "redirections": analysis.redirection_count,
                "repositions": analysis.reposition_count,
                "mcis": analysis.mci_count,
                "hospital_saturation_events": analysis.hospital_saturation_count,
                "unresolved_incidents": analysis.unresolved_incidents,
                "unresolved_mcis": analysis.unresolved_mcis,
            },
            "fleet_metrics": analysis.fleet_metrics,
            "hospital_metrics": analysis.hospital_metrics,
            "mci_metrics": analysis.mci_metrics,
            "important_events": important_events,
        }

        if format == "markdown":
            md_lines = [
                f"# RAAH Drill Analysis Report: {meta.scenario_id}",
                f"**Run ID:** `{meta.run_id}` | **Deterministic SHA-256:** `{analysis.deterministic_hash}`",
                f"**Execution Timestamp:** {meta.created_at} | **Simulated Duration:** {analysis.duration} min",
                "",
                "## 1. Executive Scorecard",
                f"- **Overall Resilience Score:** `{analysis.resilience_score['overall']} / 100.0`",
                f"- **Dispatch Success Rate:** `{analysis.fleet_metrics['dispatch_success_ratio_pct']}%`",
                f"- **Average Response ETA:** `{analysis.fleet_metrics['average_dispatch_eta_minutes']} min`",
                f"- **Peak Fleet Utilization:** `{analysis.fleet_metrics['utilization_ratio_pct']}%` ({analysis.peak_en_route} units)",
                f"- **Hospitals Saturated:** `{analysis.hospital_saturation_count}`",
                f"- **Unresolved Casualties:** `{analysis.unresolved_incidents}`",
                "",
                "## 2. Telemetry Breakdown",
                f"| Metric Domain | Metric | Measured Value |",
                f"| :--- | :--- | :--- |",
                f"| **Fleet** | Total Dispatches | {analysis.dispatch_count} |",
                f"| **Fleet** | Completed Arrivals | {analysis.arrival_count} |",
                f"| **Fleet** | Active Repositions | {analysis.reposition_count} |",
                f"| **Hospital** | Hospitals Used | {analysis.hospital_metrics['hospitals_used_count']} |",
                f"| **Hospital** | Peak Projected Utilization | {analysis.hospital_metrics['peak_projected_utilization']} |",
                f"| **MCI** | Declared Incidents | {analysis.mci_count} |",
                f"| **MCI** | Peak Concurrent MCIs | {analysis.mci_metrics['peak_concurrent_mcis']} |",
                "",
                "## 3. High-Priority Operational Events",
            ]
            for ev in important_events[:15]:
                md_lines.append(f"- **T+{ev['sim_time']}m** [{ev['event_type']}]: {ev['description']}")
            if not important_events:
                md_lines.append("_No critical saturation or MCI escalation events observed._")

            report_dict["markdown_content"] = "\n".join(md_lines)

        return report_dict

    @classmethod
    def compute_analysis_hash(cls, analysis_dict: Dict[str, Any]) -> str:
        """Derive a canonical deterministic hash from normalized analysis metrics."""
        clean = {
            "scenario_id": analysis_dict.get("scenario_id"),
            "duration": analysis_dict.get("duration"),
            "total_events": analysis_dict.get("total_events"),
            "dispatch_count": analysis_dict.get("dispatch_count"),
            "resilience_score": analysis_dict.get("resilience_score"),
            "fleet_metrics": analysis_dict.get("fleet_metrics"),
            "hospital_metrics": analysis_dict.get("hospital_metrics"),
            "mci_metrics": analysis_dict.get("mci_metrics"),
        }
        raw = json.dumps(clean, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class ReplaySessionManager:
    """
    Independent replay session manager.
    Maintains isolated ReplayEngine instances in memory without touching
    manager.simulator or DispatchState.
    """

    def __init__(self):
        self._sessions: Dict[str, ReplayEngine] = {}

    def get_or_create(self, session_id: str, artifact: ReplayArtifact) -> ReplayEngine:
        if session_id in self._sessions:
            return self._sessions[session_id]
        engine = ReplayEngine(artifact)
        self._sessions[session_id] = engine
        return engine

    def get(self, session_id: str) -> Optional[ReplayEngine]:
        return self._sessions.get(session_id)

    def close(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]
