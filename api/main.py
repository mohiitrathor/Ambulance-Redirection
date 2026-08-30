from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.config import FRONTEND_DIR
from api.dependencies import manager
from api.persistence.bridge import persistence_bridge
from api.routers import (
    dispatch,
    state,
    events,
    redirection,
    simulation,
    analytics,
)


# ==============================================================
# LIFESPAN
# ==============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: Initialize the Simulator singleton and historical persistence run.
    This loads all CSVs and populates the world state.

    Shutdown: Cleanly stop any running background real-time
    simulation thread, finalize the active run session as TERMINATED,
    and cleanly shut down the background persistence worker.
    """

    manager.initialize()
    yield
    manager.stop_realtime()
    if manager.active_run_id is not None:
        try:
            with manager.lock:
                final_time = manager.simulator.state.current_time if manager.simulator else 0
            persistence_bridge.finalize_run(
                manager.active_run_id,
                final_sim_time=final_time,
                status="TERMINATED",
            )
        except Exception:
            pass
    persistence_bridge.shutdown()


# ==============================================================
# APPLICATION
# ==============================================================

app = FastAPI(
    title="RAAH — Emergency Dispatch API",
    description=(
        "AI/ML-powered dynamic ambulance dispatch "
        "and hospital redirection system."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ==============================================================
# CORS
# ==============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================
# ROUTERS
# ==============================================================

app.include_router(
    dispatch.router,
    prefix="/dispatch",
    tags=["Dispatch"],
)

app.include_router(
    state.router,
    prefix="/state",
    tags=["State"],
)

app.include_router(
    events.router,
    prefix="/events",
    tags=["Events"],
)

app.include_router(
    redirection.router,
    prefix="/redirect",
    tags=["Redirection"],
)

app.include_router(
    simulation.router,
    prefix="/simulation",
    tags=["Simulation"],
)

app.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["Analytics"],
)


# ==============================================================
# HEALTH
# ==============================================================

@app.get(
    "/health",
    tags=["Health"],
    summary="Health check",
    description=(
        "Returns server status, current simulation time, "
        "and real-time mode status."
    ),
)
def health():

    return {
        "status": "ok",
        "time": manager.simulator.state.current_time,
        "realtime_running": manager.is_realtime_running,
    }


# ==============================================================
# DASHBOARD STATIC FILES
# ==============================================================

if FRONTEND_DIR.exists():
    app.mount(
        "/dashboard",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )

