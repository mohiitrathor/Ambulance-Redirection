from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies import manager
from api.routers import (
    dispatch,
    state,
    events,
    redirection,
    simulation,
)


# ==============================================================
# LIFESPAN
# ==============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: Initialize the Simulator singleton.
    This loads all CSVs and populates the world state.

    Shutdown: Cleanly stop any running background real-time
    simulation thread before process exit.
    """

    manager.initialize()
    yield
    manager.stop_realtime()


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
