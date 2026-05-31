"""
Integration tests for the POST /api/v1/chat/stream SSE endpoint.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from travel_agent.auth.jwt import create_token


def _auth_header() -> dict:
    token, _, _ = create_token(user_id=1, token_type="access")
    return {"Authorization": f"Bearer {token}"}


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE text into a list of event dicts."""
    events = []
    for part in text.split("\n\n"):
        line = part.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def test_chat_stream_requires_auth(api_client):
    """Stream endpoint should return 401 without a Bearer token."""
    response = api_client.post(
        "/api/v1/chat/stream",
        json={"message": "hello"},
    )
    assert response.status_code == 401


def test_chat_stream_returns_sse(api_client):
    """Stream endpoint should return text/event-stream content type."""

    async def _fake_stream(user_message, history=None, _raw_history_out=None):
        yield {"type": "delta", "content": "hello"}
        yield {"type": "done"}
        if _raw_history_out is not None:
            _raw_history_out.extend([
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": "hello"},
            ])

    with patch("travel_agent.api.routes.agent.loop.run_stream", side_effect=_fake_stream):
        response = api_client.post(
            "/api/v1/chat/stream",
            json={"message": "hello"},
            headers=_auth_header(),
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


def test_chat_stream_emits_session_event(api_client):
    """First event should be type=session with a session_id."""

    async def _fake_stream(user_message, history=None, _raw_history_out=None):
        yield {"type": "delta", "content": "ok"}
        yield {"type": "done"}

    with patch("travel_agent.api.routes.agent.loop.run_stream", side_effect=_fake_stream):
        response = api_client.post(
            "/api/v1/chat/stream",
            json={"message": "hello"},
            headers=_auth_header(),
        )

    events = _parse_sse(response.text)
    assert events[0]["type"] == "session"
    assert "session_id" in events[0]


def test_chat_stream_emits_done(api_client):
    """Stream should end with a done event."""

    async def _fake_stream(user_message, history=None, _raw_history_out=None):
        yield {"type": "thinking", "content": "working..."}
        yield {"type": "delta", "content": "result"}
        yield {"type": "done"}

    with patch("travel_agent.api.routes.agent.loop.run_stream", side_effect=_fake_stream):
        response = api_client.post(
            "/api/v1/chat/stream",
            json={"message": "plan a trip"},
            headers=_auth_header(),
        )

    events = _parse_sse(response.text)
    types = [e["type"] for e in events]
    assert "session" in types
    assert "thinking" in types
    assert "delta" in types
    assert types[-1] == "done"


def test_chat_stream_rejects_empty_message(api_client):
    """Empty message should fail validation (422)."""
    response = api_client.post(
        "/api/v1/chat/stream",
        json={"message": ""},
        headers=_auth_header(),
    )
    assert response.status_code == 422
