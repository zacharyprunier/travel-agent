"""
In-memory session store.

Sessions persist for the lifetime of the process. No concurrency protection
— single-process demo only.
"""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Session:
    id: str
    created_at: datetime
    original_intent: str
    full_history: list[dict] = field(default_factory=list)
    summary: str | None = None


_sessions: dict[str, Session] = {}


def create_session(first_message: str) -> Session:
    """Create a new session with the first user message as original intent."""
    session = Session(
        id=str(uuid.uuid4()),
        created_at=datetime.now(UTC),
        original_intent=first_message,
    )
    _sessions[session.id] = session
    return session


def get_session(session_id: str) -> Session | None:
    """Return the session if it exists, None otherwise."""
    return _sessions.get(session_id)


def update_session(
    session_id: str,
    full_history: list[dict],
    summary: str | None = None,
) -> None:
    """Update a session's history and optionally its summary."""
    session = _sessions.get(session_id)
    if session is None:
        raise KeyError(f"Session {session_id!r} not found")
    session.full_history = full_history
    if summary is not None:
        session.summary = summary
