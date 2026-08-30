import sys
import threading

from api.config import DISPATCH_DIR


# ==============================================================
# ENSURE DISPATCH MODULES ARE IMPORTABLE
#
# Same sys.path approach used by simulator.py and
# integration_test.py. No Dispatch/__init__.py needed.
# ==============================================================

if str(DISPATCH_DIR) not in sys.path:
    sys.path.insert(0, str(DISPATCH_DIR))

from simulator import Simulator


# ==============================================================
# SIMULATOR MANAGER
# ==============================================================

class SimulatorManager:
    """
    Thread-safe singleton wrapper around the Simulator.

    Owns exactly one Simulator instance and a threading.Lock.
    All API endpoints acquire the lock before touching state.
    """

    def __init__(self):

        self._simulator: Simulator | None = None
        self._lock = threading.Lock()

    # ----------------------------------------------------------
    # INITIALIZE
    # ----------------------------------------------------------

    def initialize(self):
        """
        Create the Simulator instance.
        Called once during FastAPI lifespan startup.
        """

        with self._lock:
            self._simulator = Simulator()

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
    # RESET
    # ----------------------------------------------------------

    def reset(self):
        """
        Tear down and recreate the Simulator
        with fresh world state.
        """

        with self._lock:
            self._simulator = Simulator()


# ==============================================================
# MODULE-LEVEL SINGLETON
# ==============================================================

manager = SimulatorManager()
