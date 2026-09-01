"""
RAAH Post-Incident Review (PIR) & Root-Cause Analysis Engine (M10 Phase 4)
==========================================================================

Performs purely observational, deterministic root-cause analysis on recorded
Scenario/Replay artifacts.

Detects operational anomalies, synthesizes causal graphs, explains failure chains,
computes deterministic PIR hashes, and issues evidence-based operational recommendations.

STRICT INVARIANTS:
- Purely observational. Never imports, mutates, or instantiates Simulator or DispatchState.
- No LLM dependency. Deterministic, explainable, rule-based inference.
- Same replay artifact -> identical findings, graph, recommendations, and hash.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
import hashlib
import json
from datetime import datetime, timezone

from Dispatch.scenarios.models import ReplayArtifact
from Dispatch.scenarios.analysis import ReplayAnalyzer, ReplayAnalysis


@dataclass
class PostIncidentFinding:
    """Individual operational failure or anomaly identified during review."""
    finding_id: str
    category: str       # "FLEET", "DISPATCH", "HOSPITAL", "MCI", "REPOSITIONING", "SYSTEM"
    severity: str       # "INFO", "WARNING", "CRITICAL"
    confidence: float   # 0.0 - 1.0
    title: str
    description: str
    evidence: Dict[str, Any]      # Event indices, timestamps, entity IDs, metric readings
    measurable_impact: str
    potential_causes: List[str]
    recommendation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RootCauseNode:
    """Node in the causal failure graph."""
    node_id: str
    category: str
    label: str
    severity: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RootCauseEdge:
    """Directed causal relationship: source_node -> target_node."""
    source_id: str
    target_id: str
    relation: str = "CAUSES"   # e.g., "CAUSES", "EXACERBATES", "TRIGGERS"
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RootCauseGraph:
    """Lightweight directed causal failure graph."""
    nodes: List[RootCauseNode] = field(default_factory=list)
    edges: List[RootCauseEdge] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }


@dataclass
class OperationalRecommendation:
    """Actionable advice tied strictly to detected findings and evidence."""
    recommendation_id: str
    category: str
    priority: str       # "LOW", "MEDIUM", "HIGH", "URGENT"
    issue: str
    evidence: str
    action: str
    expected_benefit: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PostIncidentReview:
    """Structured, audit-ready operational review document."""
    run_id: str
    scenario_id: str
    generated_at: str
    overall_severity: str       # "NORMAL", "MINOR_ISSUES", "ELEVATED_RISK", "CRITICAL_FAILURE"
    resilience_score: float
    summary: str
    metrics: Dict[str, Any]
    findings: List[PostIncidentFinding] = field(default_factory=list)
    root_cause_graph: RootCauseGraph = field(default_factory=RootCauseGraph)
    cascading_failures: List[List[str]] = field(default_factory=list)
    recommendations: List[OperationalRecommendation] = field(default_factory=list)
    key_events: List[Dict[str, Any]] = field(default_factory=list)
    analysis_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "generated_at": self.generated_at,
            "overall_severity": self.overall_severity,
            "resilience_score": self.resilience_score,
            "summary": self.summary,
            "metrics": self.metrics,
            "findings": [f.to_dict() for f in self.findings],
            "root_cause_graph": self.root_cause_graph.to_dict(),
            "cascading_failures": self.cascading_failures,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "key_events": self.key_events,
            "analysis_hash": self.analysis_hash,
        }


class PostIncidentReviewEngine:
    """Deterministic Rule-Based Post-Incident Review & Root-Cause Analyzer."""

    # Configurable evaluation thresholds
    DISPATCH_ETA_WARN_THRESHOLD = 8.0     # minutes
    DISPATCH_ETA_CRIT_THRESHOLD = 15.0    # minutes
    ZONE_DEFICIT_THRESHOLD = 1            # units in zone
    FLEET_UTIL_HIGH_THRESHOLD = 85.0      # %
    HOSP_UTIL_HIGH_THRESHOLD = 90.0       # %
    MCI_WAITING_WARN_THRESHOLD = 1        # casualties
    MCI_WAITING_CRIT_THRESHOLD = 5        # casualties

    @classmethod
    def generate_review(cls, artifact: ReplayArtifact) -> PostIncidentReview:
        """Analyze a ReplayArtifact and construct an end-to-end PostIncidentReview."""
        analysis = ReplayAnalyzer.analyze(artifact)
        events = artifact.events or []
        snapshots = artifact.snapshots or []

        findings: List[PostIncidentFinding] = []
        recommendations: List[OperationalRecommendation] = []
        graph_nodes: List[RootCauseNode] = []
        graph_edges: List[RootCauseEdge] = []
        cascading_chains: List[List[str]] = []

        # --------------------------------------------------------------
        # RULE A: Dispatch Delay
        # --------------------------------------------------------------
        avg_eta = analysis.fleet_metrics.get("average_dispatch_eta_minutes", 0.0)
        delayed_events = [
            e for e in events
            if e.get("event_type") == "DISPATCH" and e.get("payload", {}).get("eta_minutes", 0) > cls.DISPATCH_ETA_WARN_THRESHOLD
        ]
        if avg_eta > cls.DISPATCH_ETA_WARN_THRESHOLD or len(delayed_events) > 0:
            sev = "CRITICAL" if avg_eta > cls.DISPATCH_ETA_CRIT_THRESHOLD or len(delayed_events) >= 5 else "WARNING"
            f_id = f"FIND_DISP_{len(findings)+1}"
            r_id = f"REC_DISP_{len(recommendations)+1}"

            causes = []
            if analysis.peak_en_route >= 40:
                causes.append("Fleet saturation under concurrent incident volume")
            if analysis.peak_repositioning == 0:
                causes.append("Lack of proactive fleet repositioning to incident clusters")
            if not causes:
                causes.append("Insufficient nearby available ambulances in target zones")

            findings.append(PostIncidentFinding(
                finding_id=f_id,
                category="DISPATCH",
                severity=sev,
                confidence=0.95,
                title="Excessive Emergency Response ETA",
                description=f"Average dispatch ETA reached {avg_eta:.2f}m. {len(delayed_events)} dispatches exceeded {cls.DISPATCH_ETA_WARN_THRESHOLD}m threshold.",
                evidence={
                    "average_eta_minutes": avg_eta,
                    "delayed_dispatch_count": len(delayed_events),
                    "sample_event_ids": [e.get("event_id") for e in delayed_events[:5]],
                },
                measurable_impact=f"Prolonged pre-hospital transit times by up to {max((e.get('payload',{}).get('eta_minutes',0) for e in delayed_events), default=0):.1f}m.",
                potential_causes=causes,
                recommendation_id=r_id,
            ))
            recommendations.append(OperationalRecommendation(
                recommendation_id=r_id,
                category="DISPATCH",
                priority="HIGH" if sev == "CRITICAL" else "MEDIUM",
                issue="High ambulance dispatch arrival delays",
                evidence=f"{len(delayed_events)} units dispatched with ETA > {cls.DISPATCH_ETA_WARN_THRESHOLD}m",
                action="Increase baseline staging density in underserved sectors or lower fleet repositioning triggers.",
                expected_benefit="Reduce mean initial response ETA by 20–35%.",
            ))
            graph_nodes.append(RootCauseNode(
                node_id="DISPATCH_DELAY",
                category="DISPATCH",
                label="Dispatch Response Delay",
                severity=sev,
                details={"average_eta": avg_eta, "delayed_count": len(delayed_events)},
            ))

        # --------------------------------------------------------------
        # RULE B: Hospital & ICU Saturation
        # --------------------------------------------------------------
        sat_events = [e for e in events if e.get("event_type") == "HOSPITAL_SATURATED"]
        h_metrics = analysis.hospital_metrics
        icu_full_count = h_metrics.get("hospitals_reaching_icu_full_count", 0)
        hosp_full_count = h_metrics.get("hospitals_reaching_full_count", 0)

        if len(sat_events) > 0 or icu_full_count > 0 or hosp_full_count > 0:
            sev = "CRITICAL" if icu_full_count >= 3 or hosp_full_count >= 5 or len(sat_events) >= 5 else "WARNING"
            f_id = f"FIND_HOSP_{len(findings)+1}"
            r_id = f"REC_HOSP_{len(recommendations)+1}"

            causes = [
                "Heavy casualty convergence on primary emergency receiving centers",
                "Limited citywide ICU bed elasticity during mass casualty surge",
            ]
            if h_metrics.get("hospitals_used_count", 0) < 5 and (hosp_full_count > 0 or icu_full_count > 0):
                causes.append("Inadequate destination dispersal across secondary regional hospitals")

            findings.append(PostIncidentFinding(
                finding_id=f_id,
                category="HOSPITAL",
                severity=sev,
                confidence=0.92,
                title="Facility Bed & ICU Capacity Exhaustion",
                description=f"{len(sat_events)} hospital saturation events recorded. {icu_full_count} facilities exhausted critical ICU capacity.",
                evidence={
                    "saturation_event_count": len(sat_events),
                    "hospitals_full_count": hosp_full_count,
                    "icu_full_count": icu_full_count,
                    "peak_projected_utilization": h_metrics.get("peak_projected_utilization", 0.0),
                },
                measurable_impact=f"{hosp_full_count} facilities forced into bypass/diversion state.",
                potential_causes=causes,
                recommendation_id=r_id,
            ))
            recommendations.append(OperationalRecommendation(
                recommendation_id=r_id,
                category="HOSPITAL",
                priority="URGENT" if sev == "CRITICAL" else "HIGH",
                issue="Hospital and critical care ICU saturation",
                evidence=f"{len(sat_events)} saturation events with {icu_full_count} ICU facilities depleted",
                action="Enforce strict tertiary ICU preservation for P1 trauma and route stable P2/P3 patients to secondary centers.",
                expected_benefit="Eliminate hospital bypass conditions and preserve critical ICU beds.",
            ))
            graph_nodes.append(RootCauseNode(
                node_id="HOSPITAL_SATURATION",
                category="HOSPITAL",
                label="Hospital Capacity Exhaustion",
                severity=sev,
                details={"saturation_events": len(sat_events), "icu_full": icu_full_count},
            ))

        # --------------------------------------------------------------
        # RULE C: Fleet Coverage & Zone Deficits
        # --------------------------------------------------------------
        zone_deficit_snaps = []
        for s in snapshots:
            cov = s.get("coverage_summary", {})
            if cov.get("deficit_zones_count", 0) > 0:
                zone_deficit_snaps.append(s.get("sim_time"))

        if len(zone_deficit_snaps) > 0:
            sev = "CRITICAL" if len(zone_deficit_snaps) >= len(snapshots) * 0.5 else "WARNING"
            f_id = f"FIND_COV_{len(findings)+1}"
            r_id = f"REC_COV_{len(recommendations)+1}"

            findings.append(PostIncidentFinding(
                finding_id=f_id,
                category="FLEET",
                severity=sev,
                confidence=0.88,
                title="Persistent Operational Zone Coverage Deficit",
                description=f"Zone coverage deficits detected across {len(zone_deficit_snaps)} recorded simulation snapshots.",
                evidence={
                    "deficit_snapshot_times": zone_deficit_snaps[:10],
                    "total_deficit_intervals": len(zone_deficit_snaps),
                },
                measurable_impact="Left key sectors with zero available staging ambulances.",
                potential_causes=[
                    "High concentration of simultaneous incidents draining local staging units",
                    "Insufficient dynamic fleet repositioning response",
                ],
                recommendation_id=r_id,
            ))
            recommendations.append(OperationalRecommendation(
                recommendation_id=r_id,
                category="FLEET",
                priority="HIGH",
                issue="Persistent zone coverage deficits",
                evidence=f"Deficits logged in {len(zone_deficit_snaps)} snapshot intervals",
                action="Trigger autonomous fleet repositioning when zone available count drops below 2.",
                expected_benefit="Restore coverage parity across all 6 Jaipur operational zones.",
            ))
            graph_nodes.append(RootCauseNode(
                node_id="ZONE_DEFICIT",
                category="FLEET",
                label="Zone Fleet Deficit",
                severity=sev,
                details={"intervals": len(zone_deficit_snaps)},
            ))

        # --------------------------------------------------------------
        # RULE D: MCI Evacuation Delay & Waiting Casualties
        # --------------------------------------------------------------
        m_metrics = analysis.mci_metrics
        unresolved_mci = m_metrics.get("unresolved_mci_casualties", 0)
        total_mci_cas = sum(e.get("payload", {}).get("casualty_count", 0) for e in events if e.get("event_type") == "MCI_DECLARED")
        mci_count = analysis.mci_count

        if mci_count > 0:
            sev = "CRITICAL" if unresolved_mci > cls.MCI_WAITING_CRIT_THRESHOLD else ("WARNING" if (unresolved_mci > 0 or total_mci_cas >= 15) else "INFO")
            f_id = f"FIND_MCI_{len(findings)+1}"
            r_id = f"REC_MCI_{len(recommendations)+1}"

            causes = []
            if analysis.peak_en_route >= 35:
                causes.append("Ambulance queueing due to fleet bandwidth exhaustion")
            if hosp_full_count > 0:
                causes.append("Hospital intake bottlenecks restricting casualty transfers")
            if not causes:
                causes.append("Mass-casualty triage concentration requiring multi-wave dispatch")

            findings.append(PostIncidentFinding(
                finding_id=f_id,
                category="MCI",
                severity=sev,
                confidence=0.94,
                title="MCI Evacuation Delay & Casualty Backlog",
                description=f"{unresolved_mci} out of {total_mci_cas} MCI casualties remained un-evacuated at scenario conclusion.",
                evidence={
                    "total_mci_casualties": total_mci_cas,
                    "unresolved_mci_casualties": unresolved_mci,
                    "mci_count": mci_count,
                },
                measurable_impact=f"Delayed acute trauma evacuation for {unresolved_mci} patients.",
                potential_causes=causes,
                recommendation_id=r_id,
            ))
            recommendations.append(OperationalRecommendation(
                recommendation_id=r_id,
                category="MCI",
                priority="URGENT" if sev == "CRITICAL" else "HIGH",
                issue="MCI casualty evacuation backlog",
                evidence=f"{unresolved_mci}/{total_mci_cas} unevacuated casualties",
                action="Authorize immediate multi-zone ambulance interception and activate surge hospital trauma bays.",
                expected_benefit="Clear MCI scene within 15 minutes of declaration.",
            ))
            graph_nodes.append(RootCauseNode(
                node_id="MCI_BACKLOG",
                category="MCI",
                label="MCI Evacuation Backlog",
                severity=sev,
                details={"unresolved_casualties": unresolved_mci, "total_casualties": total_mci_cas},
            ))

        # --------------------------------------------------------------
        # RULE E: Repositioning Failure or Underutilization
        # --------------------------------------------------------------
        repo_starts = sum(1 for e in events if e.get("event_type") == "REPOSITION_START")
        if len(zone_deficit_snaps) > 2 and repo_starts == 0:
            f_id = f"FIND_REPO_{len(findings)+1}"
            r_id = f"REC_REPO_{len(recommendations)+1}"
            findings.append(PostIncidentFinding(
                finding_id=f_id,
                category="REPOSITIONING",
                severity="WARNING",
                confidence=0.85,
                title="Underutilized Fleet Repositioning During Deficits",
                description=f"Zero fleet repositioning moves initiated despite {len(zone_deficit_snaps)} zone deficit intervals.",
                evidence={"deficit_intervals": len(zone_deficit_snaps), "reposition_starts": repo_starts},
                measurable_impact="Allowed regional fleet imbalances to persist unmitigated.",
                potential_causes=["High repositioning threshold preventing automated dispatch of surplus units"],
                recommendation_id=r_id,
            ))
            recommendations.append(OperationalRecommendation(
                recommendation_id=r_id,
                category="REPOSITIONING",
                priority="MEDIUM",
                issue="Repositioning underutilization",
                evidence="0 repositions during persistent deficits",
                action="Lower automatic repositioning dispatch threshold to proactively rebalance available units.",
                expected_benefit="Prevent localized fleet starvation.",
            ))
            graph_nodes.append(RootCauseNode(
                node_id="REPOSITION_GAP",
                category="REPOSITIONING",
                label="Repositioning Underutilization",
                severity="WARNING",
                details={"deficit_intervals": len(zone_deficit_snaps)},
            ))

        # --------------------------------------------------------------
        # RULE F: Cascading Failure Detection & Causal Graph Synthesis
        # --------------------------------------------------------------
        node_ids = {n.node_id for n in graph_nodes}

        # Check sequence: ZONE_DEFICIT -> DISPATCH_DELAY
        if "ZONE_DEFICIT" in node_ids and "DISPATCH_DELAY" in node_ids:
            graph_edges.append(RootCauseEdge(source_id="ZONE_DEFICIT", target_id="DISPATCH_DELAY", relation="EXACERBATES", confidence=0.9))

        # Check sequence: DISPATCH_DELAY -> MCI_BACKLOG
        if "DISPATCH_DELAY" in node_ids and "MCI_BACKLOG" in node_ids:
            graph_edges.append(RootCauseEdge(source_id="DISPATCH_DELAY", target_id="MCI_BACKLOG", relation="CAUSES", confidence=0.95))

        # Check sequence: MCI_BACKLOG -> HOSPITAL_SATURATION
        if "MCI_BACKLOG" in node_ids and "HOSPITAL_SATURATION" in node_ids:
            graph_edges.append(RootCauseEdge(source_id="MCI_BACKLOG", target_id="HOSPITAL_SATURATION", relation="TRIGGERS", confidence=0.92))

        # Identify full cascading failure chains
        # Chain 1: ZONE_DEFICIT -> DISPATCH_DELAY -> MCI_BACKLOG -> HOSPITAL_SATURATION
        potential_chain = ["ZONE_DEFICIT", "DISPATCH_DELAY", "MCI_BACKLOG", "HOSPITAL_SATURATION"]
        active_chain = [cid for cid in potential_chain if cid in node_ids]
        if len(active_chain) >= 3:
            cascading_chains.append(active_chain)

        # --------------------------------------------------------------
        # Overall Severity Evaluation
        # --------------------------------------------------------------
        has_critical = any(f.severity == "CRITICAL" for f in findings)
        r_score = analysis.resilience_score.get("overall", 100.0)
        if has_critical or r_score < 60.0 or len(cascading_chains) > 0:
            overall_sev = "CRITICAL_FAILURE"
        elif any(f.severity == "WARNING" for f in findings) or r_score < 80.0:
            overall_sev = "ELEVATED_RISK"
        elif len(findings) > 0:
            overall_sev = "MINOR_ISSUES"
        else:
            overall_sev = "NORMAL"

        # Summary Generation
        summary = (
            f"Scenario '{artifact.run_metadata.scenario_id}' evaluated with resilience score {r_score:.2f}/100. "
            f"Identified {len(findings)} operational findings ({sum(1 for f in findings if f.severity == 'CRITICAL')} critical). "
            f"{'Cascading failure chain detected.' if len(cascading_chains) > 0 else 'No systemic cascade observed.'}"
        )

        # Key Events Extraction
        key_evs = [
            {
                "sim_time": e.get("sim_time"),
                "event_type": e.get("event_type"),
                "description": e.get("payload", {}).get("description", str(e.get("event_type"))),
            }
            for e in events
            if e.get("event_type") in ("MCI_DECLARED", "HOSPITAL_SATURATED", "REPOSITION_START", "REDIRECTION")
        ][:15]

        # Deterministic PIR Hash Calculation (independent of generated_at)
        hash_payload = {
            "scenario_id": artifact.run_metadata.scenario_id,
            "overall_severity": overall_sev,
            "resilience_score": round(r_score, 2),
            "findings": [f.finding_id for f in findings],
            "recommendations": [r.recommendation_id for r in recommendations],
            "cascading_chains": cascading_chains,
            "nodes": [n.node_id for n in graph_nodes],
            "edges": [(e.source_id, e.target_id) for e in graph_edges],
        }
        pir_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]

        return PostIncidentReview(
            run_id=artifact.run_metadata.run_id,
            scenario_id=artifact.run_metadata.scenario_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            overall_severity=overall_sev,
            resilience_score=round(r_score, 2),
            summary=summary,
            metrics=analysis.to_dict(),
            findings=findings,
            root_cause_graph=RootCauseGraph(nodes=graph_nodes, edges=graph_edges),
            cascading_failures=cascading_chains,
            recommendations=recommendations,
            key_events=key_evs,
            analysis_hash=pir_hash,
        )

    @classmethod
    def compare_pir(cls, pir_a: PostIncidentReview, pir_b: PostIncidentReview) -> Dict[str, Any]:
        """Compare two Post-Incident Reviews to evaluate regression or improvement."""
        findings_a_titles = {f.title: f for f in pir_a.findings}
        findings_b_titles = {f.title: f for f in pir_b.findings}

        new_failures = [f.to_dict() for t, f in findings_b_titles.items() if t not in findings_a_titles]
        resolved_failures = [f.to_dict() for t, f in findings_a_titles.items() if t not in findings_b_titles]

        delta_resilience = round(pir_b.resilience_score - pir_a.resilience_score, 2)

        metrics_a = pir_a.metrics.get("fleet_metrics", {})
        metrics_b = pir_b.metrics.get("fleet_metrics", {})

        worsened_metrics = []
        improved_metrics = []

        eta_a = metrics_a.get("average_dispatch_eta_minutes", 0.0)
        eta_b = metrics_b.get("average_dispatch_eta_minutes", 0.0)
        if eta_b > eta_a:
            worsened_metrics.append({"metric": "average_dispatch_eta_minutes", "delta": round(eta_b - eta_a, 2)})
        elif eta_b < eta_a:
            improved_metrics.append({"metric": "average_dispatch_eta_minutes", "delta": round(eta_b - eta_a, 2)})

        success_a = metrics_a.get("dispatch_success_ratio_pct", 100.0)
        success_b = metrics_b.get("dispatch_success_ratio_pct", 100.0)
        if success_b < success_a:
            worsened_metrics.append({"metric": "dispatch_success_ratio_pct", "delta": round(success_b - success_a, 2)})
        elif success_b > success_a:
            improved_metrics.append({"metric": "dispatch_success_ratio_pct", "delta": round(success_b - success_a, 2)})

        return {
            "run_id_a": pir_a.run_id,
            "run_id_b": pir_b.run_id,
            "resilience_score_a": pir_a.resilience_score,
            "resilience_score_b": pir_b.resilience_score,
            "delta_resilience": delta_resilience,
            "new_failures": new_failures,
            "resolved_failures": resolved_failures,
            "worsened_metrics": worsened_metrics,
            "improved_metrics": improved_metrics,
            "severity_change": f"{pir_a.overall_severity} -> {pir_b.overall_severity}",
        }

    @classmethod
    def export_report(cls, pir: PostIncidentReview, format: str = "json") -> Dict[str, Any]:
        """Export PIR in JSON, Markdown, or clean HTML format."""
        if format.lower() == "markdown":
            md_lines = [
                f"# Post-Incident Review: {pir.scenario_id}",
                f"**Run ID:** `{pir.run_id}` | **Severity:** `{pir.overall_severity}` | **Resilience Score:** `{pir.resilience_score}/100`",
                f"**Generated:** {pir.generated_at} | **Deterministic Hash:** `{pir.analysis_hash}`",
                "",
                "## Executive Summary",
                pir.summary,
                "",
                "## Detected Operational Findings",
            ]
            if not pir.findings:
                md_lines.append("*No significant operational failures detected.*")
            else:
                for f in pir.findings:
                    md_lines.extend([
                        f"### [{f.severity}] {f.title} ({f.category})",
                        f"- **Description:** {f.description}",
                        f"- **Impact:** {f.measurable_impact}",
                        f"- **Potential Causes:** {', '.join(f.potential_causes)}",
                        "",
                    ])

            md_lines.extend([
                "## Root-Cause Causal Analysis",
                f"- **Causal Nodes:** {len(pir.root_cause_graph.nodes)}",
                f"- **Causal Edges:** {len(pir.root_cause_graph.edges)}",
            ])
            for edge in pir.root_cause_graph.edges:
                md_lines.append(f"  - `{edge.source_id}` --({edge.relation})--> `{edge.target_id}`")

            if pir.cascading_failures:
                md_lines.extend(["", "## Cascading Failures"])
                for idx, chain in enumerate(pir.cascading_failures, 1):
                    md_lines.append(f"{idx}. **Chain:** {' -> '.join(chain)}")

            md_lines.extend(["", "## Operational Recommendations"])
            if not pir.recommendations:
                md_lines.append("*No corrective actions required.*")
            else:
                for r in pir.recommendations:
                    md_lines.extend([
                        f"- **[{r.priority}] {r.issue}**",
                        f"  - *Action:* {r.action}",
                        f"  - *Expected Benefit:* {r.expected_benefit}",
                    ])

            return {"format": "markdown", "content": "\n".join(md_lines)}

        elif format.lower() == "html":
            html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>RAAH PIR Report - {pir.scenario_id}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; line-height: 1.5; }}
h1, h2, h3 {{ color: #38bdf8; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }}
.CRITICAL {{ background: #ef4444; color: white; }}
.WARNING {{ background: #f59e0b; color: black; }}
.card {{ background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 14px; margin-bottom: 12px; }}
</style>
</head>
<body>
<h1>Post-Incident Review: {pir.scenario_id}</h1>
<div>Run ID: <code>{pir.run_id}</code> | Resilience Score: <b>{pir.resilience_score}/100</b></div>
<h2>Executive Summary</h2>
<p>{pir.summary}</p>
<h2>Operational Findings</h2>
{"".join(f'<div class="card"><span class="badge {f.severity}">{f.severity}</span> <b>{f.title}</b><p>{f.description}</p></div>' for f in pir.findings)}
<h2>Recommendations</h2>
<ul>{"".join(f'<li><b>[{r.priority}]</b> {r.action} (Benefit: {r.expected_benefit})</li>' for r in pir.recommendations)}</ul>
</body></html>"""
            return {"format": "html", "content": html}

        return {"format": "json", "content": pir.to_dict()}
