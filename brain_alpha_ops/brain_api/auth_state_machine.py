"""Authentication state machine for the BRAIN API adapter.

Encapsulates the cookie → bearer → basic authentication fallback chain,
token save / restore, and auth-refresh transitions previously scattered
across 200+ lines in ``official_request.py``.

Design principles
-----------------
- **Deep module**: a simple public API (``authenticate``, ``on_auth_failure``,
  ``restore_token``) hides the complexity of strategy selection, token
  lifecycle management, and retry-state tracking.
- **Thread-safe**: all mutable state writes are guarded by the shared
  ``_request_lock``.
- **No new dependencies**: relies only on ``auth_strategy``, ``BrainAPIError``,
  and the standard library.
"""

from __future__ import annotations

import enum
import logging
import threading
from dataclasses import dataclass
from typing import Any

from brain_alpha_ops.brain_api.auth_strategy import (
    AuthStrategy,
    BasicAuth,
    BearerAuth,
    CookieAuth,
)
from brain_alpha_ops.brain_api.base import BrainAPIError

logger = logging.getLogger("brain_alpha_ops.brain_api.auth_sm")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AuthAction(enum.Enum):
    """Action the caller should take after ``on_auth_failure``.

    ``RETRY``: the state machine has transitioned to a different strategy;
        the caller should re-apply auth and retry the request.

    ``RAISE``: no viable strategy remains — the caller should raise.
    """

    RETRY = "retry"
    RAISE = "raise"


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------


@dataclass
class _AuthState:
    """Mutable auth state, guarded by ``lock`` (the API-level RLock)."""

    prefer_cookie: bool = False
    saved_token: str | None = None
    auth_refresh_attempted: bool = False
    current_mode: str = "none"


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class AuthStateMachine:
    """Centralised authentication state machine for official BRAIN API.

    Manages the three-tier fallback chain, token save/restore around auth
    transitions, and auth-refresh lifecycle.

    Usage pattern (inside ``_request``)::

        sm = self._auth_state_machine

        # --- apply auth ---
        auth_mode = sm.authenticate(headers)
        req = Request(...)

        try:
            resp = open(req)
        except HTTPError as exc:
            action = sm.on_auth_failure(
                exc.code, auth_mode,
                has_more_attempts=(attempt < max_attempts - 1),
                is_auth_retry_allowed=True,
            )
            if action == AuthAction.RETRY:
                continue
            raise
        else:
            sm.on_success()
    """

    # Strategy chain priority (checked in order)
    _STRATEGIES: tuple[str, ...] = ("cookie", "bearer", "basic")

    def __init__(
        self,
        *,
        # Credential accessors
        token_getter: Any,
        token_setter: Any,
        username_getter: Any,
        password_getter: Any,
        # Cookie / lock
        cookie_jar_getter: Any,
        prefer_cookie_getter: Any,
        prefer_cookie_setter: Any,
        lock: threading.RLock,
        # Auth refresh
        authenticator: Any,
        # Config
        authentication_path: str,
    ) -> None:
        """Initialise the state machine.

        Args:
            token_getter / token_setter: get/set ``self.token``.
            username_getter / password_getter: get ``self.username``,
                ``self.password``.
            cookie_jar_getter: returns the ``CookieJar`` instance.
            prefer_cookie_getter / prefer_cookie_setter: get/set
                ``self._prefer_cookie_auth``.
            lock: the API's ``_request_lock`` (``RLock``) for thread safety.
            authenticator: callable ``authenticate()`` for auth refresh.
            authentication_path: the API's ``authentication_path`` config.
        """
        self._token_getter = token_getter
        self._token_setter = token_setter
        self._username_getter = username_getter
        self._password_getter = password_getter
        self._cookie_jar_getter = cookie_jar_getter
        self._prefer_cookie_getter = prefer_cookie_getter
        self._prefer_cookie_setter = prefer_cookie_setter
        self._lock = lock
        self._authenticator = authenticator
        self._authentication_path = authentication_path

        # Build strategy instances
        self._cookie = CookieAuth(cookie_jar_getter())
        self._bearer = BearerAuth(token_getter)
        self._basic = BasicAuth(username_getter, password_getter)

        self._state = _AuthState()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def authenticate(self, headers: dict[str, str], *, skip_auto_auth: bool = False) -> str:
        """Apply the current-best auth strategy to ``headers``.

        Strategy priority: cookie > bearer > basic.  When no strategy is
        available, auth_mode is ``"none"``.

        Args:
            headers: Mutable dict of request headers (modified in-place).
            skip_auto_auth: If ``True``, skip bearer and basic (caller
                handles auth manually or via ``X-Auth-Mode: json``).

        Returns:
            The auth mode string (``"cookie"``, ``"bearer"``, ``"basic"``,
            ``"none"``).
        """
        with self._lock:
            # 1) Cookie (only when explicitly preferred)
            if self._prefer_cookie_getter() and self._cookie.is_available():
                mode = self._cookie.apply(headers)
                self._state.current_mode = mode
                return mode

            # 2) Bearer
            if not skip_auto_auth and self._bearer.is_available():
                mode = self._bearer.apply(headers)
                self._state.current_mode = mode
                return mode

            # 3) Basic
            if not skip_auto_auth and self._basic.is_available():
                mode = self._basic.apply(headers)
                self._state.current_mode = mode
                return mode

            self._state.current_mode = "none"
            return "none"

    def on_auth_failure(
        self,
        status: int,
        auth_mode: str,
        *,
        has_more_attempts: bool,
        is_auth_retry_allowed: bool,
        path_or_url: str = "",
    ) -> AuthAction:
        """Handle an HTTP auth failure and determine the next action.

        The state machine may transition to a fallback strategy or trigger
        an auth refresh.  Token save/restore is managed internally.

        Args:
            status: HTTP status code (401, 403, etc.).
            auth_mode: The auth mode used for the failed request.
            has_more_attempts: Whether the retry loop has remaining slots.
            is_auth_retry_allowed: Whether ``allow_auth_retry`` is enabled
                for this request.
            path_or_url: The request path (for logging / skip-auth checks).

        Returns:
            ``AuthAction.RETRY`` if the caller should retry with the new
            strategy, ``AuthAction.RAISE`` otherwise.
        """
        if not has_more_attempts:
            return AuthAction.RAISE

        # -- Bearer 401 → fall back to cookie ---------------------------------
        if status == 401 and auth_mode == "bearer":
            with self._lock:
                self._state.saved_token = self._token_getter()
                self._token_setter("")
                if self._cookie.is_available():
                    self._prefer_cookie_setter(True)
            return AuthAction.RETRY

        # -- 401/403 → auth refresh (basic auth) -----------------------------
        if (
            status in {401, 403}
            and is_auth_retry_allowed
            and not self._state.auth_refresh_attempted
        ):
            self._state.auth_refresh_attempted = True
            try:
                self._authenticator()
            except BrainAPIError:
                logger.debug(
                    "Auth refresh failed: status=%d auth_mode=%s path=%s",
                    status,
                    auth_mode,
                    path_or_url,
                    exc_info=True,
                )
            else:
                with self._lock:
                    if self._cookie.is_available():
                        self._prefer_cookie_setter(True)
                return AuthAction.RETRY

        return AuthAction.RAISE

    def on_success(self) -> None:
        """Notify the state machine of a successful request.

        Restores a previously-saved bearer token after cookie / basic auth
        fallback so that subsequent requests can use bearer mode if the
        session cookie expires.
        """
        with self._lock:
            if self._state.saved_token is not None and not self._token_getter():
                self._token_setter(self._state.saved_token)

    def restore_token(self) -> None:
        """Explicitly restore a saved bearer token.

        Called by the retry-loop exhaustion path to ensure the token is
        never lost across error branches.
        """
        with self._lock:
            if self._state.saved_token is not None and not self._token_getter():
                self._token_setter(self._state.saved_token)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        """``True`` if any auth strategy is currently usable."""
        return (
            self._cookie.is_available()
            or self._bearer.is_available()
            or self._basic.is_available()
        )

    @property
    def current_strategy(self) -> AuthStrategy:
        """Return the currently-active ``AuthStrategy``.

        Returns the first available strategy in priority order.
        """
        if self._prefer_cookie_getter() and self._cookie.is_available():
            return self._cookie
        if self._bearer.is_available():
            return self._bearer
        if self._basic.is_available():
            return self._basic
        return self._cookie  # fallback (unusable)
