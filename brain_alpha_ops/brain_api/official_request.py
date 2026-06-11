"""HTTP request helpers for the official BRAIN API adapter."""

from __future__ import annotations

import json
import logging
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from brain_alpha_ops.redaction import redact_error_message

from .base import BrainAPIError
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

            if self._prefer_cookie_auth and self._has_session_cookie():
                auth_mode = "cookie"
            elif self.token and not skip_auto_auth:
                request_headers["Authorization"] = f"Bearer {self.token}"
                auth_mode = "bearer"
            elif self.username and self.password and not skip_auto_auth:
                request_headers["Authorization"] = f"Basic {self._basic_auth()}"
                auth_mode = "basic"
            request_headers.update(caller_headers)
            self._throttle()
            req = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
            try:
                with self._open(req, timeout=self.config.timeout_seconds) as resp:
                    raw = resp.read().decode("utf-8")
                    return _parse(raw), dict(resp.headers.items())
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
                if exc.code == 401 and auth_mode == "bearer" and attempt < attempts - 1:
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
                last_error = BrainAPIError(
                    f"HTTP {exc.code}: {_scrub(parsed)}",
                    status_code=exc.code,
                    payload=_scrub(parsed),
                    retry_after=_retry_after(exc.headers),
                )
                if token_before_auth_fallback is not None and not self.token:
                    self.token = token_before_auth_fallback
                raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = BrainAPIError(f"network error: {exc}")
                if self.config.rate_limit_retry_attempts > 0 and attempt < attempts - 1:
                    time.sleep(_retry_delay(None, attempt, self.config.rate_limit_backoff_seconds))
                    continue
                if token_before_auth_fallback is not None and not self.token:
                    self.token = token_before_auth_fallback
                raise last_error from exc
        if last_error is not None:
            if token_before_auth_fallback is not None and not self.token:
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
