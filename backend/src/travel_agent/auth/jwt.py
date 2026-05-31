"""
JWT creation and verification — pure functions, no I/O.

Token payload schema:
    {
        "userId": int,
        "iat":    int  (issued-at, seconds since epoch),
        "exp":    int  (expiry, seconds since epoch),
        "jti":    str  (UUID4 — used for revocation lookups),
        "type":   str  ("access" | "refresh"),
    }

Access tokens:  1 hour TTL
Refresh tokens: 30 days TTL
"""
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from travel_agent.config import settings

_ACCESS_TTL = timedelta(hours=1)
_REFRESH_TTL = timedelta(days=30)


def make_jti() -> str:
    """Generate a unique token ID."""
    return str(uuid.uuid4())


def create_token(user_id: int, token_type: str) -> tuple[str, str, datetime]:
    """
    Create a signed JWT.

    Args:
        user_id:    Stored in the 'userId' claim.
        token_type: 'access' or 'refresh'.

    Returns:
        (encoded_token, jti, expiry_datetime)
    """
    if token_type not in ("access", "refresh"):
        raise ValueError(f"Invalid token_type: {token_type!r}")

    ttl = _ACCESS_TTL if token_type == "access" else _REFRESH_TTL
    now = datetime.now(UTC)
    exp = now + ttl
    jti = make_jti()

    payload = {
        "userId": user_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "type": token_type,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti, exp


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT.

    Raises:
        jwt.ExpiredSignatureError  — token is past its 'exp'
        jwt.InvalidTokenError      — bad signature, malformed, etc.
    """
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
