from fastapi import APIRouter, HTTPException

from api.dependencies import manager
from api.schemas.dispatch import DispatchResult


# ==============================================================
# ROUTER
# ==============================================================

router = APIRouter()


# ==============================================================
# POST /dispatch/{incident_id}
# ==============================================================

@router.post(
    "/{incident_id}",
    response_model=DispatchResult,
    summary="Dispatch an incident",
    description=(
        "Run the full dispatch pipeline for an incident: "
        "ML severity prediction, ambulance selection, "
        "hospital selection, and state mutation."
    ),
)
def dispatch_incident(incident_id: int):

    sim = manager.simulator
    lock = manager.lock

    with lock:

        try:

            result = sim.create_incident(
                incident_id
            )

        except ValueError as error:

            raise HTTPException(
                status_code=404,
                detail=str(error),
            )

        except Exception as error:

            raise HTTPException(
                status_code=500,
                detail=f"Dispatch engine error: {error}",
            )

    return result
