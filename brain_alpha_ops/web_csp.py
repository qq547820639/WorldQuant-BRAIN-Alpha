"""Web security: CSP headers, CSRF tokens, session management."""

from __future__ import annotations

import base64
import hashlib
import re


SCRIPT_BLOCK_PATTERN = re.compile(r"<script(?:\s[^>]*)?>(.*?)</script>", re.IGNORECASE | re.DOTALL)
STYLE_BLOCK_PATTERN = re.compile(r"<style(?:\s[^>]*)?>(.*?)</style>", re.IGNORECASE | re.DOTALL)


def script_hash_sources(html: str) -> str:
    return _hash_sources(html, SCRIPT_BLOCK_PATTERN)


def style_hash_sources(html: str) -> str:
    return _hash_sources(html, STYLE_BLOCK_PATTERN)


def content_security_policy_for_html(html: str) -> str:
    script_hashes = script_hash_sources(html)
    style_hashes = style_hash_sources(html)

    # Detect if the HTML uses CDN scripts (React app) — allow unpkg.com + tailwind CDN
    uses_cdn = "unpkg.com" in html or "cdn.tailwindcss.com" in html
    cdn_sources = " https://unpkg.com https://cdn.tailwindcss.com" if uses_cdn else ""

    script_src = f"script-src 'self'{cdn_sources}" + (f" {script_hashes}" if script_hashes else "")
    style_src = "style-src 'self'" + (f" {style_hashes}" if style_hashes else "")
    return (
        f"default-src 'self'; {script_src}; "
        f"{style_src}; connect-src 'self'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )


def _hash_sources(html: str, pattern: re.Pattern[str]) -> str:
    hashes: list[str] = []
    for match in pattern.finditer(html):
        digest = hashlib.sha256(match.group(1).encode("utf-8")).digest()
        hashes.append("'sha256-" + base64.b64encode(digest).decode("ascii") + "'")
    return " ".join(hashes)


"""Local web console session and request-origin security helpers."""

from dataclasses import dataclass, field
import secrets
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlparse


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOOPBACK_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}
SESSION_COOKIE_NAME = "brain_alpha_ops_session"
DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60
DEFAULT_SESSION_ABSOLUTE_MAX_SECONDS = 24 * 60 * 60
REQUEST_REPLAY_TTL_SECONDS = 5 * 60
MAX_REQUEST_ID_LENGTH = 128


def header_hostname(host_header: str) -> str:
    return (urlparse(f"//{host_header}").hostname or "").lower()


def header_port(host_header: str) -> int | None:
    try:
        return urlparse(f"//{host_header}").port
    except ValueError:
        return None


def path_requires_session(path: str) -> bool:
    return path.startswith("/api/") and path != "/api/health"


def parse_cookies(cookie_header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in str(cookie_header or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def normalize_host(host: str | None, *, default_host: str = "127.0.0.1") -> str:
    value = str(host or "").strip()
    return value or default_host


def is_allowed_local_request(
    *,
    host_header: str,
    origin_header: str = "",
    referer_header: str = "",
    local_hosts: set[str] | frozenset[str] = LOCAL_HOSTS,
    allow_remote: bool = False,
) -> bool:
    host = header_hostname(host_header)
    if host and host not in local_hosts and not allow_remote:
        return False
    host_port = header_port(host_header)
    for header_value in (origin_header, referer_header):
        if not header_value:
            continue
        parsed = urlparse(header_value)
        parsed_host = (parsed.hostname or "").lower()
        if allow_remote and host:
            if parsed_host != host:
                return False
        elif parsed_host not in local_hosts:
            return False
        parsed_port = parsed.port
        if host_port and parsed_port and parsed_port != host_port:
            return False
    return True


def admin_token_from_headers(headers: Any) -> str:
    auth_header = str(headers.get("Authorization", "") if headers else "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return str(headers.get("X-Brain-Alpha-Admin-Token", "") if headers else "").strip()


def validate_admin_token(provided_token: str, expected_token: str) -> bool:
    if not provided_token or not expected_token:
        return False
    return secrets.compare_digest(str(provided_token), str(expected_token))


@dataclass
class LocalSessionManager:
    cookie_name: str = SESSION_COOKIE_NAME
    ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    absolute_max_seconds: int = DEFAULT_SESSION_ABSOLUTE_MAX_SECONDS
    allow_multiple_sessions: bool = True
    secure_cookies: bool = False
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def configure(
        self,
        ttl_seconds: int | float | None = None,
        allow_multiple_sessions: bool | None = None,
        secure_cookies: bool | None = None,
        absolute_max_seconds: int | float | None = None,
    ) -> None:
        if ttl_seconds is not None:
            try:
                self.ttl_seconds = max(60, int(ttl_seconds))
            except (TypeError, ValueError):
                self.ttl_seconds = DEFAULT_SESSION_TTL_SECONDS
        if absolute_max_seconds is not None:
            try:
                self.absolute_max_seconds = max(self.ttl_seconds, int(absolute_max_seconds))
            except (TypeError, ValueError):
                self.absolute_max_seconds = DEFAULT_SESSION_ABSOLUTE_MAX_SECONDS
        if allow_multiple_sessions is not None:
            self.allow_multiple_sessions = bool(allow_multiple_sessions)
        if secure_cookies is not None:
            self.secure_cookies = bool(secure_cookies)

    def cookie_header(self, session_id: str, *, max_age: int | None = None) -> str:
        max_age = self.ttl_seconds if max_age is None else max_age
        secure = "; Secure" if self.secure_cookies else ""
        return f"{self.cookie_name}={session_id}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict{secure}"

    def expired_cookie_header(self) -> str:
        secure = "; Secure" if self.secure_cookies else ""
        return f"{self.cookie_name}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{secure}"

    def prune(self, now: float | None = None) -> None:
        current = time.time() if now is None else now
        with self.lock:
            for session_id, row in list(self.sessions.items()):
                if self._row_expired(row, current):
                    self.sessions.pop(session_id, None)

    def create(self) -> tuple[str, str]:
        self.prune()
        now = time.time()
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        stream_token = secrets.token_urlsafe(32)
        with self.lock:
            if not self.allow_multiple_sessions:
                self.sessions.clear()
            self.sessions[session_id] = {
                "csrf": csrf_token,
                "stream": stream_token,
                "request_replay": {},
                "created_at": now,
                "expires_at": now + self.ttl_seconds,
                "absolute_expires_at": now + self.absolute_max_seconds,
            }
        return session_id, csrf_token

    def expire(self, session_id: str) -> None:
        if not session_id:
            return
        with self.lock:
            self.sessions.pop(session_id, None)

    def validate_token(self, session_id: str, token: str, token_key: str) -> bool:
        if not session_id or not token:
            return False
        self.prune()
        with self.lock:
            row = self.sessions.get(session_id)
            if not row or self._row_expired(row, time.time()):
                self.sessions.pop(session_id, None)
                return False
            if not secrets.compare_digest(str(row.get(token_key, "")), token):
                return False
            self._refresh_sliding_expiry(row, time.time())
            return True

    def validate_csrf(self, session_id: str, csrf_token: str) -> bool:
        return self.validate_token(session_id, csrf_token, "csrf")

    def validate_stream(self, session_id: str, stream_token: str) -> bool:
        return self.validate_token(session_id, stream_token, "stream")

    def validate_replay(
        self,
        session_id: str,
        request_id: str,
        request_timestamp: str,
        *,
        now: float | None = None,
        ttl_seconds: int = REQUEST_REPLAY_TTL_SECONDS,
    ) -> dict[str, Any]:
        current = time.time() if now is None else now
        request_id = str(request_id or "").strip()
        if not session_id:
            return {"ok": False, "error_code": "SESSION_INVALID", "error": "invalid local session"}
        if not request_id:
            return {"ok": False, "error_code": "REPLAY_TOKEN_REQUIRED", "error": "missing request id"}
        if len(request_id) > MAX_REQUEST_ID_LENGTH:
            return {"ok": False, "error_code": "REPLAY_TOKEN_INVALID", "error": "request id is too long"}
        if any(ch.isspace() for ch in request_id):
            return {"ok": False, "error_code": "REPLAY_TOKEN_INVALID", "error": "request id must not contain whitespace"}
        try:
            timestamp = float(str(request_timestamp or "").strip())
        except (TypeError, ValueError):
            return {"ok": False, "error_code": "REPLAY_TIMESTAMP_INVALID", "error": "invalid request timestamp"}
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000.0
        if abs(current - timestamp) > ttl_seconds:
            return {"ok": False, "error_code": "REPLAY_TIMESTAMP_STALE", "error": "stale request timestamp"}

        self.prune(current)
        with self.lock:
            row = self.sessions.get(session_id)
            if not row or self._row_expired(row, current):
                self.sessions.pop(session_id, None)
                return {"ok": False, "error_code": "SESSION_INVALID", "error": "invalid local session"}
            replay_cache = row.setdefault("request_replay", {})
            for cached_id, expires_at in list(replay_cache.items()):
                if float(expires_at or 0.0) <= current:
                    replay_cache.pop(cached_id, None)
            if request_id in replay_cache:
                return {"ok": False, "error_code": "REPLAY_DETECTED", "error": "duplicate request id"}
            replay_cache[request_id] = current + ttl_seconds
            self._refresh_sliding_expiry(row, current)
        return {"ok": True}

    def csrf_for_session(self, session_id: str) -> str:
        if not session_id:
            return ""
        self.prune()
        with self.lock:
            row = self.sessions.get(session_id)
            now = time.time()
            if not row or self._row_expired(row, now):
                self.sessions.pop(session_id, None)
                return ""
            self._refresh_sliding_expiry(row, now)
            return str(row.get("csrf", ""))

    def stream_token_for_session(self, session_id: str) -> str:
        if not session_id:
            return ""
        self.prune()
        with self.lock:
            row = self.sessions.get(session_id)
            now = time.time()
            if not row or self._row_expired(row, now):
                self.sessions.pop(session_id, None)
                return ""
            if not row.get("stream"):
                row["stream"] = secrets.token_urlsafe(32)
            self._refresh_sliding_expiry(row, now)
            return str(row.get("stream", ""))

    def get_or_create(self, existing_session_id: str) -> tuple[str, str]:
        csrf_token = self.csrf_for_session(existing_session_id)
        if csrf_token:
            return existing_session_id, csrf_token
        return self.create()

    def session_id_from_cookie(self, cookie_header: str) -> str:
        return parse_cookies(cookie_header).get(self.cookie_name, "")

    def has_valid_request_session(
        self,
        *,
        path: str,
        query_string: str,
        csrf_header: str,
        cookie_header: str,
    ) -> bool:
        session_id = self.session_id_from_cookie(cookie_header)
        if csrf_header:
            return self.validate_csrf(session_id, csrf_header)
        if path in {"/api/stream", "/sse"}:
            stream_token = (parse_qs(query_string).get("stream_token") or [""])[0]
            return self.validate_stream(session_id, stream_token)
        return False

    def _row_expired(self, row: dict[str, Any], current: float) -> bool:
        sliding_expires_at = float(row.get("expires_at", 0.0) or 0.0)
        absolute_expires_at = float(row.get("absolute_expires_at", 0.0) or 0.0)
        return sliding_expires_at <= current or (absolute_expires_at > 0 and absolute_expires_at <= current)

    def _refresh_sliding_expiry(self, row: dict[str, Any], current: float) -> None:
        absolute_expires_at = float(row.get("absolute_expires_at", 0.0) or 0.0)
        next_expires_at = current + self.ttl_seconds
        if absolute_expires_at > 0:
            next_expires_at = min(next_expires_at, absolute_expires_at)
        row["expires_at"] = next_expires_at


"""Global session policy facade for the local web console."""

import os
from typing import Any

from brain_alpha_ops.web_security import (
    LOCAL_HOSTS,
    LocalSessionManager,
    admin_token_from_headers,
    is_allowed_local_request,
    normalize_host as _normalize_host,
    validate_admin_token,
)


DEFAULT_ADMIN_TOKEN_ENV = "BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN"

SESSION_MANAGER = LocalSessionManager()
SESSIONS = SESSION_MANAGER.sessions
SESSION_LOCK = SESSION_MANAGER.lock

allow_remote_requests = False
remote_admin_token_env = DEFAULT_ADMIN_TOKEN_ENV


def configure_session_policy(
    ttl_seconds: int | float | None = None,
    allow_multiple_sessions: bool | None = None,
    secure_cookies: bool | None = None,
    absolute_max_seconds: int | float | None = None,
) -> None:
    SESSION_MANAGER.configure(ttl_seconds, allow_multiple_sessions, secure_cookies, absolute_max_seconds)


def session_ttl_seconds() -> int:
    return SESSION_MANAGER.ttl_seconds


def session_allow_multiple() -> bool:
    return SESSION_MANAGER.allow_multiple_sessions


def set_remote_policy(*, allow_remote: bool, admin_token_env: str | None = None) -> None:
    global allow_remote_requests, remote_admin_token_env
    allow_remote_requests = bool(allow_remote)
    if admin_token_env:
        remote_admin_token_env = str(admin_token_env)


def require_remote_admin_token() -> None:
    if allow_remote_requests and not os.getenv(remote_admin_token_env, ""):
        raise ValueError(f"remote web bind requires admin token env var {remote_admin_token_env}")


def remote_admin_required() -> bool:
    return bool(allow_remote_requests)


def has_valid_admin_token(headers: Any) -> bool:
    expected_token = os.getenv(remote_admin_token_env, "")
    provided_token = admin_token_from_headers(headers)
    return validate_admin_token(provided_token, expected_token)


def is_allowed_request(*, host_header: str, origin_header: str = "", referer_header: str = "") -> bool:
    return is_allowed_local_request(
        host_header=host_header,
        origin_header=origin_header,
        referer_header=referer_header,
        local_hosts=LOCAL_HOSTS,
        allow_remote=allow_remote_requests,
    )


def normalize_host(host: str | None, *, default_host: str = "127.0.0.1") -> str:
    return _normalize_host(host, default_host=default_host)


def session_cookie_header(session_id: str, *, max_age: int | None = None) -> str:
    return SESSION_MANAGER.cookie_header(session_id, max_age=max_age)


def expired_session_cookie_header() -> str:
    return SESSION_MANAGER.expired_cookie_header()


def prune_sessions(now: float | None = None) -> None:
    SESSION_MANAGER.prune(now)


def create_session() -> tuple[str, str]:
    return SESSION_MANAGER.create()


def expire_session(session_id: str) -> None:
    SESSION_MANAGER.expire(session_id)


def validate_session_token(session_id: str, token: str, token_key: str) -> bool:
    return SESSION_MANAGER.validate_token(session_id, token, token_key)


def validate_session(session_id: str, csrf_token: str) -> bool:
    return SESSION_MANAGER.validate_csrf(session_id, csrf_token)


def validate_stream_session(session_id: str, stream_token: str) -> bool:
    return SESSION_MANAGER.validate_stream(session_id, stream_token)


def csrf_for_session(session_id: str) -> str:
    return SESSION_MANAGER.csrf_for_session(session_id)


def stream_token_for_session(session_id: str) -> str:
    return SESSION_MANAGER.stream_token_for_session(session_id)


def get_or_create_session(existing_session_id: str) -> tuple[str, str]:
    return SESSION_MANAGER.get_or_create(existing_session_id)


def session_id_from_cookie(cookie_header: str) -> str:
    return SESSION_MANAGER.session_id_from_cookie(cookie_header)


def has_valid_request_session(
    *,
    path: str,
    query_string: str,
    csrf_header: str,
    cookie_header: str,
) -> bool:
    return SESSION_MANAGER.has_valid_request_session(
        path=path,
        query_string=query_string,
        csrf_header=csrf_header,
        cookie_header=cookie_header,
    )


def validate_replay_request(
    *,
    session_id: str,
    request_id: str,
    request_timestamp: str,
) -> dict[str, Any]:
    return SESSION_MANAGER.validate_replay(
        session_id=session_id,
        request_id=request_id,
        request_timestamp=request_timestamp,
    )