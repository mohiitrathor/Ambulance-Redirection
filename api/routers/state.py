from fastapi import APIRouter, HTTPException

from api.dependencies import manager
from simulation_output import SimulationOutput
from api.schemas.state import (
    SnapshotResponse,
    DashboardResponse,
    IncidentResponse,
    AmbulanceResponse,
    HospitalResponse,
)


# ==============================================================
# ROUTER
# ==============================================================

router = APIRouter()


# ==============================================================
# GET /state/snapshot
# ==============================================================

@router.get(
    "/snapshot",
    response_model=SnapshotResponse,
    summary="Full system snapshot",
    description=(
        "Returns the complete system state including "
        "all incidents, ambulances, hospitals, fleet "
        "summary, and event log."
    ),
)
def get_snapshot():

    sim = manager.simulator
    lock = manager.lock

    with lock:

        data = SimulationOutput.snapshot(
            sim.state
        )

    return data


# ==============================================================
# GET /state/dashboard
# ==============================================================

@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Dashboard snapshot",
    description=(
        "Lightweight snapshot with active incidents, "
        "fleet summary, and the last 10 events."
    ),
)
def get_dashboard():

    sim = manager.simulator
    lock = manager.lock

    with lock:

        data = SimulationOutput.dashboard_snapshot(
            sim.state
        )

    return data


# ==============================================================
# GET /state/incidents
# ==============================================================

@router.get(
    "/incidents",
    response_model=list[IncidentResponse],
    summary="All incidents",
)
def get_incidents():

    sim = manager.simulator
    lock = manager.lock

    with lock:

        incidents = [
            SimulationOutput.incident(incident)
            for incident
            in sim.state.incidents.values()
        ]

    return incidents


# ==============================================================
# GET /state/incidents/{incident_id}
# ==============================================================

@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
    summary="Single incident by ID",
)
def get_incident(incident_id: int):

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

        data = SimulationOutput.incident(
            incident
        )

    return data


# ==============================================================
# GET /state/ambulances
# ==============================================================

@router.get(
    "/ambulances",
    response_model=list[AmbulanceResponse],
    summary="All ambulances",
)
def get_ambulances():

    sim = manager.simulator
    lock = manager.lock

    with lock:

        ambulances = [
            SimulationOutput.ambulance(ambulance)
            for ambulance
            in sim.state.ambulances.values()
        ]

    return ambulances


# ==============================================================
# GET /state/ambulances/{ambulance_id}
# ==============================================================

@router.get(
    "/ambulances/{ambulance_id}",
    response_model=AmbulanceResponse,
    summary="Single ambulance by ID",
)
def get_ambulance(ambulance_id: str):

    sim = manager.simulator
    lock = manager.lock

    with lock:

        ambulance = sim.state.ambulances.get(
            ambulance_id
        )

        if ambulance is None:

            raise HTTPException(
                status_code=404,
                detail=(
                    f"Ambulance {ambulance_id} "
                    f"not found in state."
                ),
            )

        data = SimulationOutput.ambulance(
            ambulance
        )

    return data


# ==============================================================
# GET /state/hospitals
# ==============================================================

@router.get(
    "/hospitals",
    response_model=list[HospitalResponse],
    summary="All hospitals",
)
def get_hospitals():

    sim = manager.simulator
    lock = manager.lock

    with lock:

        hospitals = [
            SimulationOutput.hospital(hospital)
            for hospital
            in sim.state.hospitals.values()
        ]

    return hospitals


# ==============================================================
# GET /state/hospitals/{hospital_id}
# ==============================================================

@router.get(
    "/hospitals/{hospital_id}",
    response_model=HospitalResponse,
    summary="Single hospital by ID",
)
def get_hospital(hospital_id: str):

    sim = manager.simulator
    lock = manager.lock

    with lock:

        hospital = sim.state.hospitals.get(
            hospital_id
        )

        if hospital is None:

            raise HTTPException(
                status_code=404,
                detail=(
                    f"Hospital {hospital_id} "
                    f"not found in state."
                ),
            )

        data = SimulationOutput.hospital(
            hospital
        )

    return data
