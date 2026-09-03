"""
RAAH SQLite State Persistence Store
===================================

Production-grade SQLite implementation of StatePersistenceStore.
Provides atomic checkpointing, WAL mode concurrency, cryptographic checksum
verification, and explicit failure semantics without holding long locks.
"""

import os
import json
import sqlite3
import logging
import uuid
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from api.settings import settings
from api.persistence.interface import (
    StatePersistenceStore,
    CheckpointRecord,
    IdempotencyRecord,
    PersistenceError,
    CorruptCheckpointError,
    IncompatibleSchemaError,
    CorruptStateError,
    DatabaseUnavailableError,
    DatabaseLockedError,
)
from api.persistence.serializer import (
    SCHEMA_VERSION,
    compute_state_checksum,
    validate_state_payload,
)

logger = logging.getLogger("raah.persistence.store")


class SQLiteStateStore(StatePersistenceStore):
    """
    SQLite-backed durable persistence store for DispatchState checkpoints.
    """

    def __init__(self, db_path: Optional[Path] = None, busy_timeout_ms: int = 5000):
        self.db_path = Path(db_path or settings.database_path).resolve()
        self.busy_timeout_ms = busy_timeout_ms

        # Metrics & Telemetry
        self.total_checkpoints_saved = 0
        self.last_checkpoint_id: Optional[str] = None
        self.last_checkpoint_sim_time: Optional[int] = None
        self.last_checkpoint_saved_at: Optional[str] = None
        self.last_error: Optional[str] = None
        self.consecutive_errors: int = 0

        self._ensure_storage_ready()

    def _ensure_storage_ready(self):
        """Ensure parent directories and SQLite schema are created safely."""
        try:
            os.makedirs(self.db_path.parent, exist_ok=True)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executescript("""
                    CREATE TABLE IF NOT EXISTS state_checkpoints (
                        checkpoint_id TEXT PRIMARY KEY,
                        simulation_time INTEGER NOT NULL,
                        schema_version INTEGER NOT NULL,
                        saved_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        checksum TEXT NOT NULL,
                        is_valid INTEGER DEFAULT 1,
                        metadata_json TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_chk_time ON state_checkpoints(simulation_time DESC, saved_at DESC);

                    CREATE TABLE IF NOT EXISTS state_store (
                        state_key TEXT PRIMARY KEY,
                        schema_version INTEGER NOT NULL,
                        simulation_time INTEGER NOT NULL,
                        updated_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        checksum TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS event_idempotency (
                        idempotency_key TEXT PRIMARY KEY,
                        source TEXT NOT NULL,
                        source_event_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        response_json TEXT NOT NULL,
                        first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        seen_count INTEGER DEFAULT 1,
                        correlation_id TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_idem_src_evt ON event_idempotency(source, source_event_id);
                """)
                conn.commit()
            logger.info("SQLiteStateStore initialized at %s", self.db_path)
        except Exception as err:
            self.last_error = str(err)
            self.consecutive_errors += 1
            logger.error("Failed to initialize SQLiteStateStore at %s: %s", self.db_path, err)
            raise DatabaseUnavailableError(f"Failed to initialize SQLite state store: {err}") from err

    def _get_connection(self) -> sqlite3.Connection:
        """Create a configured SQLite connection with WAL mode and busy timeout."""
        try:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=self.busy_timeout_ms / 1000.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms};")
            cursor.execute("PRAGMA synchronous = NORMAL;")
            return conn
        except sqlite3.OperationalError as err:
            err_str = str(err).lower()
            if "locked" in err_str or "busy" in err_str:
                raise DatabaseLockedError(f"SQLite database is locked: {err}") from err
            raise DatabaseUnavailableError(f"Failed to connect to SQLite: {err}") from err
        except Exception as err:
            raise DatabaseUnavailableError(f"Database connection error: {err}") from err

    # ==================================================================
    # CHECKPOINT PERSISTENCE
    # ==================================================================

    def save_checkpoint(
        self,
        state_data: Dict[str, Any],
        sim_time: int,
        metadata: Optional[Dict[str, Any]] = None,
        checkpoint_id: Optional[str] = None,
    ) -> CheckpointRecord:
        """
        Atomically persist a state snapshot into the state_checkpoints table.
        Computes SHA-256 checksum and commits in an immediate transaction.
        """
        cid = checkpoint_id or f"chk_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        saved_at = datetime.now(timezone.utc).isoformat()
        meta = metadata or {}

        # Validate structure before persisting
        is_valid, err_msg = validate_state_payload(state_data)
        if not is_valid:
            self.last_error = f"Payload validation failed: {err_msg}"
            self.consecutive_errors += 1
            logger.error("Checkpoint failed payload validation: %s", err_msg)
            raise CorruptStateError(f"Cannot save invalid checkpoint payload: {err_msg}")

        checksum = compute_state_checksum(state_data)
        payload_json = json.dumps(state_data, sort_keys=True, separators=(",", ":"))
        metadata_json = json.dumps(meta)
        schema_version = int(state_data.get("schema_version", SCHEMA_VERSION))

        start_t = time.perf_counter()
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE;")
            cursor.execute(
                """
                INSERT INTO state_checkpoints (
                    checkpoint_id, simulation_time, schema_version, saved_at,
                    payload_json, checksum, is_valid, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    cid,
                    int(sim_time),
                    schema_version,
                    saved_at,
                    payload_json,
                    checksum,
                    metadata_json,
                ),
            )
            conn.commit()
            duration_ms = (time.perf_counter() - start_t) * 1000.0

            # Update metrics
            self.total_checkpoints_saved += 1
            self.last_checkpoint_id = cid
            self.last_checkpoint_sim_time = int(sim_time)
            self.last_checkpoint_saved_at = saved_at
            self.consecutive_errors = 0
            self.last_error = None

            logger.info(
                "Checkpoint saved successfully: id=%s sim_time=%d duration=%.2fms",
                cid,
                sim_time,
                duration_ms,
                extra={"checkpoint_id": cid, "duration_ms": duration_ms},
            )

            return CheckpointRecord(
                checkpoint_id=cid,
                simulation_time=int(sim_time),
                schema_version=schema_version,
                saved_at=saved_at,
                payload=state_data,
                checksum=checksum,
                metadata=meta,
                is_valid=True,
            )
        except (DatabaseLockedError, DatabaseUnavailableError):
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self.consecutive_errors += 1
            raise
        except sqlite3.OperationalError as err:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self.consecutive_errors += 1
            self.last_error = str(err)
            err_str = str(err).lower()
            if "locked" in err_str or "busy" in err_str:
                raise DatabaseLockedError(f"Database locked while writing checkpoint: {err}") from err
            raise DatabaseUnavailableError(f"Operational error saving checkpoint: {err}") from err
        except Exception as err:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self.consecutive_errors += 1
            self.last_error = str(err)
            logger.error("Unexpected error saving checkpoint: %s", err)
            raise PersistenceError(f"Unexpected persistence failure: {err}") from err
        finally:
            if conn:
                conn.close()

    def load_latest_checkpoint(self) -> Optional[CheckpointRecord]:
        """
        Fetch and parse the newest checkpoint ordered by simulation_time and saved_at.
        Validates checksum and payload integrity.
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT checkpoint_id, simulation_time, schema_version, saved_at,
                       payload_json, checksum, is_valid, metadata_json
                FROM state_checkpoints
                WHERE is_valid = 1
                ORDER BY simulation_time DESC, saved_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_record(row)
        except (CorruptCheckpointError, IncompatibleSchemaError, CorruptStateError):
            raise
        except sqlite3.OperationalError as err:
            self.last_error = str(err)
            err_str = str(err).lower()
            if "locked" in err_str or "busy" in err_str:
                raise DatabaseLockedError(f"Database locked reading latest checkpoint: {err}") from err
            raise DatabaseUnavailableError(f"Database error reading checkpoint: {err}") from err
        except Exception as err:
            self.last_error = str(err)
            raise PersistenceError(f"Failed to load latest checkpoint: {err}") from err
        finally:
            if conn:
                conn.close()

    def load_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointRecord]:
        """
        Fetch and parse a specific checkpoint record by ID.
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT checkpoint_id, simulation_time, schema_version, saved_at,
                       payload_json, checksum, is_valid, metadata_json
                FROM state_checkpoints
                WHERE checkpoint_id = ?
                LIMIT 1
                """,
                (str(checkpoint_id),),
            )
            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_record(row)
        except (CorruptCheckpointError, IncompatibleSchemaError, CorruptStateError):
            raise
        except Exception as err:
            self.last_error = str(err)
            raise PersistenceError(f"Failed to load checkpoint '{checkpoint_id}': {err}") from err
        finally:
            if conn:
                conn.close()

    def list_checkpoints(self, limit: int = 50) -> List[CheckpointRecord]:
        """List recent checkpoints ordered newest first."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT checkpoint_id, simulation_time, schema_version, saved_at,
                       payload_json, checksum, is_valid, metadata_json
                FROM state_checkpoints
                ORDER BY simulation_time DESC, saved_at DESC
                LIMIT ?
                """,
                (max(1, limit),),
            )
            rows = cursor.fetchall()
            records = []
            for row in rows:
                try:
                    records.append(self._row_to_record(row))
                except Exception as ex:
                    logger.warning("Skipping invalid checkpoint row '%s': %s", row["checkpoint_id"], ex)
            return records
        except Exception as err:
            raise PersistenceError(f"Failed to list checkpoints: {err}") from err
        finally:
            if conn:
                conn.close()

    def _row_to_record(self, row: sqlite3.Row) -> CheckpointRecord:
        """Parse database row, verify checksum, and return CheckpointRecord."""
        cid = row["checkpoint_id"]
        raw_json = row["payload_json"]
        expected_checksum = row["checksum"]

        try:
            payload = json.loads(raw_json)
        except Exception as json_err:
            logger.error("Checkpoint '%s' has malformed JSON payload: %s", cid, json_err)
            raise CorruptCheckpointError(f"Checkpoint '{cid}' payload is not valid JSON: {json_err}") from json_err

        computed_checksum = compute_state_checksum(payload)
        if computed_checksum != expected_checksum:
            logger.error(
                "Checksum mismatch for checkpoint '%s': expected %s, computed %s",
                cid,
                expected_checksum,
                computed_checksum,
            )
            raise CorruptCheckpointError(
                f"Checkpoint '{cid}' checksum verification failed (expected {expected_checksum[:8]}..., got {computed_checksum[:8]}...)."
            )

        metadata = {}
        if row["metadata_json"]:
            try:
                metadata = json.loads(row["metadata_json"])
            except Exception:
                pass

        return CheckpointRecord(
            checkpoint_id=cid,
            simulation_time=int(row["simulation_time"]),
            schema_version=int(row["schema_version"]),
            saved_at=row["saved_at"],
            payload=payload,
            checksum=expected_checksum,
            metadata=metadata,
            is_valid=bool(row["is_valid"]),
        )

    # ==================================================================
    # ARBITRARY STATE STORE
    # ==================================================================

    def save_state(self, state_data: Dict[str, Any], key: str = "current_state") -> bool:
        """Atomically upsert an arbitrary state snapshot under key."""
        is_valid, err_msg = validate_state_payload(state_data)
        if not is_valid:
            raise CorruptStateError(f"Invalid state data: {err_msg}")

        checksum = compute_state_checksum(state_data)
        payload_json = json.dumps(state_data, sort_keys=True, separators=(",", ":"))
        updated_at = datetime.now(timezone.utc).isoformat()
        sim_time = int(state_data.get("simulation_time", 0))
        schema_version = int(state_data.get("schema_version", SCHEMA_VERSION))

        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO state_store (state_key, schema_version, simulation_time, updated_at, payload_json, checksum)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    schema_version=excluded.schema_version,
                    simulation_time=excluded.simulation_time,
                    updated_at=excluded.updated_at,
                    payload_json=excluded.payload_json,
                    checksum=excluded.checksum
                """,
                (key, schema_version, sim_time, updated_at, payload_json, checksum),
            )
            conn.commit()
            return True
        except Exception as err:
            if conn:
                conn.rollback()
            raise PersistenceError(f"Failed to save state under key '{key}': {err}") from err
        finally:
            if conn:
                conn.close()

    def load_state(self, key: str = "current_state") -> Optional[Dict[str, Any]]:
        """Load and verify an arbitrary state snapshot by key."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT schema_version, simulation_time, updated_at, payload_json, checksum
                FROM state_store
                WHERE state_key = ?
                """,
                (key,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            payload = json.loads(row["payload_json"])
            expected_checksum = row["checksum"]
            if compute_state_checksum(payload) != expected_checksum:
                raise CorruptCheckpointError(f"State checksum mismatch for key '{key}'.")
            return payload
        except Exception as err:
            raise PersistenceError(f"Failed to load state key '{key}': {err}") from err
        finally:
            if conn:
                conn.close()

    # ==================================================================
    # EVENT DEDUPLICATION & IDEMPOTENCY
    # ==================================================================

    def get_idempotency_record(self, source: str, source_event_id: str) -> Optional[IdempotencyRecord]:
        """Lookup idempotency record by composite key (source + source_event_id)."""
        key = f"{source}:{source_event_id}"
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT idempotency_key, source, source_event_id, event_type,
                       status, response_json, first_seen_at, last_seen_at, seen_count, correlation_id
                FROM event_idempotency
                WHERE idempotency_key = ?
                LIMIT 1
                """,
                (key,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            resp_payload = json.loads(row["response_json"])
            return IdempotencyRecord(
                idempotency_key=row["idempotency_key"],
                source=row["source"],
                source_event_id=row["source_event_id"],
                event_type=row["event_type"],
                status=row["status"],
                response_payload=resp_payload,
                first_seen_at=row["first_seen_at"],
                last_seen_at=row["last_seen_at"],
                seen_count=int(row["seen_count"]),
                correlation_id=row["correlation_id"],
            )
        except (DatabaseUnavailableError, DatabaseLockedError):
            raise
        except Exception as err:
            self.last_error = str(err)
            raise PersistenceError(f"Failed to read idempotency record: {err}") from err
        finally:
            if conn:
                conn.close()

    def save_idempotency_record(self, record: IdempotencyRecord) -> bool:
        """Atomically persist an idempotency record in an immediate transaction."""
        key = record.idempotency_key or f"{record.source}:{record.source_event_id}"
        resp_json = json.dumps(record.response_payload, sort_keys=True, separators=(",", ":"))
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE;")
            cursor.execute(
                """
                INSERT INTO event_idempotency (
                    idempotency_key, source, source_event_id, event_type,
                    status, response_json, first_seen_at, last_seen_at, seen_count, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    last_seen_at=excluded.last_seen_at,
                    seen_count=event_idempotency.seen_count + 1
                """,
                (
                    key,
                    record.source,
                    record.source_event_id,
                    record.event_type,
                    record.status,
                    resp_json,
                    record.first_seen_at,
                    record.last_seen_at,
                    record.seen_count,
                    record.correlation_id,
                ),
            )
            conn.commit()
            return True
        except (DatabaseUnavailableError, DatabaseLockedError):
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        except Exception as err:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self.last_error = str(err)
            raise PersistenceError(f"Failed to save idempotency record: {err}") from err
        finally:
            if conn:
                conn.close()

    def increment_idempotency_seen(self, source: str, source_event_id: str) -> Optional[IdempotencyRecord]:
        """Atomically increment seen_count and return updated record."""
        key = f"{source}:{source_event_id}"
        now_str = datetime.now(timezone.utc).isoformat()
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE;")
            cursor.execute(
                """
                UPDATE event_idempotency
                SET seen_count = seen_count + 1, last_seen_at = ?
                WHERE idempotency_key = ?
                """,
                (now_str, key),
            )
            conn.commit()

            # Retrieve updated row
            cursor.execute(
                """
                SELECT idempotency_key, source, source_event_id, event_type,
                       status, response_json, first_seen_at, last_seen_at, seen_count, correlation_id
                FROM event_idempotency
                WHERE idempotency_key = ?
                LIMIT 1
                """,
                (key,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            resp_payload = json.loads(row["response_json"])
            return IdempotencyRecord(
                idempotency_key=row["idempotency_key"],
                source=row["source"],
                source_event_id=row["source_event_id"],
                event_type=row["event_type"],
                status=row["status"],
                response_payload=resp_payload,
                first_seen_at=row["first_seen_at"],
                last_seen_at=row["last_seen_at"],
                seen_count=int(row["seen_count"]),
                correlation_id=row["correlation_id"],
            )
        except (DatabaseUnavailableError, DatabaseLockedError):
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        except Exception as err:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self.last_error = str(err)
            raise PersistenceError(f"Failed to increment idempotency: {err}") from err
        finally:
            if conn:
                conn.close()

    # ==================================================================
    # HEALTH CHECK & DIAGNOSTICS
    # ==================================================================

    def health_check(self) -> Dict[str, Any]:
        """Perform diagnostic read probe and report store health."""
        start_t = time.perf_counter()
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM state_checkpoints;")
            count = cursor.fetchone()["cnt"]
            conn.close()
            latency_ms = (time.perf_counter() - start_t) * 1000.0

            return {
                "healthy": True,
                "backend": "sqlite",
                "database_exists": self.db_path.exists(),
                "total_checkpoints": count,
                "last_checkpoint_id": self.last_checkpoint_id,
                "last_checkpoint_sim_time": self.last_checkpoint_sim_time,
                "last_checkpoint_saved_at": self.last_checkpoint_saved_at,
                "probe_latency_ms": round(latency_ms, 2),
                "consecutive_errors": self.consecutive_errors,
                "error": None,
            }
        except Exception as err:
            latency_ms = (time.perf_counter() - start_t) * 1000.0
            return {
                "healthy": False,
                "backend": "sqlite",
                "database_exists": self.db_path.exists(),
                "total_checkpoints": 0,
                "last_checkpoint_id": self.last_checkpoint_id,
                "last_checkpoint_sim_time": self.last_checkpoint_sim_time,
                "last_checkpoint_saved_at": self.last_checkpoint_saved_at,
                "probe_latency_ms": round(latency_ms, 2),
                "consecutive_errors": self.consecutive_errors,
                "error": str(err),
            }

    def close(self) -> None:
        """Resource cleanup."""
        logger.info("Closing SQLiteStateStore.")
