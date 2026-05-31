"""
JSON file persistence for users and revoked token JTIs.

No concurrency protection — single-process demo only.

Schema:
    {
        "users": [{"id": int, "username": str, "password": str}],
        "revoked_tokens": [str]   # list of JTI strings
    }
"""
import json
import logging
from pathlib import Path

from travel_agent.config import settings

logger = logging.getLogger(__name__)


def _db_path() -> Path:
    return Path(settings.db_path)


def _load() -> dict:
    path = _db_path()
    if not path.exists():
        raise FileNotFoundError(f"Auth database not found at {path}")
    with path.open() as f:
        return json.load(f)


def _save(data: dict) -> None:
    with _db_path().open("w") as f:
        json.dump(data, f, indent=2)


def get_user_by_username(username: str) -> dict | None:
    """Return the user dict if found, None otherwise."""
    db = _load()
    for user in db.get("users", []):
        if user["username"] == username:
            return user
    return None


def is_jti_revoked(jti: str) -> bool:
    """Return True if this JTI appears in the revocation list."""
    db = _load()
    return jti in db.get("revoked_tokens", [])


def add_revoked_jti(jti: str) -> None:
    """Append a JTI to the revocation list and persist."""
    db = _load()
    revoked = db.setdefault("revoked_tokens", [])
    if jti not in revoked:
        revoked.append(jti)
        _save(db)
        logger.info("Revoked token jti=%s", jti)
