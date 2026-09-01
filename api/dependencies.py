import sys
import threading
from datetime import datetime, timezone

from api.config import DISPATCH_DIR


# ==============================================================
# ENSURE DISPATCH MODULES ARE IMPORTABLE
# ==============================================================

if str(DISPATCH_DIR) not in sys.path:
    sys.path.insert(0, str(DISPATCH_DIR))

from simulator import Simulator
from api.persistence.bridge import persistence_bridge


# ==============================================================
# SIMULATOR MANAGER
# ==============================================================

class SimulatorManager:
    """
    Thread-safe singleton manager for the RAAH Simulator.

    Guarantees:
      1. Exactly ONE authoritative Simulator instance and live state.
      2. Thread-safe execution between concurrent API requests and
         background real-time simulation ticks.
      3. Race-safe start, stop, and reset operations.
      4. Safe thread termination prior to state reconstruction.
      5. Coordinated historical persistence run lifecycle.
    """

    def __init__(self):

        self._simulator: Simulator | None = None
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()

        # Historical persistence run ID
        self._active_run_id: int | None = None

        # Real-time simulation state
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._status = "STOPPED"
        self._tick_interval_seconds: float = 1.0
        self._minutes_per_tick: int = 1
        self._ticks_processed: int = 0
        self._started_at: str | None = None
        self._last_error: str | None = None
        self._consecutive_errors: int = 0

    # ----------------------------------------------------------
    # INITIALIZE
    # ----------------------------------------------------------

    def initialize(self):
        """
        Create the Simulator instance and initialize historical run tracking.
        Called once during FastAPI lifespan startup.
        """

        with self._lock:
            if self._simulator is None:
                persistence_bridge.start()
                run_id = persistence_bridge.create_run(notes="Initial simulation session")
                self._active_run_id = run_id
                self._simulator = Simulator()
                self._simulator.persistence_bridge = persistence_bridge
                self._simulator.run_id = run_id

    # ----------------------------------------------------------
    # ACTIVE RUN ID ACCESS
    # ----------------------------------------------------------

    @property
    def active_run_id(self) -> int | None:

        with self._lock:
            return self._active_run_id

    # ----------------------------------------------------------
    # INITIALIZED STATUS
    # ----------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        with self._lock:
            return self._simulator is not None

    @property
    def status(self) -> str:
        with self._lifecycle_lock:
            return self._status

    def check_readiness(self) -> tuple[bool, dict]:
        checks = {}
        with self._lock:
            sim_init = self._simulator is not None
            checks["simulator_initialized"] = sim_init
            state_ok = False
            if sim_init:
                try:
                    state_ok = self._simulator.state is not None
                except Exception:
                    state_ok = False
            checks["simulator_state_available"] = state_ok

        db_ok = False
        try:
            from api.persistence.db import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            db_ok = True
            conn.close()
        except Exception:
            db_ok = False
        checks["database_reachable"] = db_ok

        with self._lifecycle_lock:
            sim_status_ok = self._status in ("RUNNING", "STOPPED") and self._consecutive_errors == 0
            checks["simulation_status_valid"] = sim_status_ok
            checks["simulation_status"] = self._status
            checks["consecutive_errors"] = self._consecutive_errors

        is_ready = all([sim_init, state_ok, db_ok, sim_status_ok])
        return is_ready, checks

    # ----------------------------------------------------------
    # SIMULATOR ACCESS
    # ----------------------------------------------------------

    @property
    def simulator(self) -> Simulator:

        if self._simulator is None:
            raise RuntimeError(
                "Simulator not initialized. "
                "Call manager.initialize() first."
            )

        return self._simulator

    # ----------------------------------------------------------
    # LOCK ACCESS
    # ----------------------------------------------------------

    @property
    def lock(self) -> threading.Lock:

        return self._lock

    # ----------------------------------------------------------
    # REAL-TIME RUNNING STATUS
    # ----------------------------------------------------------

    @property
    def is_realtime_running(self) -> bool:

        with self._lifecycle_lock:
            return (
                self._status == "RUNNING"
                and self._thread is not None
                and self._thread.is_alive()
            )

    # ----------------------------------------------------------
    # START REAL-TIME
    # ----------------------------------------------------------

    def start_realtime(
        self,
        tick_interval_seconds: float = 1.0,
        minutes_per_tick: int = 1,
    ) -> dict:
        """
        Start the background real-time simulation thread.
        Thread-safe and race-safe.
        """

        with self._lifecycle_lock:

            if (
                self._status == "RUNNING"
                and self._thread is not None
                and self._thread.is_alive()
            ):
                raise RuntimeError(
                    "Simulation is already running."
                )

            # Ensure any lingering dead thread handle is cleared
            if self._thread is not None and self._thread.is_alive():
                self._stop_event.set()
                self._thread.join(timeout=3.0)

            self._tick_interval_seconds = float(tick_interval_seconds)
            self._minutes_per_tick = int(minutes_per_tick)
            self._ticks_processed = 0
            self._consecutive_errors = 0
            self._last_error = None
            self._started_at = datetime.now(timezone.utc).isoformat()
            self._stop_event.clear()
            self._status = "RUNNING"

            self._thread = threading.Thread(
                target=self._run_loop,
                name="RealtimeSimulationThread",
                daemon=True,
            )
            self._thread.start()

            with self._lock:
                sim_time = self.simulator.state.current_time

            return {
                "status": "RUNNING",
                "message": "Real-time simulation started.",
                "time": sim_time,
            }

    # ----------------------------------------------------------
    # STOP REAL-TIME
    # ----------------------------------------------------------

    def stop_realtime(self) -> dict:
        """
        Stop the background real-time simulation thread.
        Signals the stop event and waits for termination.
        Idempotent and race-safe.
        """

        with self._lifecycle_lock:

            if (
                self._status == "STOPPED"
                and (self._thread is None or not self._thread.is_alive())
            ):
                with self._lock:
                    sim_time = self.simulator.state.current_time
                return {
                    "status": "STOPPED",
                    "message": "Simulation is already stopped.",
                    "time": sim_time,
                }

            self._stop_event.set()

            if self._thread is not None:
                self._thread.join(timeout=3.0)
                self._thread = None

            self._status = "STOPPED"

            with self._lock:
                sim_time = self.simulator.state.current_time

            return {
                "status": "STOPPED",
                "message": "Real-time simulation stopped.",
                "time": sim_time,
            }

    # ----------------------------------------------------------
    # REAL-TIME STATUS
    # ----------------------------------------------------------

    def get_realtime_status(self) -> dict:
        """
        Retrieve live telemetry of the real-time simulation loop.
        """

        with self._lifecycle_lock:

            is_running = (
                self._status == "RUNNING"
                and self._thread is not None
                and self._thread.is_alive()
            )

            # Detect if the worker died unexpectedly
            if self._status == "RUNNING" and not is_running:
                self._status = (
                    "STOPPED"
                    if self._last_error is None
                    else "ERRORED"
                )

            with self._lock:
                current_time = self.simulator.state.current_time

            speed_multiplier = round(
                (self._minutes_per_tick * 60.0)
                / max(self._tick_interval_seconds, 0.001),
                2,
            )

            return {
                "status": self._status,
                "is_running": is_running,
                "current_time": current_time,
                "tick_interval_seconds": self._tick_interval_seconds,
                "minutes_per_tick": self._minutes_per_tick,
                "speed_multiplier": speed_multiplier,
                "ticks_processed": self._ticks_processed,
                "started_at": self._started_at,
                "last_error": self._last_error,
            }

    # ----------------------------------------------------------
    # BACKGROUND WORKER LOOP
    # ----------------------------------------------------------

    def _run_loop(self):
        """
        Internal worker executed in a background daemon thread.
        Holds the lock ONLY during state advancement (~1ms),
        never while waiting.
        """

        while not self._stop_event.is_set():

            interrupted = self._stop_event.wait(
                timeout=self._tick_interval_seconds
            )

            if interrupted or self._stop_event.is_set():
                break

            try:

                with self._lock:
                    self._simulator.advance_time(self._minutes_per_tick)
                    self._simulator.process_events()
                    self._simulator.check_redirections()

                self._ticks_processed += 1
                self._consecutive_errors = 0

            except Exception as exc:

                self._consecutive_errors += 1
                self._last_error = f"{type(exc).__name__}: {exc}"

                if self._consecutive_errors >= 3:
                    with self._lifecycle_lock:
                        self._status = "ERRORED"
                    break

    # ----------------------------------------------------------
    # RESET
    # ----------------------------------------------------------

    def reset(self):
        """
        Tear down and recreate the Simulator with fresh state and fresh historical run.

        Guaranteed order:
          1. Stop background thread if active.
          2. Wait for background thread to terminate completely.
          3. Clear thread reference.
          4. Ensure persistence queue has processed all events belonging to old run.
          5. Finalize the current run using its final simulation time and status.
          6. Create fresh historical run session.
          7. Acquire simulator lock and re-instantiate Simulator with new run_id.
          8. Leave in STOPPED state at time = 0.
        """

        with self._lifecycle_lock:

            self._stop_event.set()

            if self._thread is not None:
                self._thread.join(timeout=3.0)
                self._thread = None

            self._status = "STOPPED"
            ticks = self._ticks_processed
            self._ticks_processed = 0
            self._last_error = None
            self._started_at = None

            # Get final simulation time and run ID from old simulation
            with self._lock:
                current_time = self._simulator.state.current_time if self._simulator else 0
                old_run_id = self._active_run_id

            # Flush persistence queue to ensure all events from old run are written
            persistence_bridge.flush(timeout=3.0)
            if old_run_id is not None:
                persistence_bridge.finalize_run(
                    old_run_id,
                    final_sim_time=current_time,
                    total_ticks=ticks,
                    status="COMPLETED",
                )

            # Create new historical run session in SQLite
            new_run_id = persistence_bridge.create_run(notes="Reset simulation session")

            with self._lock:
                self._active_run_id = new_run_id
                self._simulator = Simulator()
                self._simulator.persistence_bridge = persistence_bridge
                self._simulator.run_id = new_run_id


# ==============================================================
# MODULE-LEVEL SINGLETON
# ==============================================================

manager = SimulatorManager()
