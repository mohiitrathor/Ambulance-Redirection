"""
RAAH Asynchronous Persistence Bridge
====================================

Decouples live in-memory simulation state and FastAPI dispatch operations from
disk I/O. All operational telemetry is enqueued as immutable payloads and written
by an isolated background daemon worker to SQLite.

Guarantees:
  1. Live dispatch latency overhead is negligible (< 0.01ms enqueue).
  2. Persistence failures or disk locks NEVER fail API requests or crash simulation.
  3. The persistence worker thread NEVER acquires manager.lock.
  4. Run boundaries are preserved in strict chronological order.
"""

import queue
import sqlite3
import threading
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path

from api.persistence.db import get_connection, init_db

logger = logging.getLogger("raah.persistence.bridge")


class PersistenceBridge:
    """
    Background worker bridge between live Simulator events and SQLite.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        self._queue: queue.Queue = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._active_run_id: Optional[int] = None
        self._run_id_lock = threading.Lock()
        self._is_started = False

    @property
    def active_run_id(self) -> Optional[int]:
        with self._run_id_lock:
            return self._active_run_id

    def set_active_run_id(self, run_id: int):
        with self._run_id_lock:
            self._active_run_id = int(run_id)

    # ----------------------------------------------------------
    # LIFECYCLE MANAGEMENT
    # ----------------------------------------------------------

    def start(self):
        """Initialize the DB schema and start the background write worker."""
        if self._is_started:
            return

        init_db(self.db_path)
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="RAAH-PersistenceWorker",
            daemon=True,
        )
        self._worker_thread.start()
        self._is_started = True
        logger.info("PersistenceBridge worker thread started.")

    def shutdown(self, timeout: float = 3.0):
        """Cleanly drain pending writes and stop the worker thread."""
        if not self._is_started:
            return

        self.flush(timeout=timeout)
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)
        self._is_started = False
        logger.info("PersistenceBridge worker thread stopped.")

    def flush(self, timeout: float = 3.0):
        """Block until all currently queued write operations have been processed."""
        try:
            self._queue.join()
        except Exception as err:
            logger.warning("Error while flushing persistence queue: %s", err)

    # ----------------------------------------------------------
    # SYNCHRONOUS RUN OPERATIONS
    # ----------------------------------------------------------

    def create_run(self, notes: Optional[str] = None) -> int:
        """
        Synchronously create a new simulation run session in SQLite.
        Returns the allocated run_id.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            conn = get_connection(self.db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO simulation_runs (started_at, status, total_ticks, final_sim_time, notes)
                    VALUES (?, 'ACTIVE', 0, 0, ?)
                    """,
                    (now_iso, notes),
                )
                conn.commit()
                run_id = cursor.lastrowid
                self.set_active_run_id(run_id)
                logger.info("Created active simulation run #%d in SQLite.", run_id)
                return run_id
            finally:
                conn.close()
        except Exception as err:
            logger.error("Failed to create simulation run session in SQLite: %s", err)
            # Fallback to local auto-increment if SQLite fails so simulation never blocks
            with self._run_id_lock:
                fallback_id = (self._active_run_id or 0) + 1
                self._active_run_id = fallback_id
                return fallback_id

    def finalize_run(
        self,
        run_id: int,
        final_sim_time: int,
        total_ticks: int = 0,
        status: str = "COMPLETED",
    ):
        """
        Synchronously finalize a simulation run in SQLite.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            conn = get_connection(self.db_path)
            try:
                conn.execute(
                    """
                    UPDATE simulation_runs
                    SET ended_at = ?, status = ?, final_sim_time = ?, total_ticks = ?
                    WHERE run_id = ?
                    """,
                    (now_iso, status, int(final_sim_time), int(total_ticks), int(run_id)),
                )
                conn.commit()
                logger.info("Finalized simulation run #%d as %s (final_time=%dm).", run_id, status, final_sim_time)
            finally:
                conn.close()
        except Exception as err:
            logger.error("Failed to finalize simulation run #%d: %s", run_id, err)

    # ----------------------------------------------------------
    # ASYNCHRONOUS EVENT ENQUEUE (CALLED FROM SIMULATOR / API)
    # ----------------------------------------------------------

    def record_dispatch(
        self,
        run_id: int,
        incident_id: int,
        source: str,
        condition: str,
        predicted_severity: str,
        priority: int,
        ml_confidence: Optional[float],
        patient_lat: float,
        patient_lon: float,
        dispatched_sim_time: int,
        ambulance_id: str,
        ambulance_type: str,
        hospital_id: str,
        initial_eta_minutes: float,
        route_distance_km: Optional[float],
        traffic_level: Optional[str],
        road_condition: Optional[str],
    ):
        """Enqueue immutable incident & dispatch records for background SQLite insertion."""
        payload = {
            "type": "DISPATCH",
            "run_id": int(run_id),
            "incident_id": int(incident_id),
            "source": str(source),
            "condition": str(condition),
            "predicted_severity": str(predicted_severity),
            "priority": int(priority),
            "ml_confidence": float(ml_confidence) if ml_confidence is not None else None,
            "patient_lat": float(patient_lat),
            "patient_lon": float(patient_lon),
            "dispatched_sim_time": int(dispatched_sim_time),
            "ambulance_id": str(ambulance_id),
            "ambulance_type": str(ambulance_type),
            "hospital_id": str(hospital_id),
            "initial_eta_minutes": float(initial_eta_minutes),
            "route_distance_km": float(route_distance_km) if route_distance_km is not None else None,
            "traffic_level": str(traffic_level) if traffic_level is not None else "NORMAL",
            "road_condition": str(road_condition) if road_condition is not None else "GOOD",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._enqueue(payload)

    def record_redirection(
        self,
        run_id: int,
        incident_id: int,
        ambulance_id: str,
        decision_type: str,
        trigger_type: str,
        original_hospital_id: Optional[str],
        new_hospital_id: Optional[str],
        eta_before: Optional[float],
        eta_after: Optional[float],
        eta_saved: Optional[float],
        eta_improvement_pct: Optional[float],
        reason: str,
        sim_time: int,
    ):
        """Enqueue redirection decision for background SQLite insertion."""
        payload = {
            "type": "REDIRECTION",
            "run_id": int(run_id),
            "incident_id": int(incident_id),
            "ambulance_id": str(ambulance_id),
            "decision_type": str(decision_type),
            "trigger_type": str(trigger_type),
            "original_hospital_id": str(original_hospital_id) if original_hospital_id else None,
            "new_hospital_id": str(new_hospital_id) if new_hospital_id else None,
            "eta_before": float(eta_before) if eta_before is not None else None,
            "eta_after": float(eta_after) if eta_after is not None else None,
            "eta_saved": float(eta_saved) if eta_saved is not None else None,
            "eta_improvement_pct": float(eta_improvement_pct) if eta_improvement_pct is not None else None,
            "reason": str(reason),
            "sim_time": int(sim_time),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._enqueue(payload)

    def record_arrival(
        self,
        run_id: int,
        incident_id: int,
        ambulance_id: str,
        hospital_id: str,
        arrived_sim_time: int,
    ):
        """Enqueue ambulance arrival outcome."""
        payload = {
            "type": "ARRIVAL",
            "run_id": int(run_id),
            "incident_id": int(incident_id),
            "ambulance_id": str(ambulance_id),
            "hospital_id": str(hospital_id),
            "arrived_sim_time": int(arrived_sim_time),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._enqueue(payload)

    def record_event(
        self,
        run_id: int,
        event_type: str,
        sim_time: int,
        facility_or_unit_id: Optional[str],
        message: str,
    ):
        """Enqueue discrete operational event."""
        payload = {
            "type": "EVENT",
            "run_id": int(run_id),
            "event_type": str(event_type),
            "sim_time": int(sim_time),
            "facility_or_unit_id": str(facility_or_unit_id) if facility_or_unit_id else None,
            "message": str(message),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._enqueue(payload)

    def _enqueue(self, payload: Dict[str, Any]):
        """Place an immutable event into the thread-safe queue."""
        try:
            self._queue.put_nowait(payload)
        except Exception as err:
            logger.error("Failed to enqueue event for persistence: %s", err)

    # ----------------------------------------------------------
    # BACKGROUND WORKER LOOP (NO LOCK HELD)
    # ----------------------------------------------------------

    def _worker_loop(self):
        """
        Isolated background worker thread consuming queued events.
        Maintains its own dedicated SQLite connection with retries.
        """
        conn: Optional[sqlite3.Connection] = None

        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                try:
                    payload = self._queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                if conn is None:
                    try:
                        conn = get_connection(self.db_path)
                    except Exception as exc:
                        logger.error("Worker failed to connect to SQLite: %s", exc)
                        self._queue.task_done()
                        continue

                # Process payload with retry/backoff on database lock
                success = False
                for attempt in range(3):
                    try:
                        self._execute_write(conn, payload)
                        conn.commit()
                        success = True
                        break
                    except (sqlite3.OperationalError, sqlite3.DatabaseError) as db_err:
                        logger.warning(
                            "SQLite write attempt %d failed: %s. Retrying...",
                            attempt + 1,
                            db_err,
                        )
                        time.sleep(0.05 * (2 ** attempt))
                    except Exception as fatal_err:
                        logger.error("Permanent error processing event %s: %s", payload.get("type"), fatal_err)
                        break

                if not success:
                    logger.error("Failed to persist event after 3 attempts: %s", payload)

                self._queue.task_done()

            except Exception as loop_err:
                logger.error("Unexpected error in PersistenceBridge worker loop: %s", loop_err)

        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _execute_write(self, conn: sqlite3.Connection, p: Dict[str, Any]):
        """Execute the parameterized SQL statement for the specific event type."""
        p_type = p.get("type")

        if p_type == "DISPATCH":
            # 1. Insert incident record
            conn.execute(
                """
                INSERT OR IGNORE INTO historical_incidents (
                    run_id, incident_id, source, condition, predicted_severity,
                    priority, ml_confidence, patient_lat, patient_lon,
                    dispatched_sim_time, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p["run_id"], p["incident_id"], p["source"], p["condition"],
                    p["predicted_severity"], p["priority"], p["ml_confidence"],
                    p["patient_lat"], p["patient_lon"], p["dispatched_sim_time"],
                    p["created_at"],
                ),
            )

            # 2. Insert initial dispatch record
            conn.execute(
                """
                INSERT OR REPLACE INTO historical_dispatches (
                    run_id, incident_id, ambulance_id, ambulance_type,
                    initial_hospital_id, final_hospital_id, initial_eta_minutes,
                    final_eta_minutes, route_distance_km, traffic_level,
                    road_condition, dispatched_sim_time, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'EN_ROUTE', ?)
                """,
                (
                    p["run_id"], p["incident_id"], p["ambulance_id"], p["ambulance_type"],
                    p["hospital_id"], p["hospital_id"], p["initial_eta_minutes"],
                    p["initial_eta_minutes"], p["route_distance_km"], p["traffic_level"],
                    p["road_condition"], p["dispatched_sim_time"], p["created_at"],
                ),
            )

        elif p_type == "REDIRECTION":
            # 1. Log redirection decision
            conn.execute(
                """
                INSERT INTO historical_redirections (
                    run_id, incident_id, ambulance_id, decision_type, trigger_type,
                    original_hospital_id, new_hospital_id, eta_before, eta_after,
                    eta_saved, eta_improvement_pct, reason, sim_time, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p["run_id"], p["incident_id"], p["ambulance_id"], p["decision_type"],
                    p["trigger_type"], p["original_hospital_id"], p["new_hospital_id"],
                    p["eta_before"], p["eta_after"], p["eta_saved"],
                    p["eta_improvement_pct"], p["reason"], p["sim_time"],
                    p["created_at"],
                ),
            )

            # 2. Update dispatch target facility & status if redirected
            if p["decision_type"] == "REDIRECTED" and p["new_hospital_id"]:
                conn.execute(
                    """
                    UPDATE historical_dispatches
                    SET final_hospital_id = ?, final_eta_minutes = ?, status = 'REDIRECTED', updated_at = ?
                    WHERE run_id = ? AND incident_id = ?
                    """,
                    (
                        p["new_hospital_id"], p["eta_after"] or 0.0, p["created_at"],
                        p["run_id"], p["incident_id"],
                    ),
                )

        elif p_type == "ARRIVAL":
            conn.execute(
                """
                UPDATE historical_dispatches
                SET status = 'ARRIVED', arrived_sim_time = ?, updated_at = ?
                WHERE run_id = ? AND incident_id = ?
                """,
                (p["arrived_sim_time"], p["created_at"], p["run_id"], p["incident_id"]),
            )

        elif p_type == "EVENT":
            conn.execute(
                """
                INSERT INTO historical_events (
                    run_id, event_type, sim_time, facility_or_unit_id, message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    p["run_id"], p["event_type"], p["sim_time"],
                    p["facility_or_unit_id"], p["message"], p["created_at"],
                ),
            )


# Global singleton instance
persistence_bridge = PersistenceBridge()
