"""
RAAH SQLite Database Connection & Schema Management
===================================================

Manages the local SQLite database for historical simulation analytics.
Authoritative live operational state remains in process RAM (Simulator);
this layer maintains an indexed, queryable historical audit trail.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

from api.config import DATA_DIR

logger = logging.getLogger("raah.persistence.db")

DEFAULT_DB_PATH = DATA_DIR / "raah_history.db"

SCHEMA_SQL = """
-- 1. SIMULATION RUN SESSIONS
CREATE TABLE IF NOT EXISTS simulation_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    total_ticks INTEGER DEFAULT 0,
    final_sim_time INTEGER DEFAULT 0,
    notes TEXT
);

-- 2. INCIDENTS (Immutable triage records)
CREATE TABLE IF NOT EXISTS historical_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
    incident_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    condition TEXT NOT NULL,
    predicted_severity TEXT NOT NULL,
    priority INTEGER NOT NULL,
    ml_confidence REAL,
    patient_lat REAL NOT NULL,
    patient_lon REAL NOT NULL,
    dispatched_sim_time INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, incident_id)
);

-- 3. DISPATCH ASSIGNMENTS & OUTCOMES
CREATE TABLE IF NOT EXISTS historical_dispatches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
    incident_id INTEGER NOT NULL,
    ambulance_id TEXT NOT NULL,
    ambulance_type TEXT NOT NULL,
    initial_hospital_id TEXT NOT NULL,
    final_hospital_id TEXT NOT NULL,
    initial_eta_minutes REAL NOT NULL,
    final_eta_minutes REAL NOT NULL,
    route_distance_km REAL,
    traffic_level TEXT,
    road_condition TEXT,
    dispatched_sim_time INTEGER NOT NULL,
    arrived_sim_time INTEGER,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(run_id, incident_id)
);

-- 4. REDIRECTION DECISION AUDIT
CREATE TABLE IF NOT EXISTS historical_redirections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
    incident_id INTEGER NOT NULL,
    ambulance_id TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    original_hospital_id TEXT,
    new_hospital_id TEXT,
    eta_before REAL,
    eta_after REAL,
    eta_saved REAL,
    eta_improvement_pct REAL,
    reason TEXT NOT NULL,
    sim_time INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

-- 5. SIMULATION EVENTS LOG
CREATE TABLE IF NOT EXISTS historical_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    sim_time INTEGER NOT NULL,
    facility_or_unit_id TEXT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- OPTIMIZED QUERY INDEXES
CREATE INDEX IF NOT EXISTS idx_incidents_run ON historical_incidents(run_id);
CREATE INDEX IF NOT EXISTS idx_dispatches_run ON historical_dispatches(run_id, incident_id);
CREATE INDEX IF NOT EXISTS idx_redirections_run ON historical_redirections(run_id, incident_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON historical_events(run_id, sim_time);
"""


def get_db_path(custom_path: Optional[Path] = None) -> Path:
    """Return the resolved database path, ensuring parent directory exists."""
    path = custom_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection(custom_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Create a new connection to SQLite configured with WAL mode,
    foreign keys, and appropriate timeout.
    """
    path = get_db_path(custom_path)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row

    # Configure optimal SQLite PRAGMAs for high-concurrency read/write
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA temp_store = MEMORY;")

    return conn


def init_db(custom_path: Optional[Path] = None) -> Path:
    """
    Initialize SQLite database and execute schema creation.
    Safe to call multiple times (idempotent).
    """
    path = get_db_path(custom_path)
    logger.info("Initializing SQLite database at %s", path)

    conn = get_connection(path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()

    return path
