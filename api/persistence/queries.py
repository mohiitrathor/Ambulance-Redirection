"""
RAAH Historical Analytics Queries
=================================

High-performance read-only queries executing against local SQLite.
Used exclusively by the /analytics/* API endpoints.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path

from api.persistence.db import get_connection


def list_runs(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Return all simulation runs with summary counts."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                r.run_id,
                r.started_at,
                r.ended_at,
                r.status,
                r.total_ticks,
                r.final_sim_time,
                r.notes,
                COUNT(DISTINCT i.incident_id) AS total_incidents,
                COUNT(DISTINCT rd.id) AS total_redirections
            FROM simulation_runs r
            LEFT JOIN historical_incidents i ON r.run_id = i.run_id
            LEFT JOIN historical_redirections rd ON r.run_id = rd.run_id AND rd.decision_type = 'REDIRECTED'
            GROUP BY r.run_id
            ORDER BY r.run_id DESC
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_run_summary(run_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Compute aggregate analytical KPIs for a specific run."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        # 1. Fetch run info
        cursor.execute("SELECT * FROM simulation_runs WHERE run_id = ?", (run_id,))
        run_row = cursor.fetchone()
        if not run_row:
            return None
        run_data = dict(run_row)

        # 2. Incident counts and breakdowns
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_incidents,
                AVG(ml_confidence) as avg_confidence
            FROM historical_incidents
            WHERE run_id = ?
            """,
            (run_id,),
        )
        inc_agg = dict(cursor.fetchone())

        # Priority breakdown
        cursor.execute(
            """
            SELECT priority, COUNT(*) as count
            FROM historical_incidents
            WHERE run_id = ?
            GROUP BY priority
            """,
            (run_id,),
        )
        priority_map = {f"P{row['priority']}": row['count'] for row in cursor.fetchall()}
        for p in ["P1", "P2", "P3", "P4", "P5"]:
            priority_map.setdefault(p, 0)

        # Severity breakdown
        cursor.execute(
            """
            SELECT predicted_severity, COUNT(*) as count
            FROM historical_incidents
            WHERE run_id = ?
            GROUP BY predicted_severity
            """,
            (run_id,),
        )
        severity_map = {row['predicted_severity']: row['count'] for row in cursor.fetchall()}

        # 3. Dispatch & ETA metrics
        cursor.execute(
            """
            SELECT 
                AVG(initial_eta_minutes) as avg_initial_eta,
                SUM(CASE WHEN status = 'ARRIVED' THEN 1 ELSE 0 END) as arrived_count,
                SUM(CASE WHEN status != 'ARRIVED' THEN 1 ELSE 0 END) as in_transit_count
            FROM historical_dispatches
            WHERE run_id = ?
            """,
            (run_id,),
        )
        disp_agg = dict(cursor.fetchone())

        # 4. Redirection metrics
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_redirections,
                SUM(CASE WHEN trigger_type = 'AI_AUTONOMOUS' THEN 1 ELSE 0 END) as ai_count,
                SUM(CASE WHEN trigger_type = 'OPERATOR_MANUAL' THEN 1 ELSE 0 END) as operator_count,
                AVG(eta_saved) as avg_eta_saved,
                SUM(eta_saved) as total_eta_saved
            FROM historical_redirections
            WHERE run_id = ? AND decision_type = 'REDIRECTED'
            """,
            (run_id,),
        )
        redir_agg = dict(cursor.fetchone())

        # 5. Saturation events
        cursor.execute(
            """
            SELECT COUNT(*) as saturation_events
            FROM historical_events
            WHERE run_id = ? AND event_type = 'HOSPITAL_FULL'
            """,
            (run_id,),
        )
        sat_agg = dict(cursor.fetchone())

        total_inc = inc_agg["total_incidents"] or 0
        total_redir = redir_agg["total_redirections"] or 0
        redir_rate = round((total_redir / total_inc * 100.0), 2) if total_inc > 0 else 0.0

        return {
            "run_id": run_data["run_id"],
            "status": run_data["status"],
            "started_at": run_data["started_at"],
            "ended_at": run_data["ended_at"],
            "final_sim_time": run_data["final_sim_time"],
            "total_incidents": total_inc,
            "incidents_by_priority": priority_map,
            "incidents_by_severity": severity_map,
            "average_ml_confidence": round(inc_agg["avg_confidence"] or 0.0, 4),
            "average_initial_eta": round(disp_agg["avg_initial_eta"] or 0.0, 2),
            "arrived_count": disp_agg["arrived_count"] or 0,
            "in_transit_count": disp_agg["in_transit_count"] or 0,
            "redirections": {
                "total": total_redir,
                "ai_autonomous": redir_agg["ai_count"] or 0,
                "operator_manual": redir_agg["operator_count"] or 0,
                "redirection_rate_pct": redir_rate,
                "total_eta_saved": round(redir_agg["total_eta_saved"] or 0.0, 2),
                "avg_eta_saved": round(redir_agg["avg_eta_saved"] or 0.0, 2),
            },
            "hospital_saturation_events": sat_agg["saturation_events"] or 0,
        }
    finally:
        conn.close()


def get_incidents(
    run_id: int,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Return paginated incidents and their dispatch assignments for a run."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                i.incident_id,
                i.source,
                i.condition,
                i.predicted_severity,
                i.priority,
                i.ml_confidence,
                i.patient_lat,
                i.patient_lon,
                i.dispatched_sim_time,
                d.ambulance_id,
                d.ambulance_type,
                d.initial_hospital_id,
                d.final_hospital_id,
                d.initial_eta_minutes,
                d.final_eta_minutes,
                d.status as dispatch_status,
                d.arrived_sim_time
            FROM historical_incidents i
            LEFT JOIN historical_dispatches d ON i.run_id = d.run_id AND i.incident_id = d.incident_id
            WHERE i.run_id = ?
            ORDER BY i.incident_id DESC
            LIMIT ? OFFSET ?
            """,
            (run_id, limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_decisions(run_id: int, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Return all historical redirection decisions for a run."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM historical_redirections
            WHERE run_id = ?
            ORDER BY id DESC
            """,
            (run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_events(
    run_id: int,
    limit: int = 100,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Return chronological historical events for a run."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM historical_events
            WHERE run_id = ?
            ORDER BY sim_time DESC, id DESC
            LIMIT ?
            """,
            (run_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
