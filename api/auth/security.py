"""
RAAH Cryptographic Token Security & Validation Layer
====================================================

Manages JWT generation, signature verification, expiration checks, and claims validation
using PyJWT and HMAC-SHA256 (HS256).
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import jwt
from fastapi import HTTPException, status

from api.settings import settings
from api.auth.models import Role, AuthenticatedUser, TokenPayload


class AuthenticationError(HTTPException):
    """Standard 401 Unauthorized exception with WWW-Authenticate header."""
    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_access_token(
    username: str,
    role: Role,
    expires_delta: Optional[timedelta] = None,
    email: Optional[str] = None,
) -> str:
    """
    Generate a signed JWT access token for an authenticated operator.
    Raw tokens are never logged.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_expiration_minutes)

    payload: Dict[str, Any] = {
        "sub": username,
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if settings.jwt_issuer:
        payload["iss"] = settings.jwt_issuer
    if email:
        payload["email"] = email

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token


def decode_access_token(token: str) -> AuthenticatedUser:
    """
    Decode and validate a signed JWT token.
    Enforces signature verification, expiration, issuer matching, subject, and valid role claim.
    Raises AuthenticationError (HTTP 401) on any validation failure.
    """
    if not token or not isinstance(token, str):
        raise AuthenticationError("Malformed or empty bearer token")

    try:
        # Decode options
        decode_kwargs: Dict[str, Any] = {
            "algorithms": [settings.jwt_algorithm],
            "options": {
                "require": ["exp", "iat", "sub"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
            },
        }
        if settings.jwt_issuer:
            decode_kwargs["issuer"] = settings.jwt_issuer

        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            **decode_kwargs,
        )

    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidSignatureError:
        raise AuthenticationError("Invalid token signature")
    except jwt.InvalidIssuerError:
        raise AuthenticationError("Invalid token issuer")
    except jwt.DecodeError:
        raise AuthenticationError("Malformed or unparseable token")
    except Exception as e:
        raise AuthenticationError(f"Token validation failed: {str(e)}")

    # Validate claims
    username = payload.get("sub")
    if not username:
        raise AuthenticationError("Token subject (sub) claim missing")

    role_str = payload.get("role")
    if not role_str:
        raise AuthenticationError("Token role claim missing")

    try:
        role = Role(role_str)
    except ValueError:
        raise AuthenticationError(f"Token contains unrecognized role: '{role_str}'")

    issued_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc) if "iat" in payload else None
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None

    return AuthenticatedUser(
        username=username,
        role=role,
        email=payload.get("email"),
        issued_at=issued_at,
        expires_at=expires_at,
        token_id=payload.get("jti"),
    )


def create_test_token(
    role: Role = Role.DISPATCHER,
    username: str = "test_user",
    expires_delta: Optional[timedelta] = None,
    secret_key: Optional[str] = None,
) -> str:
    """
    Helper for test suites to generate valid test tokens with specific roles.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=60)

    payload: Dict[str, Any] = {
        "sub": username,
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if settings.jwt_issuer:
        payload["iss"] = settings.jwt_issuer

    key = secret_key or settings.jwt_secret_key
    return jwt.encode(payload, key, algorithm=settings.jwt_algorithm)
