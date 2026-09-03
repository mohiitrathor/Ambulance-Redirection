"""
RAAH Authentication & RBAC Package
===================================

Exports core security primitives, operational roles, permissions, token utilities,
and FastAPI dependencies.
"""

from api.auth.models import (
    Role,
    Permission,
    PERMISSION_ROLES,
    AuthenticatedUser,
    TokenPayload,
)
from api.auth.security import (
    create_access_token,
    decode_access_token,
    create_test_token,
    AuthenticationError,
)
from api.auth.dependencies import (
    get_current_user,
    require_authenticated_user,
    require_role,
    require_any_role,
    require_permission,
)
from api.auth.router import router as auth_router

__all__ = [
    "Role",
    "Permission",
    "PERMISSION_ROLES",
    "AuthenticatedUser",
    "TokenPayload",
    "create_access_token",
    "decode_access_token",
    "create_test_token",
    "AuthenticationError",
    "get_current_user",
    "require_authenticated_user",
    "require_role",
    "require_any_role",
    "require_permission",
    "auth_router",
]
