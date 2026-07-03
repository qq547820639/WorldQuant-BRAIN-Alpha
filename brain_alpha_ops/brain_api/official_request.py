"""HTTP request helpers for the official BRAIN API adapter.

The ``_request()`` method delegates authentication strategy selection,
token lifecycle, and auth-fallback transitions to ``AuthStateMachine``.
"""

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
from .auth_state_machine import AuthAction

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
        if self.token and (self._has_session_cookie() or (self.username and self.password)):
            attempts = max(attempts, 2)
        can_auth_refresh = (
            allow_auth_retry
            and bool(self.username and self.password)
            and not _is_authentication_request(path_or_url, self.config.authentication_path)
        )
        if can_auth_refresh:
            attempts = max(attempts, 2)
        last_error: BrainAPIError | None = None
        sm = self._auth_state_machine
        for attempt in range(attempts):
            request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
            caller_headers = dict(headers or {})
            skip_auto_auth = caller_headers.pop("X-Auth-Mode", "") == "json"
            if skip_auto_auth and not any(h.lower() == "authorization" for h in caller_headers):
                logger.warning(
                    "X-Auth-Mode=json without explicit Authorization header "
                    "— request will be sent with no auth. Path: %s", path_or_url
                )
            auth_mode = sm.authenticate(request_headers, skip_auto_auth=skip_auto_auth)
            request_headers.update(caller_headers)
            if auth_mode == "none" and "Authorization" not in request_headers:
                logger.warning(
                    "HTTP request without Authorization header (auth_mode=none, "
                    "skip_auto_auth=%s, method=%s, path=%s)",
                    skip_auto_auth, method, path_or_url,
                )
            self._throttle()
            req = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
            try:
                with self._open(req, timeout=self.config.timeout_seconds) as resp:
                    raw = resp.read().decode("utf-8")
                    parsed = _parse(raw)
                    resp_headers = dict(resp.headers.items())
                    sm.on_success()
                    return parsed, resp_headers
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                try:
                    parsed = _parse(raw)
                except BrainAPIError:
                    parsed = {"raw": raw[:500]}
                _error_code = _http_error_code(exc.code, parsed, auth_mode)
                last_error = BrainAPIError(
                    f"HTTP {exc.code}: {_scrub(parsed)}",
                    status_code=exc.code,
                    payload=_scrub(parsed),
                    retry_after=_retry_after(exc.headers),
                    error_code=_error_code,
                )
                if (
                    _retryable_status(exc.code)
                    and self.config.rate_limit_retry_attempts > 0
                    and attempt < attempts - 1
                    and "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"
                    not in json.dumps(parsed, ensure_ascii=False, default=str)
                ):
                    time.sleep(_retry_delay(exc.headers, attempt, self.config.rate_limit_backoff_seconds))
                    continue
                action = sm.on_auth_failure(
                    exc.code, auth_mode,
                    has_more_attempts=(attempt < attempts - 1),
                    is_auth_retry_allowed=can_auth_refresh,
                    path_or_url=path_or_url,
                )
                if action == AuthAction.RETRY:
                    continue
                logger.debug(
                    "API final failure: method=%s path=%s auth_mode=%s status=%d",
                    method, path_or_url, auth_mode, exc.code,
                )
                sm.restore_token()
                raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = BrainAPIError(f"network error: {exc}")
                if self.config.rate_limit_retry_attempts > 0 and attempt < attempts - 1:
                    time.sleep(_retry_delay(None, attempt, self.config.rate_limit_backoff_seconds))
                    continue
                sm.restore_token()
                raise last_error from exc
        sm.restore_token()
        if last_error is not None:
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
