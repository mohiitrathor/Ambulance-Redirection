# RAAH M12 Phase 1 — Production Architecture & Hardening Audit

**Document Version:** 1.0.0  
**Milestone:** M12 — Production Hardening & Operational Readiness  
**Target System:** RAAH Intelligent EMS Dispatch, Coordination & Autonomous Optimization Platform  
**Audit Date:** 2026-09-01  
**Auditor:** Antigravity Advanced Agentic AI Assistant  

---

## 1. Executive Summary

Over Milestones M1 through M11, the RAAH system has evolved from a machine-learning patient severity classifier into a comprehensive, state-of-the-art Emergency Medical Services (EMS) coordination and autonomous decision platform. Its capabilities now encompass:
- Clinical triage and priority prediction (M1)
- Real-time ambulance dispatch with hospital suitability matching (M2)
- Real-time simulation clock and live state convergence (M3–M5)
- Tactical operator controls and manual hospital redirection (M6)
- Asynchronous historical persistence via SQLite (M7)
- Dynamic vehicle kinematics, road multipliers, and routing engine (M8)
- Fleet coverage rebalancing, predictive hospital load balancing, and Multi-Casualty Incident (MCI) orchestration (M9)
- Deterministic scenario replay, disaster drills, and post-incident review (M10)
- Decision Intelligence, Operator Copilot, guarded semi-autonomous policy engine, confidence calibration, drift detection, and adaptive policy tuning (M11)

While RAAH’s algorithmic, clinical, and operational intelligence layers are exceptionally mature, the system currently exhibits the operational profile of a **high-fidelity prototype and simulation testbed** rather than a hardened, fault-tolerant production emergency system. Critical production deficits include:
1. **Volatile In-Memory Authoritative State:** If the process restarts or crashes, all active dispatches, en-route ambulances, and patient incidents are lost.
2. **Zero Authentication and Authorization:** The REST API is completely unauthenticated, exposing emergency dispatch, fleet movement, policy modes, and the emergency kill switch to unrestricted access.
3. **Hardcoded Configuration and Paths:** Key operational parameters, directory paths, and thresholds are hardcoded in source code without environment variable or external configuration support.
4. **Lack of Ingestion Adapters:** Vehicle kinematics and hospitals rely on synthetic datasets and simulation rather than standardized external interfaces (AVL/GPS, CAD incident feeds, HL7/FHIR hospital beds).
5. **Observability Gaps:** Observability relies on ad-hoc stdout printing and basic Python logging without structured JSON logging, distributed tracing, or Prometheus metrics.

This audit provides a comprehensive, objective evaluation of RAAH’s production readiness, assigns an overall score, categorizes technical risks (P0 to P3), and specifies a robust, phased architecture roadmap for Milestone 12.

---

## 2. Current Architecture Overview

```
                               ┌─────────────────────────────────────────────────────────────┐
                               │                    FRONTEND CLIENT                          │
                               │  (Tactical Command Center, Copilot, Drills, Replay UI)      │
                               └──────────────────────────────┬──────────────────────────────┘
                                                              │ HTTP / JSON REST API
                                                              ▼
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 FASTAPI APPLICATION LAYER                                  │
│   Routers: /dispatch, /state, /events, /simulation, /coordination, /drills, /optimization  │
│   Middleware: CORSMiddleware (allow_origins=["*"])                                          │
└──────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                               │
                        ┌──────────────────────┴──────────────────────┐
                        │ SimulatorManager Singleton (_lock)          │
                        └──────────────────────┬──────────────────────┘
                                               │
          ┌────────────────────────────────────┼────────────────────────────────────┐
          ▼                                    ▼                                    ▼
┌───────────────────────┐          ┌───────────────────────┐          ┌───────────────────────┐
│ AUTHORITATIVE LIVE    │          │ OPTIMIZATION & POLICY │          │ HISTORICAL            │
│ STATE & SIMULATOR     │          │ ENGINE (M11)          │          │ PERSISTENCE (M7)      │
├───────────────────────┤          ├───────────────────────┤          ├───────────────────────┤
│ • DispatchState (RAM) │◄─────────┤ • DecisionEngine      │          │ • PersistenceBridge   │
│ • Simulator Engine    │          │ • AdaptivePolicyEngine│          │   (Background Queue)  │
│ • RoutingEngine (M8)  │          │ • DriftDetector       │          │ • SQLite Database     │
│ • FleetCoordinator(M9)│          │ • OutcomeStore (JSON) │          │   (raah_history.db)   │
│ • HospitalBalancer(M9)│          │ • PolicyVersionStore  │          └───────────────────────┘
│ • MCIManager (M9)     │          │   (data/optimization/)│
└───────────────────────┘          └───────────────────────┘
          ▲
          │
┌───────────────────────┐
│ SCENARIO & REPLAY     │
│ WORKSTATION (M10)     │
├───────────────────────┤
│ • ScenarioRunner      │
│ • ReplayEngine (ISO)  │
│ • DrillResultStore    │
└───────────────────────┘
```

### Key Architectural Invariants
- **Sole Source of Truth:** `DispatchState` in `Dispatch/simulator.py` is the single authoritative live state.
- **Hierarchy of Control:** Decision intelligence and adaptive policy modules sit strictly *above* the simulator and execute state mutations only through authoritative simulator methods (`execute_reposition`, `apply_manual_redirection`, `cancel_reposition`).
- **Clinical Protection:** Clinical severity prediction via `Predict_Severity.py` is immutable and cannot be overridden by heuristic optimization or autonomous learning.

---

## 3. Production-Readiness Score: 58 / 100

| Domain | Weight | Score (0–100) | Weighted Score | Summary |
| :--- | :---: | :---: | :---: | :--- |
| **Algorithmic & Dispatch Core** | 20% | 95 | 19.0 | Exceptionally strong clinical ML, kinematics, balancing, and MCI coordination. |
| **Decision Intelligence & Safety** | 15% | 92 | 13.8 | 12 guardrails, confidence calibration, drift detection, kill switch, version rollback. |
| **Concurrency & Thread Safety** | 15% | 72 | 10.8 | SimulatorManager locks core state, but DecisionEngine in-memory indices have race gaps. |
| **Persistence & Disaster Recovery** | 15% | 38 | 5.7 | Live state is volatile RAM only; no crash recovery or write-ahead logging for live dispatches. |
| **Security, AuthN & AuthZ** | 15% | 18 | 2.7 | Zero authentication, zero RBAC, unrestricted kill-switch, permissive CORS. |
| **External Integration Readiness** | 10% | 32 | 3.2 | Hardcoded to local CSV datasets; no pluggable AVL, CAD, or FHIR interfaces. |
| **Observability & Operations** | 10% | 48 | 4.8 | Basic logging and health endpoints; no Prometheus metrics, tracing, or structured logs. |
| **TOTAL** | **100%** | — | **58.0** | **Prototype / Staging Grade — Requires Hardening for Production** |

---

## 4. Production Architecture Target (M12 Target Topology)

```
                              ┌───────────────────────────────┐
                              │     EXTERNAL EMS PROVIDERS    │
                              │  CAD / AVL GPS / FHIR Beds    │
                              └───────────────┬───────────────┘
                                              │ TLS / HMAC
                                              ▼
                              ┌───────────────────────────────┐
                              │  INGRESS & REVERSE PROXY      │
                              │  (Rate Limiting, TLS, CORS)   │
                              └───────────────┬───────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   FASTAPI APPLICATION CORE                                  │
│                                                                                             │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────────┐  │
│  │   AUTH & RBAC FILTER    │  │ CONFIG & SECRETS MGR    │  │  OBSERVABILITY (Prometheus  │  │
│  │ (Dispatcher/Supervisor/ │  │ (Env vars, Pydantic     │  │  Metrics, Structured JSON   │  │
│  │  Admin/Medical Control) │  │  BaseSettings)          │  │  Tracing, Liveness/Ready)   │  │
│  └────────────┬────────────┘  └────────────┬────────────┘  └──────────────┬──────────────┘  │
│               │                            │                              │                 │
│               ▼                            ▼                              ▼                 │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                       ADAPTER LAYER (M12 Interface Abstractions)                      │  │
│  │   • AmbulanceGPSAdapter        (MockKinematicsProvider / RealAVLProvider)             │  │
│  │   • HospitalCapacityAdapter    (MockDatasetProvider    / RealFHIRProvider)            │  │
│  │   • TrafficRoutingAdapter      (LocalApproxRouter      / RealOSRMProvider)            │  │
│  │   • EmergencyIntakeAdapter     (SimulationCaller       / RealCADWebhookProvider)      │  │
│  └─────────────────────────────────────────┬─────────────────────────────────────────────┘  │
│                                            │                                                │
│                                            ▼                                                │
│  ┌───────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                  AUTHORITATIVE SIMULATOR & COORDINATION CONTROLLER                    │  │
│  │               (Protected by StateLock & State Snapshot Journal)                       │  │
│  │                                                                                       │  │
│  │   DispatchState ◄────► StateJournal (WAL / Checkpointing to SQLite)                   │  │
│  │   DecisionEngine ◄───► AdaptivePolicyEngine (With Reentrant Lock)                     │  │
│  └───────────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. P0 Risks — Safety & Operational Blockers

Critical flaws that could lead to loss of life, complete data loss, unrecoverable system failure, or critical security compromise in an operational EMS environment.

### P0-1: Volatile In-Memory Authoritative State
- **Affected Component:** `Dispatch/simulator.py`, `Dispatch/state.py`, `api/dependencies.py`
- **Current Behavior:** Authoritative `DispatchState` lives exclusively in process RAM. On process termination, crash, or reboot, all active ambulance assignments, patient locations, en-route progress, and hospital commitments vanish.
- **Why It Matters:** In an active emergency deployment, a server restart causes active ambulances to become "lost" to the system, stranded patients to lose their assigned transports, and hospital bed reservations to disappear.
- **Severity:** **P0 (Critical Safety Blocker)**
- **Recommended Solution:** Implement a transactional state journal (WAL) or snapshot persistence layer that checkpoints `DispatchState` every tick or mutation into SQLite or Redis, enabling automated state hydration upon startup.
- **Addressed in M12:** Yes (M12 Phase 4).

### P0-2: Complete Absence of Authentication & Authorization
- **Affected Component:** `api/main.py`, `api/routers/*`
- **Current Behavior:** Every endpoint (including `/simulation/reset`, `/optimization/policy/kill-switch`, `/optimization/policy/mode`, and `/dispatch/live`) is exposed publicly with no token, session, or credential check.
- **Why It Matters:** Any network actor can trigger the emergency kill switch, shut down semi-autonomous dispatch, spoof critical triage calls, or reset the entire simulator during an active incident.
- **Severity:** **P0 (Critical Security Blocker)**
- **Recommended Solution:** Implement HTTP Bearer JWT authentication and Role-Based Access Control (RBAC) covering Dispatcher, Supervisor, Medical Controller, and Admin roles.
- **Addressed in M12:** Yes (M12 Phase 2).

### P0-3: Hardcoded Configuration & Source-Coupled Paths
- **Affected Component:** `api/config.py`, `Dispatch/optimization/*`, `Dispatch/coordination/*`
- **Current Behavior:** Paths (`/home/glitchedpotato/RAAH/data/...`), thresholds (0.95 confidence, 2-unit floor), and tick intervals are hardcoded as literals inside Python source files.
- **Why It Matters:** The application cannot run in a containerized environment (Docker/Kubernetes), CI runner, or cloud VM with different paths or ports without code changes. Secrets and environment-specific settings cannot be injected.
- **Severity:** **P0 (Production Deployment Blocker)**
- **Recommended Solution:** Create a unified `api/settings.py` powered by `pydantic-settings` reading from `.env` and environment variables with sensible production defaults.
- **Addressed in M12:** Yes (M12 Phase 1 & 2).

### P0-4: Silent Simulation Thread Crash Without Self-Healing or Alerting
- **Affected Component:** `api/dependencies.py` (`SimulatorManager._run_loop`)
- **Current Behavior:** If the background real-time simulation thread encounters 3 consecutive uncaught exceptions, it sets `self._status = "ERRORED"` and silently breaks out of the execution loop.
- **Why It Matters:** The clock stops ticking, vehicle kinematics freeze, and ETA tracking halts indefinitely without notifying operators or triggering automated restart.
- **Severity:** **P0 (Operational Blocker)**
- **Recommended Solution:** Add thread-level supervisor supervision, automated exponential backoff restart, deadman's alerting, and liveness probe degradation when the loop halts.
- **Addressed in M12:** Yes (M12 Phase 5).

### P0-5: Unbounded In-Memory Persistence Queue
- **Affected Component:** `api/persistence/bridge.py` (`PersistenceBridge`)
- **Current Behavior:** `self._queue = queue.Queue()` has no maximum capacity (`maxsize=0`). If SQLite locks or disk writes lag, payloads accumulate in RAM indefinitely.
- **Why It Matters:** Heavy operational surges or disk I/O stalls cause unbounded memory growth leading to process OOM (Out Of Memory) kill, permanently losing all pending events in the queue.
- **Severity:** **P0 (Data Integrity Blocker)**
- **Recommended Solution:** Enforce bounded queue capacity (`maxsize=10000`), backpressure handling, disk spillover, and persistent queueing.
- **Addressed in M12:** Yes (M12 Phase 4).

---

## 6. P1 Risks — Production Blockers

Issues that severely degrade operational stability, lead to subtle state corruption under concurrency, or block production compliance.

### P1-1: Unsynchronized `DecisionEngine` Memory Index Access
- **Affected Component:** `Dispatch/optimization/decision_engine.py` (`_recommendations_index`, `_candidates_index`)
- **Current Behavior:** In `api/routers/optimization.py`, endpoints like `get_recommendation()` and `get_copilot_summary()` access `decision_engine._recommendations_index` outside `manager.lock` or without an internal mutex.
- **Why It Matters:** Concurrent reads and writes during background evaluation cause Python `RuntimeError: dictionary changed size during iteration` or return inconsistent recommendation states to dispatchers.
- **Severity:** **P1**
- **Recommended Solution:** Introduce a reentrant `threading.RLock()` dedicated to `DecisionEngine` index manipulation.
- **Addressed in M12:** Yes (M12 Phase 1).

### P1-2: CAD Emergency Call Ingestion Lacks Deduplication & Idempotency
- **Affected Component:** `api/routers/dispatch.py` (`/dispatch/live`)
- **Current Behavior:** Every `POST /dispatch/live` call creates a brand new incident ID, even if payload attributes (location, patient phone, caller ID, description) match an active emergency.
- **Why It Matters:** Multiple bystanders calling 911/112 for the same high-speed traffic accident cause multiple separate ambulances to be dispatched to the same casualty, starving other zones.
- **Severity:** **P1**
- **Recommended Solution:** Implement an incident deduplication window (clustering calls by coordinates $\pm 100\text{m}$ within a 15-minute sliding window) and require an `Idempotency-Key` HTTP header.
- **Addressed in M12:** Yes (M12 Phase 3).

### P1-3: Uncoordinated Loose JSON Stores for Critical Optimization & Scenarios
- **Affected Component:** `Dispatch/optimization/audit.py`, `Dispatch/optimization/learning.py`, `Dispatch/scenarios/runner.py`
- **Current Behavior:** Audit trails, drill results, replay files, and outcomes are saved as individual JSON files across `data/optimization/` and `data/drills/`.
- **Why It Matters:** File operations are susceptible to filesystem corruption, concurrent file access collisions, and lack relational indexing for fast querying over time.
- **Severity:** **P1**
- **Recommended Solution:** Migrate critical audit records and scenario metadata into SQLite tables while keeping large scenario replay streams as structured binary or gzipped JSON blobs with checksums.
- **Addressed in M12:** Yes (M12 Phase 4).

### P1-4: Permissive Insecure CORS Configuration
- **Affected Component:** `api/main.py`
- **Current Behavior:** `CORSMiddleware` specifies `allow_origins=["*"]`, `allow_credentials=True`.
- **Why It Matters:** Allows malicious third-party websites visited by an operator in the same browser to forge authenticated requests against the emergency API (Cross-Origin Request Forgery).
- **Severity:** **P1**
- **Recommended Solution:** Restrict allowed CORS origins to explicit trusted internal domains configurable via environment variables.
- **Addressed in M12:** Yes (M12 Phase 2).

### P1-5: Missing Kubernetes / Container Liveness & Readiness Probes
- **Affected Component:** `api/routers/*`, `api/main.py`
- **Current Behavior:** Only `/health` exists; it performs a static check without verifying whether the database is writable or whether the background simulation loop is alive.
- **Why It Matters:** Container orchestrators cannot detect deadlocked background workers or unmounted storage, failing to restart zombie containers.
- **Severity:** **P1**
- **Recommended Solution:** Expose `/health/live` (process alive) and `/health/ready` (DB writable, state initialized, kinematics running).
- **Addressed in M12:** Yes (M12 Phase 1 & 5).

### P1-6: Frontend HTTP Polling Storm
- **Affected Component:** `frontend/js/components/*`, `frontend/js/app.js`
- **Current Behavior:** The frontend issues 4–6 distinct HTTP GET requests every 1000–2000 ms per open browser tab to refresh dashboard, events, copilot, and telemetry.
- **Why It Matters:** Multiple dispatchers on the network create hundreds of requests per minute, unnecessarily consuming CPU and locking `SimulatorManager` repeatedly.
- **Severity:** **P1**
- **Recommended Solution:** Implement Server-Sent Events (SSE) or a lightweight WebSocket feed (`/ws/live-feed`) to push state delta events.
- **Addressed in M12:** Yes (M12 Phase 5).

---

## 7. P2 Risks — Important Hardening

### P2-1: Unstructured Print & Ad-Hoc Logging
- **Affected Component:** `Dispatch/simulator.py`, `Dispatch/dispatch_engine.py`, `api/routers/*`
- **Current Behavior:** Core dispatch and kinematics use standard `print()` statements alongside scattered `logging.getLogger` calls.
- **Why It Matters:** Impossible to ingest into centralized log aggregation systems (Elasticsearch, Loki, CloudWatch) or filter by severity, incident ID, or correlation ID.
- **Recommended Solution:** Implement a centralized structured JSON logging handler with correlation IDs (`request_id`, `incident_id`).
- **Addressed in M12:** Yes (M12 Phase 1).

### P2-2: Missing Metrics & Telemetry Exporter
- **Affected Component:** Entire backend
- **Current Behavior:** Latencies and counts are printed or returned in HTTP payloads; no Prometheus `/metrics` endpoint exists.
- **Why It Matters:** Operations teams cannot set up Prometheus/Grafana dashboards or automated alertmanager triggers for elevated ETAs or high harmful action rates.
- **Recommended Solution:** Integrate `prometheus-fastapi-instrumentator` exposing standard metrics (`raah_dispatch_duration_seconds`, `raah_active_incidents`, `raah_ambulance_count`).
- **Addressed in M12:** Yes (M12 Phase 5).

### P2-3: SQLite Single-Writer Lock Contention Under Heavy Reporting
- **Affected Component:** `api/persistence/db.py`
- **Current Behavior:** Single SQLite database file with default timeout (5.0s) and standard journaling.
- **Why It Matters:** Heavy analytical queries or drill exports can lock the database and delay background write flushes.
- **Recommended Solution:** Enable SQLite WAL mode (`PRAGMA journal_mode=WAL;`), configure `busy_timeout=10000`, and separate analytical read connections from persistence write connections.
- **Addressed in M12:** Yes (M12 Phase 4).

### P2-4: Absence of Pluggable External Adapter Interfaces
- **Affected Component:** `Dispatch/routing_engine.py`, `Dispatch/coordination/*`
- **Current Behavior:** Kinematics and hospital capacities are deeply tied to local memory objects without interface abstractions.
- **Why It Matters:** Integrating real AVL GPS feeds or real hospital bed management systems would require invasive refactoring of core code.
- **Recommended Solution:** Implement Provider Interface Adapters (Strategy pattern) with clean separation between simulated providers and live hardware/API providers.
- **Addressed in M12:** Yes (M12 Phase 3).

### P2-5: Frontend Asset Resiliency
- **Affected Component:** `frontend/index.html`
- **Current Behavior:** Loads Lucide icons and fonts from external unpinned CDN URLs (`unpkg.com/lucide`).
- **Why It Matters:** Air-gapped or restricted emergency dispatch networks will fail to load UI icons if public internet access is disabled.
- **Recommended Solution:** Bundle all vendor CSS/JS assets locally within `frontend/vendor/`.
- **Addressed in M12:** Yes (M12 Phase 5).

---

## 8. P3 Risks — Polish & Architectural Hygiene

### P3-1: Lack of Database Schema Migration Versioning
- **Affected Component:** `api/persistence/db.py`
- **Current Behavior:** Database tables are created using static `CREATE TABLE IF NOT EXISTS` strings in Python.
- **Recommended Solution:** Introduce lightweight schema version tracking table (`schema_version`) or Alembic migrations.
- **Addressed in M12:** Yes (M12 Phase 4).

### P3-2: Inconsistent Error Response Schemas
- **Affected Component:** `api/routers/*`
- **Current Behavior:** Some endpoints return `{"detail": "..."}`, others return `{"error": "...", "status": "FAILED"}`.
- **Recommended Solution:** Standardize error envelopes using a unified `ErrorResponse` Pydantic model and global exception handlers.
- **Addressed in M12:** Yes (M12 Phase 1).

### P3-3: Missing Automated Performance Benchmark in CI
- **Affected Component:** `benchmark_dispatch.py`
- **Current Behavior:** Dispatch latency benchmark is run manually from terminal.
- **Recommended Solution:** Add automated assertion in CI that dispatch latency mean must remain $< 30$ ms.
- **Addressed in M12:** Yes (M12 Phase 6).

---

## 9. Persistence and Recovery Assessment

### 9.1 Current State Analysis
| Data Category | Storage Medium | Survives Restart? | Recovery Mechanism |
| :--- | :--- | :---: | :--- |
| **Active Ambulances & Kinematics** | Process RAM (`Simulator.state`) | **NO** | Re-instantiated from `Dataset/ambulances.csv` at `time=0` |
| **Active Dispatches & En-Route Status** | Process RAM (`Simulator.state`) | **NO** | Completely lost |
| **Active Emergency Incidents** | Process RAM (`Simulator.state`) | **NO** | Completely lost |
| **Hospital Dynamic Bed Occupancy** | Process RAM (`Simulator.state`) | **NO** | Reset to static `Dataset/hospitals.csv` baseline |
| **Active MCI Declarations** | Process RAM (`MCIManager`) | **NO** | Completely lost |
| **Active Optimization Recommendations**| Process RAM (`DecisionEngine`) | **NO** | Re-evaluated on demand |
| **Historical Dispatches & Runs** | SQLite (`raah_history.db`) | **YES** | Preserved in database |
| **Execution Audit Trail** | Atomic JSON (`data/optimization/`) | **YES** | Loaded on demand from disk |
| **Policy Configuration Versions** | Atomic JSON (`data/optimization/`) | **YES** | Loaded from `v{N}.json` |
| **Scenario & Drill Results** | Atomic JSON (`data/drills/`) | **YES** | Preserved on disk |

### 9.2 What Must Survive Restart in Production
In a live production deployment, the following state **must survive any process crash, reboot, or container rescheduling**:
1. Every active emergency incident, patient vitals, triage priority, and caller details.
2. Every dispatched ambulance, its current assigned destination (hospital or scene), route progress, and passenger status.
3. Every hospital bed reservation and diverted transport.
4. Active MCI status, declared casualties, and scene triage assignments.
5. Active policy mode (`OFF`, `ADVISORY`, `GUARDED`), active kill switch state, and operating policy version.

### 9.3 Recommended Persistence & Recovery Architecture
```
  OPERATIONAL MUTATION (Dispatch / Redirection / Kinematics Tick)
                         │
                         ▼
        ┌───────────────────────────────────┐
        │       DispatchState (RAM)         │
        └─────────────────┬─────────────────┘
                          │
             Synchronous State Journaling
             (Write-Ahead Log / SQLite Snapshot)
                          │
                          ▼
        ┌───────────────────────────────────┐
        │  SQLite: live_state_snapshots     │
        │  • snapshot_tick                  │
        │  • state_payload (Zlib JSON/Blob) │
        │  • sha256_hash                    │
        │  • timestamp                      │
        └───────────────────────────────────┘
```

- **Checkpoint Frequency:** Write a compact state snapshot every 10 simulation ticks (or every major operational event: dispatch, arrival, redirection, MCI declaration).
- **Crash Recovery Sequence:**
  1. On `manager.initialize()`, query `SELECT state_payload FROM live_state_snapshots ORDER BY snapshot_tick DESC LIMIT 1`.
  2. If a valid checkpoint exists and is within a configurable validity window (e.g. $< 30$ minutes old), hydrate `DispatchState` directly from the checkpoint instead of reloading CSVs.
  3. Re-verify ambulance connectivity and log an `OPERATIONAL_RESTART_RECOVERED` event.
  4. If no checkpoint exists or operator flags `--fresh-start`, fall back to clean baseline initialization.

---

## 10. Authentication and Authorization Architecture

### 10.1 Role-Based Access Control (RBAC) Matrix
A hardened emergency dispatch platform requires strict separation of privilege across 4 distinct operational roles:

| Operational Permission / Action | Dispatcher | Supervisor | Medical Controller | Administrator |
| :--- | :---: | :---: | :---: | :---: |
| View live dashboard, map, and telemetry | ✓ | ✓ | ✓ | ✓ |
| Ingest new emergency call (`POST /dispatch/live`) | ✓ | ✓ | ✓ | ✓ |
| Execute standard ambulance dispatch | ✓ | ✓ | ✓ | ✓ |
| Approve Copilot Fleet Reposition recommendation | ✓ | ✓ | — | ✓ |
| Approve Hospital Diversion recommendation | — | ✓ | ✓ | ✓ |
| Execute manual ambulance reroute | ✓ | ✓ | ✓ | ✓ |
| Declare or close Multi-Casualty Incident (MCI) | — | ✓ | ✓ | ✓ |
| Change Policy Mode (`OFF` / `ADVISORY` / `GUARDED`) | — | ✓ | — | ✓ |
| Trigger or Release Emergency Kill-Switch | — | ✓ | ✓ | ✓ |
| Approve Adaptive Policy Parameter Change (`v{N}`) | — | ✓ | — | ✓ |
| Rollback Policy Version | — | ✓ | — | ✓ |
| Run Disaster Drills & Stress Tests | — | ✓ | — | ✓ |
| User Provisioning & System Configuration | — | — | — | ✓ |
| Reset Live Simulation State | — | — | — | ✓ |

### 10.2 Technical Implementation Strategy
- **Authentication Scheme:** HTTP Bearer token utilizing standard JWT (JSON Web Tokens) signed via HMAC-SHA256 (`HS256`) or asymmetric `RS256`.
- **FastAPI Security Dependency:**
  ```python
  from fastapi.security import HTTPBearer, SecurityScopes
  # Usage on endpoint:
  # @router.post("/policy/kill-switch", dependencies=[Security(require_role, scopes=["Supervisor", "Administrator"])])
  ```
- **Audit Attribution:** Every execution record, redirection decision, and policy approval automatically binds the operator's authenticated `username` and `role` extracted directly from the verified token.

---

## 11. External Integration Architecture (Adapter Interfaces)

To allow the existing simulation and testing harness to operate alongside real-world municipal emergency systems, RAAH must adopt the **Provider Interface Pattern** (Dependency Inversion).

```
┌─────────────────────────────────────────────────────────────┐
│                    PROVIDER INTERFACES                      │
└───────┬──────────────┬──────────────┬──────────────┬────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
 ┌─────────────┐┌─────────────┐┌─────────────┐┌─────────────┐
 │  Ambulance  ││  Hospital   ││   Traffic   ││  Emergency  │
 │     GPS     ││  Capacity   ││   Routing   ││   Intake    │
 │   Adapter   ││   Adapter   ││   Adapter   ││   Adapter   │
 └──────┬──────┘└──────┬──────┘└──────┬──────┘└──────┬──────┘
        │              │              │              │
   ┌────┴────┐    ┌────┴────┐    ┌────┴────┐    ┌────┴────┐
   │         │    │         │    │         │    │         │
   ▼         ▼    ▼         ▼    ▼         ▼    ▼         ▼
[Simulated] [AVL] [Simulated] [FHIR] [Simulated] [OSRM] [Simulated] [CAD]
 Kinematics MQTT   CSV Beds   HL7-v2 LocalApprox WebAPI  Dataset   Webhook
```

### 11.1 Ambulance GPS / AVL Adapter Interface
```python
class AmbulanceLocationUpdate(NamedTuple):
    ambulance_id: str
    latitude: float
    longitude: float
    speed_kmh: float
    heading_deg: float
    timestamp: datetime

class IAmbulanceGPSProvider(ABC):
    @abstractmethod
    def get_location(self, ambulance_id: str) -> Optional[AmbulanceLocationUpdate]: ...
    @abstractmethod
    def get_all_locations(self) -> Dict[str, AmbulanceLocationUpdate]: ...
```
- **Simulated Provider:** Reads kinematics from `LocalApproxRouter`.
- **Production Provider:** Subscribes to municipal AVL GPS telemetry over MQTT, WebSockets, or HTTP push.

### 11.2 Hospital Capacity & Bed Feed Adapter Interface
```python
class HospitalCapacityUpdate(NamedTuple):
    hospital_id: str
    available_general_beds: int
    available_icu_beds: int
    is_diverting: bool
    status: str
    updated_at: datetime

class IHospitalCapacityProvider(ABC):
    @abstractmethod
    def fetch_capacities(self) -> Dict[str, HospitalCapacityUpdate]: ...
```
- **Simulated Provider:** Reads from `HospitalBalancer` dynamic counts.
- **Production Provider:** Ingests HL7 v2 / FHIR `Encounter` and `BedManagement` API updates every 60 seconds with offline circuit breaker fallback.

### 11.3 Traffic & Dynamic Routing Adapter Interface
```python
class RouteResult(NamedTuple):
    distance_km: float
    duration_minutes: float
    waypoints: List[Tuple[float, float]]
    traffic_delay_minutes: float

class ITrafficRoutingProvider(ABC):
    @abstractmethod
    def calculate_route(self, origin: Tuple[float, float], dest: Tuple[float, float]) -> RouteResult: ...
```
- **Simulated Provider:** `LocalApproxRouter` (M8 kinematics).
- **Production Provider:** OSRM (Open Source Routing Machine) or TomTom/Google Traffic API with fallback to `LocalApproxRouter` upon network timeout ($> 300\text{ ms}$).

### 11.4 Emergency Incident CAD Intake Adapter Interface
```python
class IncidentCallPayload(NamedTuple):
    idempotency_key: str
    caller_phone: str
    patient_condition: str
    latitude: float
    longitude: float
    age: int
    vitals: Dict[str, Any]

class IEmergencyIntakeProvider(ABC):
    @abstractmethod
    def validate_and_deduplicate(self, payload: IncidentCallPayload) -> Tuple[bool, Optional[str]]: ...
```
- **Simulated Provider:** `/dispatch/live` direct intake.
- **Production Provider:** CAD (Computer Aided Dispatch) webhook receiver with coordinate spatial clustering deduplication.

---

## 12. Observability Architecture

### 12.1 Structured Logging Standards
All console and file outputs must conform to structured JSON schema:
```json
{
  "timestamp": "2026-09-01T22:04:12.104Z",
  "level": "INFO",
  "logger": "raah.dispatch.engine",
  "trace_id": "c1f098a8-6b21-4f93-b8e1-92e105e19201",
  "message": "Ambulance dispatched to critical emergency",
  "incident_id": 100001,
  "ambulance_id": "AMB_0484",
  "hospital_id": "HOSP_117",
  "priority": "P1",
  "eta_minutes": 2.06,
  "ml_confidence": 0.9965,
  "duration_ms": 22.4
}
```

### 12.2 Prometheus Metrics Instrumentation (`/metrics`)
Key operational metrics to expose:
- `raah_dispatch_requests_total{status, priority}` (Counter)
- `raah_dispatch_duration_seconds` (Histogram with buckets: `[0.005, 0.010, 0.025, 0.050, 0.100]`)
- `raah_active_ambulances{status}` (Gauge: `AVAILABLE`, `BUSY`, `REPOSITIONING`, `MAINTENANCE`)
- `raah_hospital_occupancy_ratio{hospital_id}` (Gauge)
- `raah_optimization_policy_actions_total{mode, decision, type}` (Counter)
- `raah_operational_drift_score` (Gauge: 0–100)
- `raah_learning_safety_score` (Gauge: 0–100)
- `raah_kill_switch_active` (Gauge: 0 or 1)

### 12.3 Health & Readiness Probes
- `GET /health/live`: Fast process health check ($< 1\text{ ms}$). Verifies HTTP server is responsive.
- `GET /health/ready`: Deep dependency readiness check ($< 10\text{ ms}$). Verifies:
  1. `SimulatorManager` initialized.
  2. Background simulation thread is active (`status == "RUNNING"` or `"STOPPED"`).
  3. SQLite persistence database is reachable and writable.
  4. Clinical ML pipeline is loaded in memory.

---

## 13. Failure and Recovery Architecture

| Failure Mode | Detection Mechanism | Operational Impact | Automated Remediation |
| :--- | :--- | :--- | :--- |
| **SQLite Database Lock / Failure** | `sqlite3.OperationalError` caught in `PersistenceBridge` | Historical persistence blocked; live dispatches unaffected | Enqueue in bounded in-memory buffer, apply exponential retry with jitter, alert on queue depth $> 5000$. |
| **GPS / AVL Feed Interruption** | No location updates received for $> 30\text{ s}$ | Ambulance positions become stale | Fall back immediately to `LocalApproxRouter` dead reckoning kinematics based on last known velocity and heading. |
| **Hospital Capacity Feed Stale/Down** | Health probe on FHIR feed times out | Hospital bed availability unknown | Freeze capacity updates to last valid state, apply conservative $+10\%$ buffer to occupancy, flag hospital status as `UNVERIFIED`. |
| **External Routing API Failure** | HTTP 500 or timeout $> 300\text{ ms}$ | High-fidelity route waypoints unavailable | Instant fallback to internal `LocalApproxRouter` spherical haversine calculation with static speed matrices. |
| **Duplicate Emergency Incidents** | Spatial-temporal hashing matches active incident within $100\text{m}$ / $15\text{m}$ | Redundant ambulance dispatch | Tag second call as `DUPLICATE_CALL`, attach new caller notes to parent incident, do NOT dispatch secondary unit. |
| **Stale Optimization Recommendation** | Hash mismatch in `_validate_constraints()` | Outdated operational action | Reject execution, mark recommendation `OBSOLETE`, trigger fresh state evaluation. |
| **Concurrent Operator Action Race** | State lock contention in `executor.py` | Potential double-assignment | First operator request acquires lock and executes; second receives HTTP 409 Conflict with explanation. |
| **Process Crash / Hard Reboot** | Container exit / OS reboot | Complete loss of RAM state | Recovery manager detects dirty shutdown, hydrates `DispatchState` from most recent SQLite snapshot journal. |
| **Corrupted Policy / Scenario File** | `json.JSONDecodeError` on store load | Malformed config blocks engine | Version store rejects corrupt file, falls back to `v{N-1}` parent version, and emits critical alert. |

---

## 14. Security Architecture

1. **Authentication:** All administrative, operator, and dispatch mutation endpoints require an `Authorization: Bearer <token>` header.
2. **Secrets Hygiene:** No credentials, API tokens, or encryption keys in source code. All secrets loaded through `RAAH_JWT_SECRET_KEY`, `RAAH_DATABASE_URL`, and `RAAH_API_KEY` environment variables.
3. **Audit Immutability:** All audit logs (`ExecutionAuditStore`, `OutcomeStore`, `PolicyVersionStore`) generate deterministic SHA-256 signatures over their contents upon persistence, preventing manual tampering with event history.
4. **Rate Limiting:** Protect `/dispatch/live` and `/optimization/simulate` using an in-memory token bucket rate limiter (e.g. max 100 requests/minute per client IP) to mitigate Denial-of-Service attacks.
5. **CORS Hardening:** Replace `allow_origins=["*"]` with an environment-driven whitelist: `RAAH_CORS_ALLOWED_ORIGINS="https://dispatch.ems.raah.internal,https://supervisor.ems.raah.internal"`.

---

## 15. Comprehensive Testing Strategy

To elevate test coverage from unit/milestone validation to production reliability, M12 will introduce dedicated test harnesses:

1. **Failure Injection & Chaos Testing (`test_failure_injection.py`):**
   - Inject simulated SQLite disk write locks during high-throughput dispatch.
   - Inject simulated corrupt JSON syntax into policy version files.
   - Inject network timeouts during routing and hospital capacity checks.
2. **State Crash & Hydration Recovery (`test_crash_recovery.py`):**
   - Populate live simulation with 20 active en-route ambulances and 10 queued incidents.
   - Forcibly kill process state (`sim = None`), trigger hydration from snapshot journal, and verify 100% state parity.
3. **Concurrent Multi-Operator Race Stress (`test_concurrency_stress.py`):**
   - 50 concurrent threads attempting simultaneous manual redirection, fleet reposition approval, and kill-switch toggling to verify zero deadlocks and zero double-executions.
4. **Security & RBAC Enforcement (`test_security_rbac.py`):**
   - Verify unauthenticated requests receive 401 Unauthorized.
   - Verify Dispatchers attempting to switch Policy Mode or trigger Kill-Switch receive 403 Forbidden.
   - Verify CORS preflight rejects unauthorized origins.
5. **External Adapter Interface Contract (`test_external_adapters.py`):**
   - Verify seamless swapping between Mock/Simulated providers and Live provider stubs without altering core dispatch behavior.

---

## 16. Proposed Milestone 12 Phased Roadmap

We propose structuring Milestone 12 into **6 logical, incremental, non-breaking phases**:

```
M12 Phase 1: Production Architecture Audit & Hardening Foundation (THIS PHASE)
   └── Complete architectural audit, define schemas, establish risk register and baseline

M12 Phase 2: Configuration, Environment & Structured Observability
   └── Pydantic Settings, environment variable loading, structured JSON logging, Prometheus /metrics, /health/ready

M12 Phase 3: Security, Authentication & Role-Based Access Control (RBAC)
   └── JWT Bearer authentication, 4 operational roles, secure CORS, endpoint permission gating

M12 Phase 4: State Persistence, Crash Recovery & Resilient Storage
   └── Live state journaling (WAL snapshots), crash hydration, bounded persistence queue, SQLite WAL mode

M12 Phase 5: External Data Adapters & Real-Time Ingestion
   └── Provider interfaces for GPS/AVL, CAD intake deduplication, hospital capacity feeds, and routing fallback

M12 Phase 6: Failure Engineering, Production Deployment & End-to-End Acceptance
   └── Failure-injection test suite, load testing, Docker/systemd packaging, zero-downtime operational verification
```

---

## 17. Explicit File Modification Plan

### SAFE TO MODIFY (Additions and wrappers around existing architecture)
- `api/main.py`: Add middleware, new health routes, auth dependencies.
- `api/config.py`: Migrate to `pydantic-settings` with environment variable overrides.
- `api/dependencies.py`: Add health checks, thread supervisor recovery, and state hydration hooks.
- `api/routers/*`: Attach authentication dependencies and RBAC permissions.
- `api/schemas/*`: Add auth, metrics, and health response models.
- `api/persistence/db.py`: Add WAL mode, state snapshot journal table, and connection optimizations.
- `api/persistence/bridge.py`: Add bounded queue capacity and backpressure monitoring.
- `Dispatch/optimization/decision_engine.py`: Add thread-safe reentrant lock (`threading.RLock`) for index access.
- `frontend/js/api.js`: Add auth header injection and new health endpoints.
- `frontend/js/components/*`: Render operator role and connection health indicators.

### REQUIRES CARE (Must maintain exact backwards compatibility and latency budgets)
- `Dispatch/simulator.py`: Add snapshot export/import methods for crash recovery without modifying simulation rules.
- `Dispatch/routing_engine.py`: Wrap routing calls in adapter interface without changing `LocalApproxRouter` math.
- `Dispatch/coordination/fleet_coordinator.py`: Preserve all M9 coordination contracts.
- `Dispatch/optimization/policy_engine.py`: Preserve all 12 guardrails and confidence thresholds.

### DO NOT MODIFY (Protected Core Architecture)
- `Models/Final Model/*` (Protected clinical ML model and preprocessing)
- `Dataset/*` (Authoritative baseline CSV datasets)
- `Dispatch/dispatch_engine.py` (Authoritative dispatch algorithm)
- `Dispatch/events.py` (Core event structures)
- `Dispatch/decision_logger.py` (Core redirection logger)
- `Dispatch/redirection_engine.py` (Authoritative hospital redirection evaluation)
- `Dispatch/state.py` (Authoritative dataclasses: `AmbulanceState`, `IncidentState`, `DispatchState`)
- `test_m1*.py` through `test_m11_phase4.py` (All existing milestone test suites)

---

## 18. Phase 1 Implementation Plan (Next Immediate Step)

Once user approval is granted to proceed beyond the audit:

### Objective
Implement **M12 Phase 1 Hardening Foundation**:
1. Create `api/settings.py` (Pydantic Settings reading from `.env` and environment variables with full production defaults for paths, ports, timeouts, thresholds, and CORS).
2. Create `api/observability/` package with structured JSON logging and request correlation ID middleware.
3. Implement `/health/live` and `/health/ready` endpoints in `api/main.py`.
4. Add reentrant thread safety lock to `DecisionEngine._recommendations_index`.
5. Create `test_m12_phase1.py` covering settings injection, health probes, structured logging, and thread safety.
6. Verify all existing M1–M11 regression suites pass with 100% fidelity.

### Acceptance Criteria & Safety Invariants
- Core dispatch latency mean remains $\le 25\text{ ms}$.
- Zero modifications to protected core files.
- Zero changes to clinical severity prediction or P1/P2 dispatch logic.
- Complete backwards compatibility with existing frontend and test suites.

---

**AUDIT CONCLUSION: RAAH architecture is functionally robust and algorithmically exceptional. Implementing the M12 Hardening Roadmap will convert it into a resilient, secure, and production-grade municipal emergency coordination system.**
