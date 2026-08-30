from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from api.dependencies import manager
from redirection_engine import check_live_redirection
from api.schemas.redirection import (
    RedirectionResult,
    DecisionRecord,
)


# ==============================================================
# ROUTER
# ==============================================================

router = APIRouter()


# ==============================================================
# POST /redirect/check/{incident_id}
# ==============================================================

@router.post(
    "/check/{incident_id}",
    response_model=RedirectionResult,
    summary="Check redirection for an incident",
    description=(
        "Evaluate whether a dispatched incident "
        "should be redirected to a different hospital. "
        "This is a read-only evaluation — it does NOT "
        "apply the redirection."
    ),
)
def check_redirection(incident_id: int):

    sim = manager.simulator
    lock = manager.lock

    with lock:

        incident = sim.state.incidents.get(
            incident_id
        )

        if incident is None:

            raise HTTPException(
                status_code=404,
                detail=(
                    f"Incident {incident_id} "
                    f"not found in state."
                ),
            )

        try:

            result = check_live_redirection(
                sim.state,
                incident_id,
            )

        except ValueError as error:

            raise HTTPException(
                status_code=404,
                detail=str(error),
            )

        except Exception as error:

            raise HTTPException(
                status_code=500,
                detail=(
                    f"Redirection engine error: "
                    f"{error}"
                ),
            )

    return result


# ==============================================================
# GET /redirect/decisions
# ==============================================================

@router.get(
    "/decisions",
    response_model=list[DecisionRecord],
    summary="All redirection decisions",
    description=(
        "Returns every redirection decision logged "
        "during this simulation session."
    ),
)
def get_decisions():

    sim = manager.simulator
    lock = manager.lock

    with lock:

        decisions = sim.logger.get_decisions()

        results = [
            DecisionRecord(**asdict(decision))
            for decision in decisions
        ]

    return results


# ==============================================================
# GET /redirect/decisions/{incident_id}
# ==============================================================

@router.get(
    "/decisions/{incident_id}",
    response_model=list[DecisionRecord],
    summary="Decisions for a specific incident",
    description=(
        "Returns all redirection decisions logged "
        "for a specific incident."
    ),
)
def get_incident_decisions(incident_id: int):

    sim = manager.simulator
    lock = manager.lock

    with lock:

        decisions = sim.logger.get_incident_history(
            incident_id
        )

        results = [
            DecisionRecord(**asdict(decision))
            for decision in decisions
        ]

    return results
