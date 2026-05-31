"""
JWT authentication middleware.

Protects all routes except the explicitly unprotected set.
/docs and /openapi.json are additionally bypassed when DEPLOYMENT_TYPE=DEV.

401 error shapes returned as JSON:
    {"error": "token_missing"}   — no Authorization header
    {"error": "token_invalid"}   — malformed / bad signature
    {"error": "token_expired"}   — past exp claim
    {"error": "token_revoked"}   — JTI in revocation list
    {"error": "token_type"}      — wrong token type (e.g. refresh used as access)
"""
import json
import logging

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from travel_agent.auth.jwt import decode_token
from travel_agent.auth.store import is_jti_revoked
from travel_agent.config import settings

logger = logging.getLogger(__name__)

# Always unprotected — auth and health never require a token
_UNPROTECTED: frozenset[str] = frozenset({
    "/health",
    "/api/v1/auth",
    "/api/v1/refresh",
})

# Unprotected only in DEV — docs routes
_DEV_ONLY_UNPROTECTED: frozenset[str] = frozenset({
    "/docs",
    "/openapi.json",
    "/redoc",
})


def _json_401(error: str) -> Response:
    return Response(
        content=json.dumps({"error": error}),
        status_code=401,
        media_type="application/json",
    )


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Always-open routes
        if path in _UNPROTECTED:
            return await call_next(request)

        # Docs routes — open in DEV, protected in PROD
        if path in _DEV_ONLY_UNPROTECTED:
            if settings.deployment_type.upper() == "DEV":
                return await call_next(request)
            # Fall through to token validation in PROD

        # Extract Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _json_401("token_missing")

        raw_token = auth_header.removeprefix("Bearer ").strip()

        # Decode and verify signature + expiry
        try:
            payload = decode_token(raw_token)
        except jwt.ExpiredSignatureError:
            return _json_401("token_expired")
        except jwt.InvalidTokenError:
            return _json_401("token_invalid")

        # Must be an access token — refuse refresh tokens hitting API routes
        if payload.get("type") != "access":
            return _json_401("token_type")

        # Revocation check
        jti = payload.get("jti", "")
        if is_jti_revoked(jti):
            return _json_401("token_revoked")

        # Attach decoded payload for downstream handlers if needed
        request.state.token_payload = payload
        return await call_next(request)
