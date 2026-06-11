import pytest
import json

from brain_alpha_ops import web_session


def test_session_policy_facade_tracks_ttl_multiple_and_secure_cookie():
    original_ttl = web_session.session_ttl_seconds()
    original_multiple = web_session.session_allow_multiple()
    original_secure = web_session.SESSION_MANAGER.secure_cookies
    try:
        web_session.configure_session_policy(30, False, True)

        assert web_session.session_ttl_seconds() == 60
        assert web_session.session_allow_multiple() is False
        session_id, csrf = web_session.create_session()
        assert web_session.validate_session(session_id, csrf) is True
        assert "Secure" in web_session.session_cookie_header(session_id)
    finally:
        web_session.configure_session_policy(original_ttl, original_multiple, original_secure)
        web_session.SESSION_MANAGER.sessions.clear()


def test_brain_connection_status_is_server_side_and_sanitized():
    web_session.SESSION_MANAGER.sessions.clear()
    session_id, csrf_token = web_session.create_session()
    try:
        initial = web_session.session_status(session_id)
        assert initial["authenticated"] is True
        assert initial["connected"] is False

        verified = web_session.mark_brain_connection_verified(
            session_id,
            {"ok": True, "environment": "production", "auth": "basic"},
            {"username": "reader@example.test", "password": "secret-password"},
        )
        encoded = json.dumps(verified)
        assert verified["connected"] is True
        assert verified["brain_connection_verified"] is True
        assert verified["credential_source"] == "page"
        assert verified["session_credentials_available"] is True
        assert verified["environment"] == "production"
        assert verified["auth_mode"] == "basic"
        assert "reader@example.test" not in encoded
        assert "secret-password" not in encoded
        assert web_session.validate_session(session_id, csrf_token) is True
        assert web_session.brain_session_credentials(session_id) == {
            "username": "reader@example.test",
            "password": "secret-password",
        }
        assert web_session.payload_with_brain_session_credentials(
            session_id,
            {"syncRange": "all"},
        ) == {
            "syncRange": "all",
            "username": "reader@example.test",
            "password": "secret-password",
        }
        assert web_session.payload_with_brain_session_credentials(
            session_id,
            {"syncRange": "all", "token": "current-page-token"},
        ) == {"syncRange": "all", "token": "current-page-token"}

        cleared = web_session.clear_brain_connection_verified(session_id)
        assert cleared["connected"] is False
        assert cleared["brain_connection_verified"] is False
        assert cleared["session_credentials_available"] is False
        assert web_session.brain_session_credentials(session_id) == {}
    finally:
        web_session.SESSION_MANAGER.sessions.clear()


def test_mixed_page_credentials_store_complete_basic_pair_before_token():
    web_session.SESSION_MANAGER.sessions.clear()
    session_id, _csrf_token = web_session.create_session()
    try:
        verified = web_session.mark_brain_connection_verified(
            session_id,
            {"ok": True, "environment": "production", "auth": "basic"},
            {
                "username": "basic-user@example.test",
                "password": "basic-password",
                "token": "stale-token",
            },
        )

        assert verified["connected"] is True
        assert verified["session_credentials_available"] is True
        assert web_session.brain_session_credentials(session_id) == {
            "username": "basic-user@example.test",
            "password": "basic-password",
        }
        assert web_session.payload_with_brain_session_credentials(
            session_id,
            {"syncRange": "all"},
        ) == {
            "syncRange": "all",
            "username": "basic-user@example.test",
            "password": "basic-password",
        }
    finally:
        web_session.SESSION_MANAGER.sessions.clear()


def test_remote_policy_requires_env_and_validates_admin_header(monkeypatch):
    env_name = "BRAIN_ALPHA_OPS_TEST_WEB_SESSION_TOKEN"
    monkeypatch.delenv(env_name, raising=False)
    web_session.set_remote_policy(allow_remote=True, admin_token_env=env_name)

    with pytest.raises(ValueError, match=env_name):
        web_session.require_remote_admin_token()

    monkeypatch.setenv(env_name, "secret-token")

    web_session.require_remote_admin_token()
    assert web_session.remote_admin_required() is True
    assert web_session.has_valid_admin_token({"Authorization": "Bearer secret-token"}) is True
    assert web_session.has_valid_admin_token({"Authorization": "Bearer wrong-token"}) is False
    assert web_session.is_allowed_request(
        host_header="console.example.test:8765",
        origin_header="http://console.example.test:8765",
    )
    assert not web_session.is_allowed_request(
        host_header="console.example.test:8765",
        origin_header="http://evil.example:8765",
    )

    web_session.set_remote_policy(allow_remote=False, admin_token_env=web_session.DEFAULT_ADMIN_TOKEN_ENV)


def test_expiring_session_drops_brain_session_credentials():
    web_session.SESSION_MANAGER.sessions.clear()
    session_id, _csrf_token = web_session.create_session()
    try:
        assert web_session.store_brain_session_credentials(
            session_id,
            {"token": "session-token"},
        ) is True
        assert web_session.brain_session_credentials(session_id) == {"token": "session-token"}
        web_session.expire_session(session_id)
        assert web_session.brain_session_credentials(session_id) == {}
        assert web_session.session_status(session_id)["session_credentials_available"] is False
    finally:
        web_session.SESSION_MANAGER.sessions.clear()


def test_brain_session_credentials_do_not_cross_session_ids():
    web_session.SESSION_MANAGER.sessions.clear()
    first_session, _first_csrf = web_session.create_session()
    second_session, _second_csrf = web_session.create_session()
    try:
        assert web_session.store_brain_session_credentials(
            first_session,
            {"username": "first@example.test", "password": "first-password"},
        ) is True

        assert web_session.brain_session_credentials(second_session) == {}
        assert web_session.payload_with_brain_session_credentials(
            second_session,
            {"syncRange": "all"},
        ) == {"syncRange": "all"}
        assert web_session.session_status(second_session)["session_credentials_available"] is False

        web_session.expire_session(first_session)
        assert web_session.brain_session_credentials(first_session) == {}
        assert web_session.brain_session_credentials(second_session) == {}
    finally:
        web_session.SESSION_MANAGER.sessions.clear()
