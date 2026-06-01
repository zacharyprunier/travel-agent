"""
Auth store — env-var credentials + in-memory token revocation.

Credentials come from the environment (ADMIN_USERNAME / ADMIN_PASSWORD via
settings). There is no database: this is a single-user deployment.

Revoked token JTIs are held in a process-level set. This resets on restart or
redeploy, which is acceptable given the short access-token TTL (1 hour). Single
process only — no cross-instance sharing.
"""
import logging
import secrets

from travel_agent.config import settings

logger = logging.getLogger(__name__)

# Synthetic ID for the single admin user (the JWT 'userId' claim).
_ADMIN_USER_ID = 1

# Process-level revocation list. Cleared on restart/redeploy.
_revoked_jtis: set[str] = set()


def verify_credentials(username: str, password: str) -> dict | None:
    """Return the admin user dict if credentials match, else None.

    Both comparisons use constant-time matching and are always evaluated
    (no short-circuit) to avoid leaking timing information.
    """
    username_ok = secrets.compare_digest(username, settings.admin_username)
    password_ok = secrets.compare_digest(password, settings.admin_password)
    if username_ok and password_ok:
        return {"id": _ADMIN_USER_ID, "username": settings.admin_username}
    return None


def is_jti_revoked(jti: str) -> bool:
    """Return True if this JTI appears in the in-memory revocation set."""
    return jti in _revoked_jtis


def add_revoked_jti(jti: str) -> None:
    """Add a JTI to the in-memory revocation set (idempotent)."""
    if jti not in _revoked_jtis:
        _revoked_jtis.add(jti)
        logger.info("Revoked token jti=%s", jti)
