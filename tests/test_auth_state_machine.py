"""Unit tests for auth_state_machine.py — AuthStateMachine.

Covers normal auth flow (cookie → bearer → basic), failure fallback
(bearer-401 → cookie), auth-refresh lifecycle, token save/restore,
concurrency safety, and edge cases (no strategies available).
"""

from __future__ import annotations

import http.cookiejar
import threading
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from brain_alpha_ops.brain_api.auth_state_machine import (
    AuthAction,
    AuthStateMachine,
)
from brain_alpha_ops.brain_api.base import BrainAPIError


# ============================================================================
# Helpers
# ============================================================================


@dataclass
class _FakeCredentials:
    """Minimal credential bundle for testing."""
    token: str = ""
    username: str = ""
    password: str = ""


def _make_sm(
    *,
    token: str = "",
    username: str = "",
    password: str = "",
    cookie_count: int = 0,
    prefer_cookie: bool = False,
    authenticator=None,
) -> tuple[AuthStateMachine, _FakeCredentials, threading.RLock, http.cookiejar.CookieJar, dict]:
    """Factory: create an AuthStateMachine with controlled mutable state.

    Returns:
        (sm, creds, lock, jar, state_proxy) — state_proxy is a dict that
        tracks ``prefer_cookie`` so tests can inspect / modify it.
    """
    creds = _FakeCredentials(token=token, username=username, password=password)
    lock = threading.RLock()
    jar = http.cookiejar.CookieJar()
    for i in range(cookie_count):
        cookie = http.cookiejar.Cookie(
            version=0,
            name=f"session_{i}",
            value=f"val_{i}",
            port=None,
            port_specified=False,
            domain="brain.worldquant.com",
            domain_specified=True,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=True,
            expires=None,
            discard=False,
            comment=None,
            comment_url=None,
            rest={"HttpOnly": None},
        )
        jar.set_cookie(cookie)

    prefer_state: dict[str, bool] = {"prefer_cookie": prefer_cookie}
    auth_calls: list[tuple] = []

    def mock_authenticator():
        auth_calls.append(("authenticate",))
        # Simulate setting a token on success
        creds.token = "refreshed-token"
        return {"token": creds.token}

    sm = AuthStateMachine(
        token_getter=lambda: creds.token,
        token_setter=lambda v: setattr(creds, "token", v or ""),
        username_getter=lambda: creds.username,
        password_getter=lambda: creds.password,
        cookie_jar_getter=lambda: jar,
        prefer_cookie_getter=lambda: prefer_state["prefer_cookie"],
        prefer_cookie_setter=lambda v: prefer_state.__setitem__("prefer_cookie", bool(v)),
        lock=lock,
        authenticator=authenticator if authenticator is not None else mock_authenticator,
        authentication_path="/auth/login",
    )
    return sm, creds, lock, jar, prefer_state


# ============================================================================
# AuthAction enum
# ============================================================================


class TestAuthAction:
    """Verify AuthAction enum values."""

    def test_retry_value(self):
        assert AuthAction.RETRY.value == "retry"

    def test_raise_value(self):
        assert AuthAction.RAISE.value == "raise"

    def test_retry_is_not_raise(self):
        assert AuthAction.RETRY != AuthAction.RAISE


# ============================================================================
# authenticate() — strategy selection
# ============================================================================


class TestAuthenticateStrategySelection:
    """Tests for ``authenticate()`` choosing the right strategy."""

    def test_bearer_selected_when_token_present(self):
        """With a token and no cookie preference, bearer should be chosen."""
        sm, creds, _, _, _ = _make_sm(token="tok-xyz")
        headers: dict[str, str] = {}
        mode = sm.authenticate(headers)
        assert mode == "bearer"
        assert headers["Authorization"] == "Bearer tok-xyz"

    def test_cookie_preferred_when_available(self):
        """When prefer_cookie=True and cookies exist, cookie should be chosen."""
        sm, creds, _, _, _ = _make_sm(token="tok-xyz", cookie_count=1, prefer_cookie=True)
        headers: dict[str, str] = {}
        mode = sm.authenticate(headers)
        assert mode == "cookie"
        # CookieAuth doesn't touch headers
        assert "Authorization" not in headers

    def test_cookie_ignored_when_not_preferred(self):
        """Even with cookies present, if not preferred, fall through to bearer."""
        sm, creds, _, _, _ = _make_sm(token="tok-xyz", cookie_count=2, prefer_cookie=False)
        headers: dict[str, str] = {}
        mode = sm.authenticate(headers)
        assert mode == "bearer"

    def test_cookie_preferred_but_no_cookies_falls_to_bearer(self):
        """prefer_cookie=True but jar empty → should fall through to bearer."""
        sm, creds, _, _, _ = _make_sm(token="tok-xyz", cookie_count=0, prefer_cookie=True)
        headers: dict[str, str] = {}
        mode = sm.authenticate(headers)
        assert mode == "bearer"

    def test_falls_to_basic_when_no_token(self):
        """No token but username/password available → basic auth."""
        sm, creds, _, _, _ = _make_sm(token="", username="alice", password="secret")
        headers: dict[str, str] = {}
        mode = sm.authenticate(headers)
        assert mode == "basic"
        assert headers["Authorization"].startswith("Basic ")

    def test_skip_auto_auth_skips_bearer_and_basic(self):
        """skip_auto_auth=True should skip bearer and basic, return 'none'."""
        sm, creds, _, _, _ = _make_sm(token="tok", username="u", password="p")
        headers: dict[str, str] = {}
        mode = sm.authenticate(headers, skip_auto_auth=True)
        assert mode == "none"
        assert "Authorization" not in headers

    def test_skip_auto_auth_still_allows_cookie(self):
        """skip_auto_auth=True still allows cookie when preferred."""
        sm, creds, _, jar, prefer = _make_sm(
            token="tok", username="u", password="p", cookie_count=1, prefer_cookie=True
        )
        headers: dict[str, str] = {}
        mode = sm.authenticate(headers, skip_auto_auth=True)
        assert mode == "cookie"

    def test_no_credentials_returns_none(self):
        """When nothing is available, authenticate returns 'none'."""
        sm, creds, _, _, _ = _make_sm(token="", username="", password="")
        headers: dict[str, str] = {}
        mode = sm.authenticate(headers)
        assert mode == "none"
        assert "Authorization" not in headers

    def test_is_authenticated_with_token(self):
        """is_authenticated should be True when a token is present."""
        sm, _, _, _, _ = _make_sm(token="tok")
        assert sm.is_authenticated

    def test_is_authenticated_with_basic(self):
        """is_authenticated should be True when username/password available."""
        sm, _, _, _, _ = _make_sm(token="", username="u", password="p")
        assert sm.is_authenticated

    def test_is_authenticated_with_cookie(self):
        """is_authenticated should be True when cookies exist."""
        sm, _, _, _, _ = _make_sm(token="", cookie_count=1)
        assert sm.is_authenticated

    def test_is_authenticated_none(self):
        """is_authenticated should be False when nothing available."""
        sm, _, _, _, _ = _make_sm(token="", username="", password="")
        assert not sm.is_authenticated


# ============================================================================
# on_auth_failure — bearer 401 → cookie fallback
# ============================================================================


class TestAuthFailureBearerToCookie:
    """Tests for bearer-401 triggering cookie fallback."""

    def test_bearer_401_falls_back_to_cookie(self):
        """Bearer 401 with cookies available → RETRY, prefer_cookie set."""
        sm, creds, _, jar, prefer = _make_sm(token="old-tok", cookie_count=1)
        assert prefer["prefer_cookie"] is False  # sanity

        action = sm.on_auth_failure(
            401, "bearer", has_more_attempts=True, is_auth_retry_allowed=True
        )
        assert action == AuthAction.RETRY
        assert prefer["prefer_cookie"] is True
        # Token should be saved and cleared
        assert creds.token == ""

    def test_bearer_401_saves_token(self):
        """Bearer 401 should save the current token before clearing."""
        sm, creds, _, jar, prefer = _make_sm(token="my-precious-token", cookie_count=1)

        sm.on_auth_failure(401, "bearer", has_more_attempts=True, is_auth_retry_allowed=True)
        # Token should be saved in internal state
        sm.restore_token()
        assert creds.token == "my-precious-token"

    def test_bearer_401_no_cookies_still_retries(self):
        """Bearer 401 with no cookies still returns RETRY — the next
        authenticate() call can fall through to basic auth if available."""
        sm, creds, _, _, _ = _make_sm(token="tok", cookie_count=0, username="u", password="p")
        action = sm.on_auth_failure(
            401, "bearer", has_more_attempts=True, is_auth_retry_allowed=True
        )
        # Always RETRY — token is saved & cleared, caller retries and
        # authenticate() will pick basic auth on the next iteration.
        assert action == AuthAction.RETRY
        # Token was saved (cleared from creds)
        assert creds.token == ""
        # Verify token can be restored
        sm.restore_token()
        assert creds.token == "tok"

    def test_bearer_401_no_more_attempts(self):
        """Bearer 401 with has_more_attempts=False → RAISE immediately."""
        sm, creds, _, _, _ = _make_sm(token="tok", cookie_count=1)
        action = sm.on_auth_failure(
            401, "bearer", has_more_attempts=False, is_auth_retry_allowed=True
        )
        assert action == AuthAction.RAISE


# ============================================================================
# on_auth_failure — auth refresh
# ============================================================================


class TestAuthFailureRefresh:
    """Tests for 401/403 triggering auth refresh."""

    def test_401_triggers_auth_refresh(self):
        """401 with auth_retry_allowed → calls authenticator → RETRY."""
        auth_calls = []

        def mock_auth():
            auth_calls.append(1)
            return {"token": "new-tok"}

        sm, creds, _, jar, prefer = _make_sm(
            token="old", username="u", password="p", cookie_count=1, authenticator=mock_auth
        )

        action = sm.on_auth_failure(
            401, "basic", has_more_attempts=True, is_auth_retry_allowed=True
        )
        assert action == AuthAction.RETRY
        assert len(auth_calls) == 1
        # After successful auth refresh + cookie available, prefer_cookie set
        assert prefer["prefer_cookie"] is True

    def test_403_triggers_auth_refresh(self):
        """403 should also trigger auth refresh."""
        auth_calls = []

        def mock_auth():
            auth_calls.append(1)

        sm, _, _, jar, _ = _make_sm(
            token="old", username="u", password="p", cookie_count=1, authenticator=mock_auth
        )

        action = sm.on_auth_failure(
            403, "basic", has_more_attempts=True, is_auth_retry_allowed=True
        )
        assert action == AuthAction.RETRY
        assert len(auth_calls) == 1

    def test_auth_refresh_only_once(self):
        """auth_refresh_attempted flag prevents multiple refresh attempts."""
        auth_calls = []

        def mock_auth():
            auth_calls.append(1)

        sm, _, _, jar, _ = _make_sm(
            token="old", username="u", password="p", cookie_count=1, authenticator=mock_auth
        )

        # First call → refresh happens
        action1 = sm.on_auth_failure(
            401, "basic", has_more_attempts=True, is_auth_retry_allowed=True
        )
        assert action1 == AuthAction.RETRY
        assert len(auth_calls) == 1

        # Second call → no refresh, should RAISE (after retries exhausted by caller)
        action2 = sm.on_auth_failure(
            401, "basic", has_more_attempts=True, is_auth_retry_allowed=True
        )
        assert action2 == AuthAction.RAISE
        assert len(auth_calls) == 1  # no additional call

    def test_auth_refresh_returns_raise_on_brain_api_error(self):
        """When authenticator raises BrainAPIError, should still be handled gracefully."""

        def mock_auth():
            raise BrainAPIError("auth failed", error_code="AUTH_INVALID")

        sm, _, _, _, _ = _make_sm(
            token="old", username="u", password="p", cookie_count=0, authenticator=mock_auth
        )

        action = sm.on_auth_failure(
            401, "basic", has_more_attempts=True, is_auth_retry_allowed=True
        )
        # Refresh failed, no cookie available → RAISE
        assert action == AuthAction.RAISE

    def test_auth_refresh_not_allowed(self):
        """is_auth_retry_allowed=False → no refresh → RAISE."""
        sm, _, _, _, _ = _make_sm(token="old", username="u", password="p")

        action = sm.on_auth_failure(
            401, "basic", has_more_attempts=True, is_auth_retry_allowed=False
        )
        assert action == AuthAction.RAISE

    def test_429_does_not_trigger_auth_refresh(self):
        """429 (rate limit) should not trigger auth refresh."""
        sm, _, _, _, _ = _make_sm(token="old", username="u", password="p")

        action = sm.on_auth_failure(
            429, "bearer", has_more_attempts=True, is_auth_retry_allowed=True
        )
        assert action == AuthAction.RAISE


# ============================================================================
# on_success() — token restoration
# ============================================================================


class TestOnSuccess:
    """Tests for token restoration after successful request."""

    def test_restores_saved_token(self):
        """on_success should restore a previously saved token."""
        sm, creds, _, jar, prefer = _make_sm(token="original-tok", cookie_count=1)

        # Simulate bearer-401 → token saved, cleared
        sm.on_auth_failure(401, "bearer", has_more_attempts=True, is_auth_retry_allowed=True)
        assert creds.token == ""  # cleared
        assert prefer["prefer_cookie"] is True

        # After successful cookie request
        sm.on_success()
        assert creds.token == "original-tok"

    def test_on_success_noop_when_no_saved_token(self):
        """on_success is a no-op when no token was saved."""
        sm, creds, _, _, _ = _make_sm(token="current-tok")
        sm.on_success()
        assert creds.token == "current-tok"  # unchanged

    def test_on_success_noop_when_token_already_present(self):
        """on_success should not overwrite a token that's already been restored."""
        sm, creds, _, jar, prefer = _make_sm(token="orig-tok", cookie_count=1)

        sm.on_auth_failure(401, "bearer", has_more_attempts=True, is_auth_retry_allowed=True)
        assert creds.token == ""

        # Manually set a different token first
        creds.token = "newer-tok"
        sm.on_success()
        # Should NOT overwrite newer-tok with orig-tok
        assert creds.token == "newer-tok"


# ============================================================================
# restore_token() — explicit token restore
# ============================================================================


class TestRestoreToken:
    """Tests for explicit restore_token()."""

    def test_restore_token_from_bearer_fallback(self):
        """After bearer-401, restore_token brings back the saved token."""
        sm, creds, _, jar, _ = _make_sm(token="precious-token", cookie_count=1)

        sm.on_auth_failure(401, "bearer", has_more_attempts=True, is_auth_retry_allowed=True)
        assert creds.token == ""

        sm.restore_token()
        assert creds.token == "precious-token"

    def test_restore_token_noop_without_saved_token(self):
        """restore_token is a no-op when nothing was saved."""
        sm, creds, _, _, _ = _make_sm(token="current")
        sm.restore_token()
        assert creds.token == "current"

    def test_restore_token_noop_when_token_already_set(self):
        """restore_token should not overwrite a token that's already present."""
        sm, creds, _, jar, _ = _make_sm(token="orig", cookie_count=1)

        sm.on_auth_failure(401, "bearer", has_more_attempts=True, is_auth_retry_allowed=True)
        assert creds.token == ""

        creds.token = "new-token"
        sm.restore_token()
        assert creds.token == "new-token"  # not overwritten


# ============================================================================
# current_strategy property
# ============================================================================


class TestCurrentStrategy:
    """Tests for current_strategy property."""

    def test_current_strategy_bearer(self):
        """current_strategy should return BearerAuth when token is available."""
        sm, _, _, _, _ = _make_sm(token="tok")
        from brain_alpha_ops.brain_api.auth_strategy import BearerAuth
        assert isinstance(sm.current_strategy, BearerAuth)

    def test_current_strategy_cookie_when_preferred(self):
        """current_strategy should return CookieAuth when cookie is preferred."""
        sm, _, _, _, _ = _make_sm(token="tok", cookie_count=1, prefer_cookie=True)
        from brain_alpha_ops.brain_api.auth_strategy import CookieAuth
        assert isinstance(sm.current_strategy, CookieAuth)

    def test_current_strategy_basic(self):
        """current_strategy should return BasicAuth when only user/pass available."""
        sm, _, _, _, _ = _make_sm(token="", username="u", password="p")
        from brain_alpha_ops.brain_api.auth_strategy import BasicAuth
        assert isinstance(sm.current_strategy, BasicAuth)

    def test_current_strategy_fallback_cookie(self):
        """current_strategy falls back to CookieAuth when nothing else is available."""
        sm, _, _, _, _ = _make_sm(token="", username="", password="")
        from brain_alpha_ops.brain_api.auth_strategy import CookieAuth
        assert isinstance(sm.current_strategy, CookieAuth)


# ============================================================================
# Concurrency safety
# ============================================================================


class TestConcurrencySafety:
    """Verify that AuthStateMachine is thread-safe under contention."""

    def test_concurrent_authenticate(self):
        """Multiple threads calling authenticate should not corrupt state."""
        sm, creds, lock, _, _ = _make_sm(token="shared-tok")
        errors: list[Exception] = []
        results: list[str] = []

        def worker():
            try:
                headers: dict[str, str] = {}
                mode = sm.authenticate(headers)
                results.append(mode)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r == "bearer" for r in results)

    def test_concurrent_auth_failure_and_restore(self):
        """Concurrent on_auth_failure + restore_token should not race."""
        sm, creds, lock, jar, prefer = _make_sm(token="concurrent-tok", cookie_count=1)
        errors: list[Exception] = []

        def fail_worker():
            try:
                sm.on_auth_failure(401, "bearer", has_more_attempts=True, is_auth_retry_allowed=True)
            except Exception as e:
                errors.append(e)

        def restore_worker():
            try:
                sm.restore_token()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=fail_worker) for _ in range(5)] + [
            threading.Thread(target=restore_worker) for _ in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ============================================================================
# Edge cases
# ============================================================================


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_authenticate_with_empty_headers_dict(self):
        """authenticate with empty dict should populate it."""
        sm, _, _, _, _ = _make_sm(token="tok")
        headers: dict[str, str] = {}
        sm.authenticate(headers)
        assert "Authorization" in headers

    def test_authenticate_preserves_existing_headers(self):
        """authenticate should not remove non-auth headers."""
        sm, _, _, _, _ = _make_sm(token="tok")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        sm.authenticate(headers)
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"
        assert "Authorization" in headers

    def test_on_auth_failure_non_401_non_403(self):
        """Non-auth HTTP errors (e.g. 500) should return RAISE."""
        sm, _, _, _, _ = _make_sm(token="tok")
        action = sm.on_auth_failure(
            500, "bearer", has_more_attempts=True, is_auth_retry_allowed=True
        )
        assert action == AuthAction.RAISE

    def test_on_auth_failure_without_has_more_attempts(self):
        """Without retry attempts, always RAISE."""
        sm, _, _, _, _ = _make_sm(token="tok")
        action = sm.on_auth_failure(
            401, "bearer", has_more_attempts=False, is_auth_retry_allowed=True
        )
        assert action == AuthAction.RAISE

    def test_token_state_consistency_after_multiple_failures(self):
        """After multiple auth failures, token state should remain consistent."""
        sm, creds, _, jar, prefer = _make_sm(token="original", username="u", password="p", cookie_count=1)

        # First: bearer 401 → fallback to cookie
        action1 = sm.on_auth_failure(401, "bearer", has_more_attempts=True, is_auth_retry_allowed=True)
        assert action1 == AuthAction.RETRY
        assert creds.token == ""  # saved, cleared

        # Simulate success on cookie request → restore token
        sm.on_success()
        assert creds.token == "original"

        # Reset prefer_cookie for next test
        prefer["prefer_cookie"] = False

        # Second: bearer 401 again
        action2 = sm.on_auth_failure(401, "bearer", has_more_attempts=True, is_auth_retry_allowed=True)
        assert action2 == AuthAction.RETRY

        # Restore
        sm.restore_token()
        assert creds.token == "original"
