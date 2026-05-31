"""
Authentication routes.

POST /api/v1/auth    — exchange username/password for access + refresh token pair
POST /api/v1/refresh — exchange a valid refresh token for a new token pair (revokes the old one)

Rate limiting on /auth: 5 requests/minute per IP (enforced via slowapi on the app limiter).
"""
import logging

import jwt
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from travel_agent.api.models import AuthResponse, LoginRequest, RefreshRequest
from travel_agent.auth.jwt import create_token, decode_token
from travel_agent.auth.store import add_revoked_jti, get_user_by_username, is_jti_revoked

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level limiter — shares the same key function as the app limiter.
# slowapi matches decorators by key_func, not by instance identity, so this
# correctly applies to the app.state.limiter registered in main.py.
_limiter = Limiter(key_func=get_remote_address)


def _build_auth_response(user_id: int) -> AuthResponse:
    """Issue a fresh access + refresh token pair for the given user."""
    access_token, _, access_exp = create_token(user_id, "access")
    refresh_token, _, _ = create_token(user_id, "refresh")
    return AuthResponse(
        authorization=access_token,
        expiry=int(access_exp.timestamp()),
        refresh=refresh_token,
    )


@router.post(
    "/auth",
    response_model=AuthResponse,
    summary="Login — exchange credentials for a token pair",
)
@_limiter.limit("5/minute")
async def login(body: LoginRequest, request: Request) -> AuthResponse:
    user = get_user_by_username(body.username)
    if user is None or user["password"] != body.password:
        return JSONResponse(status_code=401, content={"error": "invalid_credentials"})

    logger.info("Login successful user_id=%s", user["id"])
    return _build_auth_response(user["id"])


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Refresh — exchange a refresh token for a new token pair",
)
async def refresh(body: RefreshRequest) -> AuthResponse:
    # Decode and validate the refresh token
    try:
        payload = decode_token(body.refresh)
    except jwt.ExpiredSignatureError:
        return JSONResponse(status_code=401, content={"error": "token_expired"})
    except jwt.InvalidTokenError:
        return JSONResponse(status_code=401, content={"error": "token_invalid"})

    if payload.get("type") != "refresh":
        return JSONResponse(status_code=401, content={"error": "token_type"})

    jti = payload.get("jti", "")
    if is_jti_revoked(jti):
        return JSONResponse(status_code=401, content={"error": "token_revoked"})

    # Revoke the consumed refresh token, then issue a new pair
    add_revoked_jti(jti)
    user_id = payload["userId"]
    logger.info("Token refreshed user_id=%s old_jti=%s", user_id, jti)
    return _build_auth_response(user_id)
