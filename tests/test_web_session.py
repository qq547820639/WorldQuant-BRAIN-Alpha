import pytest

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

