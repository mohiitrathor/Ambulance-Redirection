"""
RAAH Server-Sent Events (SSE) Router
====================================

Provides the authenticated streaming endpoint GET /events/stream.
Delivers real-time state projections, ticks, and notifications to connected clients.
"""

import asyncio
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from api.auth import (
    AuthenticatedUser,
    Permission,
    require_permission,
)
from api.auth.dependencies import bearer_scheme
from api.auth.models import Role, PERMISSION_ROLES
from api.auth.security import decode_access_token, AuthenticationError
from api.dependencies import manager
from api.realtime.broadcaster import broadcaster
from api.realtime.models import EventType
from api.settings import settings
from simulation_output import SimulationOutput

logger = logging.getLogger("raah.realtime.router")

router = APIRouter(tags=["Realtime Events"])


async def authenticate_stream_user(
    request: Request,
    token: Optional[str] = Query(default=None),
) -> AuthenticatedUser:
    """
    Authenticate the streaming client using Bearer header (primary)
    or query token ?token=<jwt> (secondary fallback for browser EventSource).
    Guarantees that token is NEVER logged, echoed, or leaked in errors.
    """
    # 1. Check Authorization header
    auth_header = request.headers.get("authorization")
    raw_token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        raw_token = auth_header[7:].strip()
    elif token:
        raw_token = token.strip()

    if raw_token:
        try:
            user = decode_access_token(raw_token)
            return user
        except AuthenticationError as exc:
            # Clean 401 without exposing the token
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed: invalid or expired bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed: could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 2. No token provided
    if settings.auth_enforced:
        if settings.environment != "production" and settings.dev_auth_fallback:
            return AuthenticatedUser(
                username="dev_stream_operator",
                role=Role.ADMINISTRATOR,
                email="dev_operator@raah.internal",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        username="anonymous_stream_user",
        role=Role.ADMINISTRATOR,
    )


@router.get(
    "/events/stream",
    summary="Server-Sent Events Realtime Stream",
    description=(
        "Streams real-time authoritative state projections, ticks, and emergency "
        "events to connected clients. Supports automatic reconnect with sequence "
        "gap recovery and idle keep-alive heartbeats."
    ),
)
async def stream_realtime_events(
    request: Request,
    since_sequence: Optional[int] = Query(default=None),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    max_events: Optional[int] = Query(
        default=None,
        ge=1,
        description="Optional limit of events before clean stream termination",
    ),
    user: AuthenticatedUser = Depends(authenticate_stream_user),
):
    # Enforce VIEW_LIVE permission
    allowed_roles = PERMISSION_ROLES.get(Permission.VIEW_LIVE, set())
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: '{user.role.value}' role does not have VIEW_LIVE permission",
        )

    # Resolve reconnect sequence
    req_sequence = since_sequence
    if req_sequence is None and last_event_id is not None:
        try:
            req_sequence = int(last_event_id)
        except (ValueError, TypeError):
            req_sequence = None

    client_id = f"client_{uuid.uuid4().hex[:8]}"

    async def event_generator():
        session = broadcaster.subscribe(
            client_id=client_id,
            username=user.username,
            loop=asyncio.get_running_loop(),
        )
        emitted_count = 0

        try:
            # Step 1: Initial Snapshot or Replay
            if req_sequence is not None:
                replayed_events, gap_detected = broadcaster.get_events_since(req_sequence)
                if gap_detected:
                    # Extract authoritative projection under manager.lock
                    with manager.lock:
                        sim_state = manager.simulator.state
                        dash_snapshot = SimulationOutput.dashboard_snapshot(sim_state)
                        cur_time = sim_state.current_time

                    # Deliver authoritative snapshot with gap flag directly to this client
                    from api.realtime.models import RealtimeEvent
                    snap_event = RealtimeEvent(
                        event_type=EventType.STATE_SNAPSHOT.value,
                        simulation_time=cur_time,
                        sequence=broadcaster.current_sequence,
                        payload={
                            "dashboard": dash_snapshot,
                            "gap_detected": True,
                            "reconnect_sequence": req_sequence,
                        },
                    )
                    emitted_count += 1
                    yield snap_event.to_sse()
                    if max_events is not None and emitted_count >= max_events:
                        return
                else:
                    for rev in replayed_events:
                        emitted_count += 1
                        yield rev.to_sse()
                        if max_events is not None and emitted_count >= max_events:
                            return
            else:
                # Fresh connection: emit initial authoritative snapshot
                with manager.lock:
                    sim_state = manager.simulator.state
                    dash_snapshot = SimulationOutput.dashboard_snapshot(sim_state)
                    cur_time = sim_state.current_time

                # Produce snapshot event directly for this client
                from api.realtime.models import RealtimeEvent
                init_snap = RealtimeEvent(
                    event_type=EventType.STATE_SNAPSHOT.value,
                    simulation_time=cur_time,
                    sequence=broadcaster.current_sequence,
                    payload={"dashboard": dash_snapshot, "initial": True},
                )
                emitted_count += 1
                yield init_snap.to_sse()
                if max_events is not None and emitted_count >= max_events:
                    return

            # Step 2: Stream live events with keep-alive heartbeats
            last_hb_time = time.time()
            while session.is_active:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(session.queue.get(), timeout=0.2)
                    if event is None:
                        # Termination sentinel
                        break
                    emitted_count += 1
                    yield event.to_sse()
                    if max_events is not None and emitted_count >= max_events:
                        break
                except asyncio.TimeoutError:
                    # Connection is idle: check if heartbeat is due (15s)
                    if time.time() - last_hb_time >= 15.0:
                        last_hb_time = time.time()
                        with manager.lock:
                            cur_sim_time = manager.simulator.state.current_time if (manager.simulator and manager.simulator.state) else 0
                        hb = broadcaster.create_heartbeat(cur_sim_time)
                        emitted_count += 1
                        yield hb.to_sse()
                        if max_events is not None and emitted_count >= max_events:
                            break

        except (asyncio.CancelledError, GeneratorExit):
            pass
        except Exception as exc:
            logger.warning("Stream exception for client '%s': %s", client_id, exc)
        finally:
            broadcaster.unsubscribe(client_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
