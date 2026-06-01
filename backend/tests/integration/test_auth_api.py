"""
Integration tests for the auth endpoints.

All tests run through the full ASGI stack. Admin credentials are injected via
patched settings; revocation uses the in-memory store (cleared per-test by the
autouse fixture in conftest).
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from travel_agent.auth.jwt import create_token
from travel_agent.auth.store import add_revoked_jti


@pytest.fixture
def auth_client(api_client: TestClient) -> TestClient:
    """TestClient with known admin credentials patched into the store."""
    with patch("travel_agent.auth.store.settings") as ms:
        ms.admin_username = "test"
        ms.admin_password = "test"
        yield api_client


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_valid_credentials(auth_client: TestClient):
    resp = auth_client.post("/api/v1/auth", json={"username": "test", "password": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert "authorization" in body
    assert "refresh" in body
    assert isinstance(body["expiry"], int)


def test_login_wrong_password(auth_client: TestClient):
    resp = auth_client.post("/api/v1/auth", json={"username": "test", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


def test_login_unknown_user(auth_client: TestClient):
    resp = auth_client.post("/api/v1/auth", json={"username": "ghost", "password": "x"})
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


def test_login_empty_body_rejected(auth_client: TestClient):
    resp = auth_client.post("/api/v1/auth", json={})
    assert resp.status_code == 422


# ── Refresh ───────────────────────────────────────────────────────────────────

def test_refresh_issues_new_token_pair(auth_client: TestClient):
    # Login first to get a real refresh token
    login = auth_client.post("/api/v1/auth", json={"username": "test", "password": "test"})
    refresh_token = login.json()["refresh"]

    resp = auth_client.post("/api/v1/refresh", json={"refresh": refresh_token})

    assert resp.status_code == 200
    body = resp.json()
    assert "authorization" in body
    assert body["refresh"] != refresh_token  # new refresh token issued


def test_refresh_rejects_access_token(auth_client: TestClient):
    access_token, _, _ = create_token(user_id=1, token_type="access")
    resp = auth_client.post("/api/v1/refresh", json={"refresh": access_token})
    assert resp.status_code == 401
    assert resp.json()["error"] == "token_type"


def test_refresh_rejects_revoked_token(auth_client: TestClient):
    refresh_token, jti, _ = create_token(user_id=1, token_type="refresh")
    add_revoked_jti(jti)
    resp = auth_client.post("/api/v1/refresh", json={"refresh": refresh_token})
    assert resp.status_code == 401
    assert resp.json()["error"] == "token_revoked"


# ── Auth middleware ───────────────────────────────────────────────────────────

def test_protected_route_requires_token(auth_client: TestClient):
    resp = auth_client.post("/api/v1/chat", json={"message": "hi"})
    assert resp.status_code == 401
    assert resp.json()["error"] == "token_missing"


def test_protected_route_accepts_valid_token(auth_client: TestClient):
    from unittest.mock import AsyncMock
    access_token, _, _ = create_token(user_id=1, token_type="access")

    with patch("travel_agent.api.routes.agent.loop.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "Here is your plan"
        resp = auth_client.post(
            "/api/v1/chat",
            json={"message": "Plan a trip"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    assert resp.status_code == 200


def test_middleware_rejects_refresh_token_on_protected_route(auth_client: TestClient):
    refresh_token, _, _ = create_token(user_id=1, token_type="refresh")
    resp = auth_client.post(
        "/api/v1/chat",
        json={"message": "hi"},
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "token_type"


def test_middleware_rejects_revoked_access_token(auth_client: TestClient):
    access_token, jti, _ = create_token(user_id=1, token_type="access")
    add_revoked_jti(jti)
    resp = auth_client.post(
        "/api/v1/chat",
        json={"message": "hi"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "token_revoked"


def test_health_is_unprotected(api_client: TestClient):
    resp = api_client.get("/health")
    assert resp.status_code == 200
