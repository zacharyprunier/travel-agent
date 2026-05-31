"""Tests for the in-memory session store."""
import pytest

from travel_agent.session.store import (
    Session,
    _sessions,
    create_session,
    get_session,
    update_session,
)


@pytest.fixture(autouse=True)
def _clear_sessions():
    """Ensure each test starts with an empty session store."""
    _sessions.clear()
    yield
    _sessions.clear()


def test_create_session():
    session = create_session("Plan a trip to Tokyo")
    assert isinstance(session, Session)
    assert session.original_intent == "Plan a trip to Tokyo"
    assert session.full_history == []
    assert session.summary is None
    assert session.id in _sessions


def test_get_session_found():
    session = create_session("test")
    result = get_session(session.id)
    assert result is session


def test_get_session_not_found():
    assert get_session("nonexistent-id") is None


def test_update_session_history():
    session = create_session("test")
    history = [{"role": "user", "content": "hello"}]
    update_session(session.id, full_history=history)
    assert session.full_history == history


def test_update_session_summary():
    session = create_session("test")
    update_session(session.id, full_history=[], summary="User wants to go to Tokyo")
    assert session.summary == "User wants to go to Tokyo"


def test_update_session_not_found():
    with pytest.raises(KeyError, match="not found"):
        update_session("nonexistent", full_history=[])
