"""
RAAH Authentication & RBAC FastAPI Dependencies
================================================

Provides reusable, declarative authentication and role-based authorization dependencies
for endpoint protection and operator identity attribution.
"""

from typing import List, Callable, Optional, Set
import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from api.settings import settings
from api.auth.models import Role, Permission, AuthenticatedUser, PERMISSION_ROLES
from api.auth.security import decode_access_token, AuthenticationError

logger = logging.getLogger("raah.auth")

# FastAPI Bearer security scheme with auto_error=False to support clean 401 handling
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """
    Extract and validate the active authenticated user from the Authorization: Bearer token.
    Enforces strict 401 on missing, expired, or malformed credentials.
    Supports explicit dev_auth_fallback only when not running in production.
    """
    if credentials is not None:
        # Token explicitly provided: must be cryptographically valid
        token = credentials.credentials
        user = decode_access_token(token)
        return user

    # No token provided
    if settings.auth_enforced:
        if settings.environment != "production" and settings.dev_auth_fallback:
            # Explicit, auditable development fallback for local tools and unauthenticated test suites
            return AuthenticatedUser(
                username="dev_operator",
                role=Role.ADMINISTRATOR,
                email="dev_operator@raah.internal",
            )
        raise AuthenticationError("Missing authorization bearer token")

    # In case auth is globally toggled off for testing
    return AuthenticatedUser(
        username="anonymous",
        role=Role.ADMINISTRATOR,
    )


def require_authenticated_user() -> Callable:
    """
    Returns the callable dependency for requiring an authenticated user.
    """
    return get_current_user


def require_role(required_role: Role) -> Callable:
    """
    Dependency requiring the user to have an exact operational role.
    Raises HTTP 403 Forbidden if the user's role does not match.
    """
    async def role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Action requires '{required_role.value}' role (current: '{user.role.value}').",
            )
        return user

    return role_checker


def require_any_role(*allowed_roles: Role) -> Callable:
    """
    Dependency requiring the user's role to be one of the specified allowed roles.
    Raises HTTP 403 Forbidden if the user is not in the authorized set.
    """
    allowed_set: Set[Role] = set(allowed_roles)

    async def any_role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role not in allowed_set:
            role_names = [r.value for r in allowed_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Insufficient privileges. Required one of {role_names} (current: '{user.role.value}').",
            )
        return user

    return any_role_checker


def require_permission(permission: Permission) -> Callable:
    """
    Dependency checking the RBAC permission matrix for the active user.
    Raises HTTP 403 Forbidden if the user's role is not authorized for the permission.
    """
    allowed_roles = PERMISSION_ROLES.get(permission, set())

    async def permission_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not user.has_permission(permission):
            role_names = [r.value for r in allowed_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Permission '{permission.value}' requires one of {role_names} (current: '{user.role.value}').",
            )
        return user

    return permission_checker
