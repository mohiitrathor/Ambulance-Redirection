"""
RAAH Authentication & Authorization Models
==========================================

Defines standard operational roles, granular permissions, the RBAC permission matrix,
and authenticated user identity representations.
"""

from enum import Enum
from typing import Set, Dict, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class Role(str, Enum):
    """
    Standard operational roles in RAAH emergency management.
    """
    DISPATCHER = "Dispatcher"
    SUPERVISOR = "Supervisor"
    MEDICAL_CONTROLLER = "Medical Controller"
    ADMINISTRATOR = "Administrator"


class Permission(str, Enum):
    """
    Granular operational permissions enforced across API endpoints.
    """
    VIEW_LIVE = "VIEW_LIVE"
    INGEST_EMERGENCY = "INGEST_EMERGENCY"
    STANDARD_DISPATCH = "STANDARD_DISPATCH"
    APPROVE_FLEET_REPOSITION = "APPROVE_FLEET_REPOSITION"
    APPROVE_HOSPITAL_DIVERSION = "APPROVE_HOSPITAL_DIVERSION"
    MANUAL_REROUTE = "MANUAL_REROUTE"
    MCI_CONTROL = "MCI_CONTROL"
    CHANGE_POLICY_MODE = "CHANGE_POLICY_MODE"
    KILL_SWITCH = "KILL_SWITCH"
    APPROVE_POLICY_CHANGE = "APPROVE_POLICY_CHANGE"
    ROLLBACK_POLICY = "ROLLBACK_POLICY"
    RUN_DRILLS = "RUN_DRILLS"
    USER_ADMINISTRATION = "USER_ADMINISTRATION"
    RESET_SIMULATION = "RESET_SIMULATION"


# Authoritative RBAC Matrix
PERMISSION_ROLES: Dict[Permission, Set[Role]] = {
    Permission.VIEW_LIVE: {
        Role.DISPATCHER, Role.SUPERVISOR, Role.MEDICAL_CONTROLLER, Role.ADMINISTRATOR
    },
    Permission.INGEST_EMERGENCY: {
        Role.DISPATCHER, Role.SUPERVISOR, Role.MEDICAL_CONTROLLER, Role.ADMINISTRATOR
    },
    Permission.STANDARD_DISPATCH: {
        Role.DISPATCHER, Role.SUPERVISOR, Role.MEDICAL_CONTROLLER, Role.ADMINISTRATOR
    },
    Permission.APPROVE_FLEET_REPOSITION: {
        Role.DISPATCHER, Role.SUPERVISOR, Role.ADMINISTRATOR
    },
    Permission.APPROVE_HOSPITAL_DIVERSION: {
        Role.SUPERVISOR, Role.MEDICAL_CONTROLLER, Role.ADMINISTRATOR
    },
    Permission.MANUAL_REROUTE: {
        Role.DISPATCHER, Role.SUPERVISOR, Role.MEDICAL_CONTROLLER, Role.ADMINISTRATOR
    },
    Permission.MCI_CONTROL: {
        Role.SUPERVISOR, Role.MEDICAL_CONTROLLER, Role.ADMINISTRATOR
    },
    Permission.CHANGE_POLICY_MODE: {
        Role.SUPERVISOR, Role.ADMINISTRATOR
    },
    Permission.KILL_SWITCH: {
        Role.SUPERVISOR, Role.MEDICAL_CONTROLLER, Role.ADMINISTRATOR
    },
    Permission.APPROVE_POLICY_CHANGE: {
        Role.SUPERVISOR, Role.ADMINISTRATOR
    },
    Permission.ROLLBACK_POLICY: {
        Role.SUPERVISOR, Role.ADMINISTRATOR
    },
    Permission.RUN_DRILLS: {
        Role.SUPERVISOR, Role.ADMINISTRATOR
    },
    Permission.USER_ADMINISTRATION: {
        Role.ADMINISTRATOR
    },
    Permission.RESET_SIMULATION: {
        Role.ADMINISTRATOR
    },
}


class AuthenticatedUser(BaseModel):
    """
    Authenticated user identity extracted from verified JWT claims.
    """
    username: str
    role: Role
    email: Optional[str] = None
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    token_id: Optional[str] = None

    def has_permission(self, permission: Permission) -> bool:
        """Check if this user's role grants the requested permission."""
        allowed_roles = PERMISSION_ROLES.get(permission, set())
        return self.role in allowed_roles


class TokenPayload(BaseModel):
    """
    Internal JWT claim schema.
    """
    sub: str = Field(description="Subject identifier / username")
    role: str = Field(description="Role name string")
    exp: int = Field(description="Expiration epoch timestamp")
    iat: int = Field(description="Issued-at epoch timestamp")
    iss: Optional[str] = Field(default=None, description="Token issuer")
    jti: Optional[str] = Field(default=None, description="Unique token identifier")
