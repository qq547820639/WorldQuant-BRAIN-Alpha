"""HTTP request helpers for the official BRAIN API adapter."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from brain_alpha_ops.redaction import redact_error_message

from .base import BrainAPIError


def _http_error_code(status: int, parsed: dict | None, auth_mode: str) -> str:
    """Map HTTP status + context to a user-facing error code (C20/C30)."""
    if status in (401, 403):
        detail = str(parsed.get("detail", "") if isinstance(parsed, dict) else "").lower()
        if "expired" in detail or "expir" in detail:
            return "AUTH_TOKEN_EXPIRED"
        if auth_mode == "bearer":
            return "AUTH_BEARER_INVALID"
        return "AUTH_INVALID"
    if status == 429:
        return "RATE_LIMITED"
    if status >= 500:
        return "BRAIN_SERVER_ERROR"
    return f"HTTP_{status}"

from .official_helpers import (
    build_official_url,
    parse_response as _parse,
    retry_after as _retry_after,
    retry_delay as _retry_delay,
    retryable_status as _retryable_status,
    scrub as _scrub,
)

logger = logging.getLogger("brain_alpha_ops.brain_api.official")


class OfficialRequestMixin:
    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        body: dict | None = None,
        query: dict | None = None,
        headers: dict | None = None,
        allow_auth_retry: bool = True,
    ) -> tuple[Any, dict]:
        url = build_official_url(self.config.base_url, path_or_url, query)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        attempts = max(1, int(self.config.rate_limit_retry_attempts) + 1)
        auth_refresh_available = (
            allow_auth_retry
            and bool(self.username and self.password)
            and not _is_authentication_request(path_or_url, self.config.authentication_path)
        )
        if self.token and (self._has_session_cookie() or (self.username and self.password)):
            attempts = max(attempts, 2)
        if auth_refresh_available:
            attempts = max(attempts, 2)
        last_error: BrainAPIError | None = None
        token_before_auth_fallback: str | None = None
        auth_refresh_attempted = False
        for attempt in range(attempts):
            request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
            auth_mode = "none"

            caller_headers = dict(headers or {})
            skip_auto_auth = caller_headers.pop("X-Auth-Mode", "") == "json"
            if skip_auto_auth and not any(h.lower() == "authorization" for h in caller_headers):
                logger.warning(
                    "X-Auth-Mode=json without explicit Authorization header "
                    "— request will be sent with no auth. Path: %s", path_or_url
                )

            with self._request_lock:
                if self._prefer_cookie_auth and self._has_session_cookie():
                    auth_mode = "cookie"
                elif self.token and not skip_auto_auth:
                    request_headers["Authorization"] = f"Bearer {self.token}"
                    auth_mode = "bearer"
                elif self.username and self.password and not skip_auto_auth:
                    request_headers["Authorization"] = f"Basic {self._basic_auth()}"
                    auth_mode = "basic"
            request_headers.update(caller_headers)
            if auth_mode == 'none' and 'Authorization' not in request_headers:
                logger.warning(
                    'HTTP request without Authorization header (auth_mode=none, '
                    'skip_auto_auth=%s, method=%s, path=%s)',
                    skip_auto_auth, method, path_or_url,
                )
            self._throttle()
            req = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
            try:
                with self._open(req, timeout=self.config.timeout_seconds) as resp:
                    raw = resp.read().decode("utf-8")
                    parsed = _parse(raw)
                    resp_headers = dict(resp.headers.items())
                    # C30 P0: Restore bearer token after successful cookie-auth fallback.
                    # When a 401 on bearer mode triggers a cookie-auth retry and succeeds,
                    # self.token was cleared (line 122) and never restored. Restoring it
                    # here ensures subsequent requests can fall back to bearer if the
                    # session cookie expires.
                    if token_before_auth_fallback is not None and not self.token and auth_mode != "bearer":
                        with self._request_lock:
                            self.token = token_before_auth_fallback
                    return parsed, resp_headers
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                try:
                    parsed = _parse(raw)
                except BrainAPIError:
                    parsed = {"raw": raw[:500]}
                rate_limit_text = json.dumps(parsed, ensure_ascii=False, default=str)
                concurrency_limit = "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in rate_limit_text
                if (
                    _retryable_status(exc.code)
                    and self.config.rate_limit_retry_attempts > 0
                    and attempt < attempts - 1
                    and not concurrency_limit
                ):
                    time.sleep(_retry_delay(exc.headers, attempt, self.config.rate_limit_backoff_seconds))
                    continue
                # C30 P0: 401 bearer token may be expired — differentiate from hard auth failure
                if exc.code == 401 and auth_mode == "bearer" and attempt < attempts - 1:
                    with self._request_lock:
                        token_before_auth_fallback = self.token
                        self.token = ""
                        if self._has_session_cookie():
                            self._prefer_cookie_auth = True
                    continue
                if (
                    exc.code in {401, 403}
                    and auth_refresh_available
                    and not auth_refresh_attempted
                    and attempt < attempts - 1
                ):
                    auth_refresh_attempted = True
                    auth_refresh_available = False
                    try:
                        self.authenticate()
                    except BrainAPIError:
                        logger.debug(
                            "API auth refresh failed: method=%s path=%s auth_mode=%s",
                            method,
                            path_or_url,
                            auth_mode,
                            exc_info=True,
                        )
                    else:
                        with self._request_lock:
                            if self._has_session_cookie():
                                self._prefer_cookie_auth = True
                        continue
                logger.debug(
                    "API auth context: method=%s path=%s auth_mode=%s "
                    "has_cookie=%s has_user_pass=%s",
                    method,
                    path_or_url,
                    auth_mode,
                    self._has_session_cookie(),
                    bool(self.username and self.password),
                )
                # C20 P0: derive error_code from HTTP status for frontend display
                _error_code = _http_error_code(exc.code, parsed, auth_mode)
                last_error = BrainAPIError(
                    f"HTTP {exc.code}: {_scrub(parsed)}",
                    status_code=exc.code,
                    payload=_scrub(parsed),
                    retry_after=_retry_after(exc.headers),
                    error_code=_error_code,
                )
                if token_before_auth_fallback is not None and not self.token:
                    with self._request_lock:
                        self.token = token_before_auth_fallback
                raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = BrainAPIError(f"network error: {exc}")
                if self.config.rate_limit_retry_attempts > 0 and attempt < attempts - 1:
                    time.sleep(_retry_delay(None, attempt, self.config.rate_limit_backoff_seconds))
                    continue
                if token_before_auth_fallback is not None and not self.token:
                    with self._request_lock:
                        self.token = token_before_auth_fallback
                raise last_error from exc
        if last_error is not None:
            if token_before_auth_fallback is not None and not self.token:
                with self._request_lock:
                    self.token = token_before_auth_fallback
            raise BrainAPIError(
                f"request failed after retries: {redact_error_message(last_error)}",
                status_code=last_error.status_code,
                payload=getattr(last_error, "payload", None),
                retry_after=getattr(last_error, "retry_after", None),
            ) from last_error
        raise BrainAPIError("request failed after retries")


def _is_authentication_request(path_or_url: str, authentication_path: str) -> bool:
    path = urllib.parse.urlparse(str(path_or_url or "")).path if str(path_or_url or "").startswith(("http://", "https://")) else str(path_or_url or "")
    return "/" + path.lstrip("/") == "/" + str(authentication_path or "").lstrip("/")
