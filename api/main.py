from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.config import FRONTEND_DIR
from api.settings import settings
from api.observability import setup_structured_logging, ObservabilityMiddleware
from api.dependencies import manager
from api.persistence.bridge import persistence_bridge
from api.routers import (
    dispatch,
    state,
    events,
    redirection,
    simulation,
    analytics,
    coordination,
    scenarios,
    drills,
    replay_analysis,
    post_incident,
    optimization,
)

# Initialize structured logging
setup_structured_logging(log_level=settings.log_level, log_format=settings.log_format)


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
    title=settings.app_name,
    description=(
        "AI/ML-powered dynamic ambulance dispatch "
        "and hospital redirection system."
    ),
    version=settings.app_version,
    lifespan=lifespan,
)


# ==============================================================
# MIDDLEWARE
# ==============================================================

# Request correlation ID & structured access logging
app.add_middleware(ObservabilityMiddleware)

# CORS Whitelist from centralized settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
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

app.include_router(
    coordination.router,
)

app.include_router(
    scenarios.router,
)

app.include_router(
    drills.router,
)

app.include_router(
    replay_analysis.router,
)

app.include_router(
    post_incident.router,
)

app.include_router(
    optimization.router,
)


# ==============================================================
# HEALTH
# ==============================================================

@app.get(
    "/health",
    tags=["Health"],
    summary="Health check (legacy backwards-compatible)",
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


@app.get(
    "/health/live",
    tags=["Health"],
    summary="Process liveness probe",
    description="Cheap probe confirming the API process is alive and accepting traffic.",
)
def health_live():
    return {
        "status": "ALIVE",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get(
    "/health/ready",
    tags=["Health"],
    summary="Application readiness probe",
    description="Deep probe checking simulator, database, and background engine readiness.",
)
def health_ready():
    is_ready, checks = manager.check_readiness()
    payload = {
        "status": "READY" if is_ready else "NOT_READY",
        "ready": is_ready,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    if not is_ready:
        return JSONResponse(status_code=503, content=payload)
    return payload


# ==============================================================
# DASHBOARD STATIC FILES
# ==============================================================

if FRONTEND_DIR.exists():
    app.mount(
        "/dashboard",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )

