"""
Integration tests for the FastAPI layer.

These tests exercise the full HTTP stack (routing, request validation,
response serialization) with the agent loop mocked out. They do NOT
call the Anthropic API or external services.

We use FastAPI's TestClient which runs the ASGI app in-process.

All /api/v1/chat requests carry a valid Bearer token — the auth middleware
is active and will reject unauthenticated requests with 401.
The store is patched to a temp db so revocation checks don't touch disk.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from travel_agent.auth.jwt import create_token


@pytest.fixture
def access_token() -> str:
    """Valid access token for user_id=1 — no store interaction needed."""
    token, _, _ = create_token(user_id=1, token_type="access")
    return token


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    db = {"users": [{"id": 1, "username": "test", "password": "test"}], "revoked_tokens": []}
    f = tmp_path / "db.json"
    f.write_text(json.dumps(db))
    return f


def test_health_check(api_client: TestClient):
    """GET /health should return 200 with status=ok (no auth required)."""
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_chat_returns_agent_response(api_client: TestClient, access_token: str, db_file: Path):
    """POST /api/v1/chat should return the agent's response."""
    with patch("travel_agent.auth.store.settings") as ms:
        ms.db_path = str(db_file)
        with patch("travel_agent.api.routes.agent.loop.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Here is your Tokyo trip plan!"
            response = api_client.post(
                "/api/v1/chat",
                json={"message": "Plan a 5-day trip to Tokyo"},
                headers={"Authorization": f"Bearer {access_token}"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Here is your Tokyo trip plan!"
    mock_run.assert_awaited_once_with(
        user_message="Plan a 5-day trip to Tokyo",
        history=None,
    )


def test_chat_passes_history_to_agent(api_client: TestClient, access_token: str, db_file: Path):
    """POST /api/v1/chat should forward conversation history to the agent loop."""
    history = [
        {"role": "user", "content": "I want to go somewhere warm"},
        {"role": "assistant", "content": "How about Tokyo?"},
    ]

    with patch("travel_agent.auth.store.settings") as ms:
        ms.db_path = str(db_file)
        with patch("travel_agent.api.routes.agent.loop.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Great choice!"
            response = api_client.post(
                "/api/v1/chat",
                json={"message": "Yes, Tokyo!", "history": history},
                headers={"Authorization": f"Bearer {access_token}"},
            )

    assert response.status_code == 200
    _, kwargs = mock_run.call_args
    assert len(kwargs["history"]) == 2
    assert kwargs["history"][0]["role"] == "user"


def test_chat_returns_500_on_agent_error(api_client: TestClient, access_token: str, db_file: Path):
    """POST /api/v1/chat should return 500 when the agent loop raises."""
    with patch("travel_agent.auth.store.settings") as ms:
        ms.db_path = str(db_file)
        with patch("travel_agent.api.routes.agent.loop.run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("Anthropic API unavailable")
            response = api_client.post(
                "/api/v1/chat",
                json={"message": "Plan a trip"},
                headers={"Authorization": f"Bearer {access_token}"},
            )

    assert response.status_code == 500


def test_chat_rejects_empty_message(api_client: TestClient, access_token: str, db_file: Path):
    """POST /api/v1/chat should return 422 for an empty message (Pydantic min_length=1)."""
    with patch("travel_agent.auth.store.settings") as ms:
        ms.db_path = str(db_file)
        response = api_client.post(
            "/api/v1/chat",
            json={"message": ""},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert response.status_code == 422
