"""Authentication strategy protocol and concrete implementations.

Defines the ``AuthStrategy`` interface and three concrete strategies
(Cookie → Bearer → Basic) forming the authentication fallback chain.
"""

from __future__ import annotations

import base64
import http.cookiejar
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuthStrategy(Protocol):
    """Protocol for authentication strategies.

    Each strategy knows how to apply its credentials to an outgoing
    request and can report whether required credentials are available.
    """

    def apply(self, headers: dict[str, str]) -> str:
        """Apply auth credentials to ``headers`` in-place.

        Returns:
            The auth mode string (``"cookie"``, ``"bearer"``, ``"basic"``).
        """
        ...

    def is_available(self) -> bool:
        """Return ``True`` if this strategy has usable credentials."""
        ...


class CookieAuth:
    """Authenticate via session cookies stored in a ``CookieJar``.

    This strategy applies no explicit ``Authorization`` header — the
    ``HTTPCookieProcessor`` in the opener handles cookie transmission.
    """

    _MODE = "cookie"

    def __init__(self, cookie_jar: http.cookiejar.CookieJar) -> None:
        """Initialise with a shared cookie jar.

        Args:
            cookie_jar: The ``CookieJar`` used by the API's URL opener.
        """
        self._jar = cookie_jar

    def apply(self, headers: dict[str, str]) -> str:
        """No-op: cookies are transmitted by the opener automatically.

        Returns:
            ``"cookie"``.
        """
        return self._MODE

    def is_available(self) -> bool:
        """Return ``True`` if the cookie jar contains at least one cookie."""
        return any(True for _ in self._jar)


class BearerAuth:
    """Authenticate via a Bearer token in the ``Authorization`` header."""

    _MODE = "bearer"
    _HEADER = "Authorization"

    def __init__(self, token_getter: Any) -> None:
        """Initialise with a callable that returns the current token.

        Args:
            token_getter: A zero-argument callable (or property-like object)
                returning the bearer token string.
        """
        self._getter = token_getter

    def apply(self, headers: dict[str, str]) -> str:
        """Set the ``Authorization: Bearer <token>`` header.

        Returns:
            ``"bearer"``.
        """
        headers[self._HEADER] = f"Bearer {self._getter()}"
        return self._MODE

    def is_available(self) -> bool:
        """Return ``True`` if a non-empty token is present."""
        return bool(self._getter())


class BasicAuth:
    """Authenticate via HTTP Basic Auth with username / password."""

    _MODE = "basic"
    _HEADER = "Authorization"

    def __init__(
        self,
        username_getter: Any,
        password_getter: Any,
    ) -> None:
        """Initialise with callables for username and password.

        Args:
            username_getter: Zero-argument callable returning the username.
            password_getter: Zero-argument callable returning the password.
        """
        self._user = username_getter
        self._pw = password_getter

    @staticmethod
    def _encode(username: str, password: str) -> str:
        return base64.b64encode(
            f"{username}:{password}".encode("utf-8")
        ).decode("ascii")

    def apply(self, headers: dict[str, str]) -> str:
        """Set the ``Authorization: Basic <base64>`` header.

        Returns:
            ``"basic"``.
        """
        encoded = self._encode(self._user(), self._pw())
        headers[self._HEADER] = f"Basic {encoded}"
        return self._MODE

    def is_available(self) -> bool:
        """Return ``True`` if both username and password are non-empty."""
        return bool(self._user() and self._pw())
