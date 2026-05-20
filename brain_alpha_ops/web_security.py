"""Local web console session and request-origin security helpers."""

from __future__ import annotations

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
) -> bool:
    host = header_hostname(host_header)
    if host and host not in local_hosts:
        return False
    host_port = header_port(host_header)
    for header_value in (origin_header, referer_header):
        if not header_value:
            continue
        parsed = urlparse(header_value)
        if parsed.hostname not in local_hosts:
            return False
        if host_port and parsed.port and parsed.port != host_port:
            return False
    return True


@dataclass
class LocalSessionManager:
    cookie_name: str = SESSION_COOKIE_NAME
    ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    allow_multiple_sessions: bool = True
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def configure(self, ttl_seconds: int | float | None = None, allow_multiple_sessions: bool | None = None) -> None:
        if ttl_seconds is not None:
            try:
                self.ttl_seconds = max(60, int(ttl_seconds))
            except (TypeError, ValueError):
                self.ttl_seconds = DEFAULT_SESSION_TTL_SECONDS
        if allow_multiple_sessions is not None:
            self.allow_multiple_sessions = bool(allow_multiple_sessions)

    def cookie_header(self, session_id: str, *, max_age: int | None = None) -> str:
        max_age = self.ttl_seconds if max_age is None else max_age
        return f"{self.cookie_name}={session_id}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict"

    def expired_cookie_header(self) -> str:
        return f"{self.cookie_name}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"

    def prune(self, now: float | None = None) -> None:
        current = time.time() if now is None else now
        with self.lock:
            for session_id, row in list(self.sessions.items()):
                if float(row.get("expires_at", 0.0) or 0.0) <= current:
                    self.sessions.pop(session_id, None)

    def create(self) -> tuple[str, str]:
        self.prune()
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        stream_token = secrets.token_urlsafe(32)
        with self.lock:
            if not self.allow_multiple_sessions:
                self.sessions.clear()
            self.sessions[session_id] = {
                "csrf": csrf_token,
                "stream": stream_token,
                "expires_at": time.time() + self.ttl_seconds,
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
            if not row:
                return False
            if not secrets.compare_digest(str(row.get(token_key, "")), token):
                return False
            row["expires_at"] = time.time() + self.ttl_seconds
            return True

    def validate_csrf(self, session_id: str, csrf_token: str) -> bool:
        return self.validate_token(session_id, csrf_token, "csrf")

    def validate_stream(self, session_id: str, stream_token: str) -> bool:
        return self.validate_token(session_id, stream_token, "stream")

    def csrf_for_session(self, session_id: str) -> str:
        if not session_id:
            return ""
        self.prune()
        with self.lock:
            row = self.sessions.get(session_id)
            if not row:
                return ""
            row["expires_at"] = time.time() + self.ttl_seconds
            return str(row.get("csrf", ""))

    def stream_token_for_session(self, session_id: str) -> str:
        if not session_id:
            return ""
        self.prune()
        with self.lock:
            row = self.sessions.get(session_id)
            if not row:
                return ""
            if not row.get("stream"):
                row["stream"] = secrets.token_urlsafe(32)
            row["expires_at"] = time.time() + self.ttl_seconds
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
        if path == "/api/stream":
            stream_token = (parse_qs(query_string).get("stream_token") or [""])[0]
            return self.validate_stream(session_id, stream_token)
        return False
