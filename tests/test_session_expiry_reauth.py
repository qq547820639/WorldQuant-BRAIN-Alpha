"""F1.5 — Session expiry → re-auth flow tests.

Spec ref: .trae/specs/overhaul-alpha-production-quality/spec.md
  "会话过期重认证" — Auth token expires (401 response) → system detects,
  clears session, prompts re-auth.

Verifies that:
  - A 401 response from the BRAIN API classifies as ErrorKind.login_expired.
  - AUTH_TOKEN_EXPIRED error_code classifies as ErrorKind.login_expired.
  - secure_credentials.resolve_credentials() re-resolves from env vars
    (simulating the re-auth flow after session clear).
  - ProductionHealthMonitor.check_login_session() flags an expired session.
  - web_errors.safe_error_payload() returns an actionable error with the
    login_expired kind and a /config recovery_url.
"""
from __future__ import annotations

import os
import time

import pytest

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.error_catalog import (
    ErrorKind,
    build_actionable_error,
    classify_exception,
)
from brain_alpha_ops.monitoring.production_health import ProductionHealthMonitor
from brain_alpha_ops.monitoring.unified_monitor import Severity
from brain_alpha_ops.secure_credentials import (
    CredentialBundle,
    resolve_credentials,
    validate_credential_envs,
)
from brain_alpha_ops.web.misc.web_errors import safe_error_message, safe_error_payload


# --------------------------------------------------------------------------- #
# classify_exception: 401 / AUTH_TOKEN_EXPIRED → login_expired
# --------------------------------------------------------------------------- #

def test_401_status_classifies_as_login_expired():
    """An HTTP 401 response classifies as ErrorKind.login_expired."""
    err = BrainAPIError("HTTP 401 Unauthorized", status_code=401)
    assert classify_exception(err) == ErrorKind.login_expired


def test_403_status_classifies_as_login_expired():
    """An HTTP 403 (forbidden) is treated as a session/auth failure too."""
    err = BrainAPIError("HTTP 403 Forbidden", status_code=403)
    assert classify_exception(err) == ErrorKind.login_expired


def test_auth_token_expired_error_code_classifies_as_login_expired():
    """A BRAIN error_code AUTH_TOKEN_EXPIRED classifies as login_expired
    regardless of the HTTP status code.
    """
    err = BrainAPIError(
        "token expired",
        status_code=400,
        error_code="AUTH_TOKEN_EXPIRED",
    )
    assert classify_exception(err) == ErrorKind.login_expired


def test_unauthorized_string_classifies_as_login_expired():
    """A bare 'unauthorized' string classifies as login_expired."""
    assert classify_exception("401 unauthorized") == ErrorKind.login_expired


def test_session_expired_string_classifies_as_login_expired():
    assert classify_exception("session_expired: please log in again") == ErrorKind.login_expired


# --------------------------------------------------------------------------- #
# secure_credentials: env-var re-resolution (re-auth flow)
# --------------------------------------------------------------------------- #

@pytest.fixture
def _clean_credential_env(monkeypatch):
    """Strip credential env vars so tests start from a clean state."""
    for var in ("BRAIN_USERNAME", "BRAIN_PASSWORD", "BRAIN_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    yield


def test_resolve_credentials_picks_up_env_vars_after_session_clear(_clean_credential_env, monkeypatch):
    """After a session expiry, the system clears the in-memory session and
    re-resolves credentials from the environment. This test verifies that
    resolve_credentials() picks up newly-set env vars on the next call.
    """
    # 1) No env vars → no credentials.
    bundle = resolve_credentials()
    assert bundle.has_credentials is False
    assert bundle.auth_method == "none"

    # 2) User re-authenticates by exporting env vars (re-auth flow).
    monkeypatch.setenv("BRAIN_USERNAME", "user@example.com")
    monkeypatch.setenv("BRAIN_PASSWORD", "fake_token_password")
    monkeypatch.setenv("BRAIN_TOKEN", "fake_token_value")

    bundle = resolve_credentials()
    assert bundle.has_credentials is True
    assert bundle.username == "user@example.com"
    assert bundle.password == "fake_token_password"
    assert bundle.token == "fake_token_value"
    # auth_method prefers token when both token and userpass are present.
    assert bundle.auth_method == "token"


def test_resolve_credentials_explicit_args_override_env(_clean_credential_env, monkeypatch):
    """Explicit args take precedence over env vars — used when the user
    enters credentials via the ConfigPanel after a session expiry.
    """
    monkeypatch.setenv("BRAIN_USERNAME", "env_user@example.com")
    monkeypatch.setenv("BRAIN_PASSWORD", "env_fake_password")

    bundle = resolve_credentials(
        username="explicit_user@example.com",
        password="explicit_fake_password",
    )
    assert bundle.username == "explicit_user@example.com"
    assert bundle.password == "explicit_fake_password"


def test_validate_credential_envs_reports_missing_after_clear(_clean_credential_env):
    """validate_credential_envs() returns the missing env var names — used
    by the re-auth flow to prompt the user.
    """
    missing = validate_credential_envs()
    assert "BRAIN_USERNAME" in missing
    assert "BRAIN_PASSWORD" in missing
    assert "BRAIN_TOKEN" in missing


def test_validate_credential_envs_passes_when_token_present(_clean_credential_env, monkeypatch):
    monkeypatch.setenv("BRAIN_TOKEN", "fake_token_value")
    assert validate_credential_envs() == []


def test_credential_bundle_masked_repr_does_not_leak_secrets(_clean_credential_env, monkeypatch):
    """The CredentialBundle.__repr__ must not leak the actual password/token."""
    monkeypatch.setenv("BRAIN_PASSWORD", "fake_token_password")
    monkeypatch.setenv("BRAIN_TOKEN", "fake_token_value")
    bundle = resolve_credentials()

    repr_text = repr(bundle)
    assert "fake_token_password" not in repr_text
    assert "fake_token_value" not in repr_text
    assert "CredentialBundle" in repr_text


# --------------------------------------------------------------------------- #
# ProductionHealthMonitor: session expiry detection
# --------------------------------------------------------------------------- #

def test_health_monitor_flags_expired_session():
    """An expired session (session_expiry in the past) is detected as DEGRADED."""
    monitor = ProductionHealthMonitor()
    auth_state = {
        "authenticated": True,
        "session_expiry": time.time() - 3600,  # expired 1 hour ago
        "consecutive_failures": 0,
    }
    check = monitor.check_login_session(auth_state)
    assert check.severity == Severity.DEGRADED
    assert "session token expired" in check.message
    assert "refresh authentication" in check.suggested_action


def test_health_monitor_flags_unauthenticated_session():
    """An unauthenticated session triggers a WARNING (prompt re-auth)."""
    monitor = ProductionHealthMonitor()
    check = monitor.check_login_session({"authenticated": False, "consecutive_failures": 0})
    assert check.severity == Severity.WARNING
    assert "not authenticated" in check.message
    assert "BRAIN_USERNAME" in check.suggested_action or "env" in check.suggested_action.lower()


def test_health_monitor_flags_auth_failure_loop():
    """Multiple consecutive auth failures trigger a DEGRADED state and
    a 'halt automated retries' action.
    """
    monitor = ProductionHealthMonitor()
    check = monitor.check_login_session(
        {"authenticated": False, "consecutive_failures": 10}
    )
    assert check.severity == Severity.DEGRADED
    assert "auth failure loop" in check.message
    assert "halt automated retries" in check.suggested_action


def test_health_monitor_ok_when_session_valid_and_not_expiring_soon():
    monitor = ProductionHealthMonitor()
    check = monitor.check_login_session(
        {
            "authenticated": True,
            "session_expiry": time.time() + 7200,  # 2 hours from now
            "consecutive_failures": 0,
        }
    )
    assert check.severity == Severity.OK


# --------------------------------------------------------------------------- #
# web_errors: safe_error_payload → login_expired actionable error
# --------------------------------------------------------------------------- #

def test_safe_error_message_for_401_returns_auth_message():
    """safe_error_message() returns a Chinese auth-failure message for 401."""
    err = BrainAPIError("HTTP 401 Unauthorized", status_code=401)
    message = safe_error_message(err)
    assert "认证失败" in message or "登录" in message or "凭据" in message


def test_safe_error_message_for_auth_token_expired_returns_reauth_hint():
    """AUTH_TOKEN_EXPIRED returns a re-auth prompt."""
    err = BrainAPIError(
        "token expired",
        status_code=400,
        error_code="AUTH_TOKEN_EXPIRED",
    )
    message = safe_error_message(err, error_code="AUTH_TOKEN_EXPIRED")
    assert "登录已过期" in message or "重新输入凭据" in message


def test_safe_error_payload_classifies_401_as_login_expired():
    """safe_error_payload() builds an actionable error whose 'actionable'
    sub-payload has kind=login_expired and a /config recovery_url.
    """
    err = BrainAPIError("HTTP 401 Unauthorized", status_code=401)
    payload = safe_error_payload(err, error_code="AUTH_TOKEN_EXPIRED")

    assert payload["ok"] is False
    actionable = payload["actionable"]
    assert actionable["kind"] == ErrorKind.login_expired.value
    assert actionable["recovery_url"] == "/config"
    assert actionable["suggested_action"]
    assert actionable["cause"]


def test_login_expired_actionable_payload_carries_recovery_entry():
    """The login_expired actionable error payload includes a recovery_url
    so the frontend can render a clickable 'reconnect' entry.
    """
    payload = build_actionable_error(ErrorKind.login_expired)
    assert payload["kind"] == "login_expired"
    assert payload["recovery_url"] == "/config"
    assert payload["recovery_action_id"] == "reconnect_session"
    assert "登录" in payload["cause"] or "凭据" in payload["cause"]


# --------------------------------------------------------------------------- #
# End-to-end: 401 → classify → actionable payload → recovery entry
# --------------------------------------------------------------------------- #

def test_full_reauth_flow_on_401():
    """End-to-end: a 401 response is classified as login_expired, the
    actionable payload carries a /config recovery_url, and the user is
    prompted to set BRAIN_USERNAME/BRAIN_PASSWORD env vars.
    """
    err = BrainAPIError("HTTP 401 Unauthorized", status_code=401)

    # 1) Classify.
    kind = classify_exception(err)
    assert kind == ErrorKind.login_expired

    # 2) Build actionable payload.
    payload = build_actionable_error(kind, context={"status_code": 401})
    assert payload["recovery_url"] == "/config"
    assert payload["severity"] == "error"

    # 3) Web error payload includes the actionable payload.
    web_payload = safe_error_payload(err, error_code="AUTH_INVALID")
    assert web_payload["actionable"]["kind"] == "login_expired"
    assert web_payload["actionable"]["recovery_url"] == "/config"
