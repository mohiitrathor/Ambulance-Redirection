"""
RAAH State Persistence & Durability API Router
==============================================

Provides operator endpoints for state checkpointing, recovery inspection,
checkpoint history retrieval, and durability health telemetry.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends

from api.dependencies import manager
from api.auth import (
    AuthenticatedUser,
    Role,
    Permission,
    require_permission,
    require_any_role,
    get_current_user,
)

router = APIRouter(prefix="/persistence", tags=["State Persistence & Durability"])


class CheckpointCreateRequest(BaseModel):
    notes: Optional[str] = Field(default=None, description="Operator audit notes for checkpoint")
    tags: Optional[List[str]] = Field(default=None, description="Operational tags for categorization")


class CheckpointResponse(BaseModel):
    checkpoint_id: str
    simulation_time: int
    schema_version: int
    saved_at: str
    checksum: str
    is_valid: bool
    metadata: Dict[str, Any]
    payload_summary: Dict[str, Any]


class PersistenceStatusResponse(BaseModel):
    enabled: bool
    backend: str
    healthy: bool
    recovery_status: str
    recovered_checkpoint_id: Optional[str]
    total_checkpoints: int
    last_checkpoint_id: Optional[str]
    last_checkpoint_sim_time: Optional[int]
    last_checkpoint_saved_at: Optional[str]
    telemetry_queue: Dict[str, Any]
    error: Optional[str]


@router.post(
    "/checkpoint",
    response_model=CheckpointResponse,
    summary="Create authoritative state checkpoint",
    description="Atomically captures the live DispatchState and persists a durable, checksummed checkpoint.",
)
def create_checkpoint(
    req: Optional[CheckpointCreateRequest] = None,
    user: AuthenticatedUser = Depends(require_any_role(Role.SUPERVISOR, Role.ADMINISTRATOR)),
):
    notes = req.notes if req and req.notes else "Manual operator checkpoint"
    tags = req.tags if req and req.tags else []

    metadata = {
        "operator": user.username,
        "role": user.role.value,
        "notes": notes,
        "tags": tags,
    }

    try:
        record = manager.create_checkpoint(metadata=metadata)
        return record.to_dict()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to create state checkpoint: {ex}")


@router.get(
    "/checkpoints",
    response_model=List[CheckpointResponse],
    summary="List recent state checkpoints",
    description="Retrieve chronological list of persisted state checkpoints (newest first).",
)
def list_checkpoints(
    limit: int = 50,
    user: AuthenticatedUser = Depends(require_permission(Permission.VIEW_LIVE)),
):
    try:
        records = manager.persistence_store.list_checkpoints(limit=limit)
        return [r.to_dict() for r in records]
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to list checkpoints: {ex}")


@router.get(
    "/checkpoints/{checkpoint_id}",
    response_model=CheckpointResponse,
    summary="Get details of a specific checkpoint",
)
def get_checkpoint(
    checkpoint_id: str,
    user: AuthenticatedUser = Depends(require_permission(Permission.VIEW_LIVE)),
):
    record = manager.persistence_store.load_checkpoint(checkpoint_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Checkpoint '{checkpoint_id}' not found.")
    return record.to_dict()


@router.get(
    "/status",
    response_model=PersistenceStatusResponse,
    summary="Get persistence store and durability status",
    description="Returns persistence store health, telemetry queue depth, and recovery status.",
)
def get_persistence_status(
    user: AuthenticatedUser = Depends(require_permission(Permission.VIEW_LIVE)),
):
    from api.settings import settings
    from api.persistence import persistence_bridge

    health = manager.persistence_store.health_check()
    return PersistenceStatusResponse(
        enabled=settings.persistence_enabled,
        backend=settings.persistence_backend,
        healthy=health.get("healthy", False),
        recovery_status=manager.recovery_status,
        recovered_checkpoint_id=manager.recovered_checkpoint_id,
        total_checkpoints=health.get("total_checkpoints", 0),
        last_checkpoint_id=manager.persistence_store.last_checkpoint_id,
        last_checkpoint_sim_time=manager.persistence_store.last_checkpoint_sim_time,
        last_checkpoint_saved_at=manager.persistence_store.last_checkpoint_saved_at,
        telemetry_queue={
            "depth": persistence_bridge.queue_depth,
            "capacity": persistence_bridge.queue_capacity,
            "dropped": persistence_bridge.dropped_count,
        },
        error=health.get("error"),
    )


@router.post(
    "/restore/{checkpoint_id}",
    summary="Restore state from an explicit checkpoint",
    description="Cold-restores authoritative DispatchState from the designated checkpoint. Administrator only.",
)
def restore_checkpoint(
    checkpoint_id: str,
    user: AuthenticatedUser = Depends(require_permission(Permission.RESET_SIMULATION)),
):
    try:
        manager.restore_from_checkpoint(checkpoint_id)
        return {
            "status": "RESTORED",
            "checkpoint_id": checkpoint_id,
            "sim_time": manager.simulator.state.current_time,
            "operator": user.username,
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to restore checkpoint '{checkpoint_id}': {ex}")
