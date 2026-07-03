"""Unit tests for auth_strategy.py — AuthStrategy Protocol + 3 concrete strategies.

Covers CookieAuth, BearerAuth, BasicAuth behaviour including availability
checks, header construction, and structural protocol conformance.
"""

from __future__ import annotations

import base64
import http.cookiejar

import pytest

from brain_alpha_ops.brain_api.auth_strategy import (
    AuthStrategy,
    BasicAuth,
    BearerAuth,
    CookieAuth,
)


# ============================================================================
# AuthStrategy Protocol
# ============================================================================


class TestAuthStrategyProtocol:
    """Verify that AuthStrategy works as a runtime-checkable Protocol."""

    def test_cookie_auth_is_auth_strategy(self):
        """CookieAuth should satisfy the AuthStrategy protocol."""
        jar = http.cookiejar.CookieJar()
        ca = CookieAuth(jar)
        assert isinstance(ca, AuthStrategy)

    def test_bearer_auth_is_auth_strategy(self):
        """BearerAuth should satisfy the AuthStrategy protocol."""
        ba = BearerAuth(lambda: "my-token")
        assert isinstance(ba, AuthStrategy)

    def test_basic_auth_is_auth_strategy(self):
        """BasicAuth should satisfy the AuthStrategy protocol."""
        bc = BasicAuth(lambda: "user", lambda: "pass")
        assert isinstance(bc, AuthStrategy)

    def test_non_auth_strategy_fails_check(self):
        """A plain object without apply/is_available should NOT be an AuthStrategy."""

        class NotAuth:
            pass

        assert not isinstance(NotAuth(), AuthStrategy)

    def test_partial_implementation_fails(self):
        """An object with only apply (no is_available) should NOT pass protocol check."""

        class Partial:
            def apply(self, headers):
                return "foo"

        # Protocol runtime_checkable requires BOTH apply AND is_available
        assert not isinstance(Partial(), AuthStrategy)


# ============================================================================
# CookieAuth
# ============================================================================


class TestCookieAuth:
    """Tests for CookieAuth strategy."""

    def test_mode_is_cookie(self):
        """CookieAuth should return 'cookie' mode."""
        ca = CookieAuth(http.cookiejar.CookieJar())
        assert ca.apply({}) == "cookie"

    def test_apply_is_noop(self):
        """CookieAuth.apply should not modify headers."""
        jar = http.cookiejar.CookieJar()
        ca = CookieAuth(jar)
        headers: dict[str, str] = {"X-Custom": "val"}
        result = ca.apply(headers)
        assert result == "cookie"
        assert headers == {"X-Custom": "val"}  # no Authorization added

    def test_is_available_empty_jar(self):
        """Empty cookie jar → is_available returns False."""
        jar = http.cookiejar.CookieJar()
        ca = CookieAuth(jar)
        assert not ca.is_available()

    def test_is_available_with_cookies(self):
        """Cookie jar with cookies → is_available returns True."""
        jar = http.cookiejar.CookieJar()
        cookie = http.cookiejar.Cookie(
            version=0,
            name="sessionid",
            value="abc123",
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
        ca = CookieAuth(jar)
        assert ca.is_available()


# ============================================================================
# BearerAuth
# ============================================================================


class TestBearerAuth:
    """Tests for BearerAuth strategy."""

    def test_mode_is_bearer(self):
        """BearerAuth should return 'bearer' mode."""
        ba = BearerAuth(lambda: "tok123")
        assert ba.apply({}) == "bearer"

    def test_sets_authorization_header(self):
        """BearerAuth.apply must set Authorization: Bearer <token>."""
        ba = BearerAuth(lambda: "tok-abc-123")
        headers: dict[str, str] = {}
        ba.apply(headers)
        assert headers["Authorization"] == "Bearer tok-abc-123"

    def test_overwrites_existing_authorization(self):
        """BearerAuth should overwrite any existing Authorization header."""
        ba = BearerAuth(lambda: "new-token")
        headers = {"Authorization": "Old-Value"}
        ba.apply(headers)
        assert headers["Authorization"] == "Bearer new-token"

    def test_is_available_with_token(self):
        """Non-empty token → is_available returns True."""
        ba = BearerAuth(lambda: "valid-token")
        assert ba.is_available()

    def test_is_available_empty_token(self):
        """Empty token → is_available returns False."""
        ba = BearerAuth(lambda: "")
        assert not ba.is_available()

    def test_is_available_none_token(self):
        """None/NULL token → is_available returns False."""
        ba = BearerAuth(lambda: None)
        assert not ba.is_available()

    def test_token_getter_called_each_time(self):
        """The token getter is called on every apply/is_available."""
        call_count = 0

        def counter_getter():
            nonlocal call_count
            call_count += 1
            return f"token-{call_count}"

        ba = BearerAuth(counter_getter)
        assert ba.is_available()  # call 1
        assert call_count == 1
        headers: dict[str, str] = {}
        ba.apply(headers)  # call 2
        assert call_count == 2
        assert headers["Authorization"] == "Bearer token-2"


# ============================================================================
# BasicAuth
# ============================================================================


class TestBasicAuth:
    """Tests for BasicAuth strategy."""

    def test_mode_is_basic(self):
        """BasicAuth should return 'basic' mode."""
        bc = BasicAuth(lambda: "usr", lambda: "pwd")
        assert bc.apply({}) == "basic"

    def test_sets_basic_authorization_header(self):
        """BasicAuth.apply must set Authorization: Basic <base64(user:pass)>."""
        bc = BasicAuth(lambda: "alice", lambda: "secret")
        headers: dict[str, str] = {}
        bc.apply(headers)
        expected = base64.b64encode(b"alice:secret").decode("ascii")
        assert headers["Authorization"] == f"Basic {expected}"

    def test_encode_static_method(self):
        """Verify _encode produces correct base64 values for known inputs."""
        encoded = BasicAuth._encode("user", "pass")
        assert encoded == base64.b64encode(b"user:pass").decode("ascii")

    def test_encode_special_characters(self):
        """Verify _encode handles special characters in username/password."""
        encoded = BasicAuth._encode("user@domain", "p@ss:word!")
        expected = base64.b64encode(b"user@domain:p@ss:word!").decode("ascii")
        assert encoded == expected

    def test_is_available_with_both(self):
        """Both username and password non-empty → is_available returns True."""
        bc = BasicAuth(lambda: "user", lambda: "pass")
        assert bc.is_available()

    def test_is_available_empty_username(self):
        """Empty username → is_available returns False."""
        bc = BasicAuth(lambda: "", lambda: "pass")
        assert not bc.is_available()

    def test_is_available_empty_password(self):
        """Empty password → is_available returns False."""
        bc = BasicAuth(lambda: "user", lambda: "")
        assert not bc.is_available()

    def test_is_available_both_empty(self):
        """Both empty → is_available returns False."""
        bc = BasicAuth(lambda: "", lambda: "")
        assert not bc.is_available()

    def test_is_available_none_values(self):
        """None values → is_available returns False."""
        bc = BasicAuth(lambda: None, lambda: None)
        assert not bc.is_available()

    def test_overwrites_existing_authorization(self):
        """BasicAuth should overwrite any existing Authorization header."""
        bc = BasicAuth(lambda: "usr", lambda: "pwd")
        headers = {"Authorization": "Old-Value"}
        bc.apply(headers)
        assert headers["Authorization"].startswith("Basic ")
