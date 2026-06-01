"""
Unit tests for the auth module (JWT + store).

JWT tests are pure — no I/O. Store tests patch settings to inject admin
credentials and use the in-memory revocation set (cleared per-test via the
autouse fixture in conftest).
"""
from unittest.mock import patch

import jwt
import pytest

import travel_agent.auth.store as store
from travel_agent.auth.jwt import create_token, decode_token, make_jti
from travel_agent.auth.store import add_revoked_jti, is_jti_revoked, verify_credentials


# ── JWT unit tests ────────────────────────────────────────────────────────────

def test_make_jti_returns_unique_values():
    assert make_jti() != make_jti()


def test_create_access_token_payload():
    token, jti, exp = create_token(user_id=1, token_type="access")
    payload = decode_token(token)

    assert payload["userId"] == 1
    assert payload["type"] == "access"
    assert payload["jti"] == jti
    assert payload["exp"] > payload["iat"]
    # Access token should expire ~1 hour from now (allow ±5s for test timing)
    assert abs((payload["exp"] - payload["iat"]) - 3600) < 5


def test_create_refresh_token_payload():
    token, jti, exp = create_token(user_id=1, token_type="refresh")
    payload = decode_token(token)

    assert payload["type"] == "refresh"
    # Refresh token should expire ~30 days from now
    assert abs((payload["exp"] - payload["iat"]) - 30 * 86400) < 5


def test_create_token_rejects_unknown_type():
    with pytest.raises(ValueError, match="Invalid token_type"):
        create_token(user_id=1, token_type="admin")


def test_decode_token_raises_on_expired(monkeypatch):
    # Create a token then travel time forward past its expiry
    token, _, _ = create_token(user_id=1, token_type="access")

    # Decode with a manually adjusted 'now' by patching jwt.decode to use leeway=0
    # Simpler: create a token with exp in the past by monkeypatching time
    import travel_agent.auth.jwt as jwt_module
    from datetime import UTC, datetime, timedelta

    original_now = datetime.now

    def fake_now(tz=None):
        # Return a time 2 hours in the past so the token appears expired
        return original_now(UTC) - timedelta(hours=2)

    monkeypatch.setattr("travel_agent.auth.jwt.datetime", type("dt", (), {
        "now": staticmethod(fake_now),
    }))

    past_token, _, _ = create_token(user_id=1, token_type="access")

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(past_token)


def test_decode_token_raises_on_bad_signature():
    token, _, _ = create_token(user_id=1, token_type="access")
    tampered = token[:-4] + "xxxx"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(tampered)


# ── Store unit tests ──────────────────────────────────────────────────────────

@pytest.fixture
def admin_creds():
    """Inject known admin credentials via patched settings."""
    with patch("travel_agent.auth.store.settings") as mock_settings:
        mock_settings.admin_username = "test"
        mock_settings.admin_password = "test"
        yield


def test_verify_credentials_valid(admin_creds):
    user = verify_credentials("test", "test")
    assert user is not None
    assert user["id"] == 1
    assert user["username"] == "test"


def test_verify_credentials_wrong_password(admin_creds):
    assert verify_credentials("test", "wrong") is None


def test_verify_credentials_unknown_user(admin_creds):
    assert verify_credentials("nobody", "test") is None


def test_is_jti_revoked_false_when_clean():
    assert is_jti_revoked("some-jti-abc") is False


def test_add_and_check_revoked_jti():
    jti = "test-jti-12345"
    assert is_jti_revoked(jti) is False
    add_revoked_jti(jti)
    assert is_jti_revoked(jti) is True


def test_add_revoked_jti_is_idempotent():
    jti = "idempotent-jti"
    add_revoked_jti(jti)
    add_revoked_jti(jti)  # second call should not duplicate
    assert sum(1 for x in store._revoked_jtis if x == jti) == 1
