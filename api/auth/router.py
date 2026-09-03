"""
RAAH Authentication API Router
==============================

Provides token issuance and inspection endpoints for operators and clients.
"""

from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, status

from api.auth.models import Role, AuthenticatedUser
from api.auth.security import create_access_token
from api.auth.dependencies import get_current_user, require_authenticated_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


class TokenRequest(BaseModel):
    """Token generation request payload."""
    username: str = Field(..., description="Operator username / callsign")
    role: Role = Field(..., description="Assigned operational role")
    email: Optional[str] = Field(default=None, description="Operator email address")


class TokenResponse(BaseModel):
    """Token response payload."""
    access_token: str
    token_type: str = "bearer"
    username: str
    role: Role
    expires_in_minutes: int


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Issue an operational JWT access token",
    description="Generate a cryptographically signed HMAC-SHA256 Bearer JWT token.",
)
def issue_token(req: TokenRequest):
    """
    Issue a new JWT access token signed with the configured secret key.
    Raw tokens are never written to disk or logs.
    """
    from api.settings import settings
    token = create_access_token(
        username=req.username,
        role=req.role,
        email=req.email,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=req.username,
        role=req.role,
        expires_in_minutes=settings.jwt_expiration_minutes,
    )


@router.get(
    "/me",
    response_model=AuthenticatedUser,
    summary="Inspect current authenticated operator identity",
    description="Returns the claims and role of the current verified JWT bearer token.",
)
def get_me(user: AuthenticatedUser = Depends(get_current_user)):
    return user
