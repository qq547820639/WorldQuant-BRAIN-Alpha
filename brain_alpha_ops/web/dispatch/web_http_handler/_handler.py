"""HTTP handler factory for the local web console.

Subpackage split (deep-optimization-phase13, Task A4) of the former
``web_http_handler.py`` monolith. This module hosts the
``create_handler_class`` factory that builds a ``BaseHTTPRequestHandler``
subclass bound to the supplied dispatch callbacks, session validator,
SSE job resolver, and static-asset resolver.

The helper functions referenced from inside the closure
(``_json_default``, ``_is_origin_allowed``, ``_is_terminal_status``,
``_sse_event_type``) live in ``_helpers`` and are imported here so the
closure captures the same singletons the public API exposes.
"""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from ._helpers import (
    _is_terminal_status,
    _json_default,
    _sse_event_type,
    set_cors_headers,
)


def create_handler_class(
    *,
    server_version: str,
    max_body_bytes: int,
    dispatch_get: Callable[[Any, Any, Any], None],
    dispatch_post: Callable[[Any, Any, Any], None],
    dispatch_context: Callable[[], Any],
    web_session: Any,
    jobs: Any | None = None,
    enrich_progress: Callable[[dict], dict],
    content_security_policy_for_html: Callable[[str | None], str],
    sse_push_interval: float,
    max_sse_duration: float,
    resolve_sse_job: Callable[[str], dict | None] | None = None,
    resolve_static_asset: Callable[[str], tuple[bytes, str] | None] | None = None,
) -> type[BaseHTTPRequestHandler]:
    server_version_value = server_version
    max_body_bytes_value = max_body_bytes
    sse_push_interval_value = sse_push_interval
    max_sse_duration_value = max_sse_duration
    if resolve_sse_job is not None:
        resolve_sse_job_value = resolve_sse_job
    else:
        if jobs is None:
            raise ValueError("jobs or resolve_sse_job is required")
        resolve_sse_job_value = lambda job_id: jobs.get(job_id)
    resolve_static_asset_value = resolve_static_asset or (lambda _path: None)

    class Handler(BaseHTTPRequestHandler):
        server_version = server_version_value
        _MAX_BODY_BYTES = max_body_bytes_value

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path.startswith("/assets/"):
                self._handle_static_asset(parsed.path)
                return
            dispatch_get(self, parsed, dispatch_context())

        def do_POST(self):
            # P1-2: Content-Type 校验——带 body 的 JSON API 请求必须是 application/json。
            # 无 body（Content-Length == 0/缺省）时不校验，兼容无 body 的触发类端点
            # （如 /api/session、/api/logout、/api/shutdown）。校验放在公共层 do_POST
            # 开头，避免每个端点单独处理。
            if self._reject_unsupported_json_content_type():
                return
            dispatch_post(self, urlparse(self.path), dispatch_context())

        def _reject_unsupported_json_content_type(self) -> bool:
            """对带 body 的 POST 校验 Content-Type 为 application/json。

            仅当 Content-Length > 0 时强制要求 ``Content-Type: application/json``
            （允许 charset 等参数，如 ``application/json; charset=utf-8``）。无 body
            请求不校验。不匹配时发送 415 Unsupported Media Type + JSON 错误信息并
            返回 True；放行时返回 False。
            """
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except (TypeError, ValueError):
                length = 0
            if length <= 0:
                return False
            content_type = self.headers.get("Content-Type", "")
            media_type = content_type.split(";", 1)[0].strip().lower()
            if media_type == "application/json":
                return False
            self._json(
                {
                    "ok": False,
                    "error_code": "UNSUPPORTED_MEDIA_TYPE",
                    "error": "Content-Type \u5fc5\u987b\u662f application/json",
                    "details": {"content_type": content_type or None},
                },
                status=415,
            )
            return True

        def do_OPTIONS(self):
            self.send_response(204)
            # 统一 CORS: 仅当 Origin 通过白名单校验时回显 ACAO；无 Origin 或白名单外
            # 不设置 ACAO（不回退 Host 头），浏览器会拦截跨域预检。
            cors_headers: dict[str, str] = {}
            set_cors_headers(self.headers, cors_headers)
            for name, value in cors_headers.items():
                self.send_header(name, value)
            self.end_headers()

        def _send_html(self, html, *, extra_headers=None):
            body = html.encode("utf-8") if isinstance(html, str) else html
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if extra_headers:
                for name, value in extra_headers:
                    self.send_header(name, value)
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload, status=200, *, extra_headers=None):
            import json as _json_module
            body = _json_module.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            # CORS headers MUST be set before end_headers() — Python's
            # BaseHTTPRequestHandler does not allow send_header/end_headers
            # after the first body write.  Unified via set_cors_headers:
            # only echo ACAO for allowlisted origins (no Host fallback).
            cors_headers: dict[str, str] = {}
            set_cors_headers(self.headers, cors_headers)
            for name, value in cors_headers.items():
                self.send_header(name, value)
            if extra_headers:
                for name, value in extra_headers:
                    self.send_header(name, value)
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *args):
            return

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0:
                raise ValueError("invalid request body length")
            if length > self._MAX_BODY_BYTES:
                raise ValueError("request body too large")
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _is_allowed_local_request(self) -> bool:
            return web_session.is_allowed_request(
                host_header=self.headers.get("Host", ""),
                origin_header=self.headers.get("Origin", ""),
                referer_header=self.headers.get("Referer", ""),
            )

        def _has_valid_session(self, query_string: str = "") -> bool:
            return web_session.has_valid_request_session(
                path=urlparse(self.path).path,
                query_string=query_string,
                csrf_header=str(
                    self.headers.get("X-Brain-Alpha-CSRF", "")
                    or self.headers.get("X-CSRF-Token", "")
                    or self.headers.get("X-CSRF", "")
                ),
                cookie_header=self.headers.get("Cookie", ""),
            )

        def _validate_replay_request(self) -> dict:
            return web_session.validate_replay_request(
                session_id=self._session_id_from_cookie(),
                request_id=str(self.headers.get("X-Brain-Alpha-Request-ID", "")),
                request_timestamp=str(self.headers.get("X-Brain-Alpha-Request-Timestamp", "")),
            )

        def _session_id_from_cookie(self) -> str:
            return web_session.session_id_from_cookie(self.headers.get("Cookie", ""))

        def _handle_sse_stream(self, query_string: str):
            if not self._has_valid_session(query_string):
                self._json({"ok": False, "error_code": "AUTH_REQUIRED", "error": "session required"}, status=401)
                return

            job_id = (parse_qs(query_string).get("job_id") or [""])[0]
            if not job_id:
                self._json({"ok": False, "error_code": "VALIDATION_ERROR", "error": "missing job_id"}, status=400)
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()

            started = time.monotonic()
            try:
                while True:
                    if time.monotonic() - started > max_sse_duration_value:
                        payload = {
                            "ok": True,
                            "type": "stream_timeout",
                            "job_id": job_id,
                            "task_id": job_id,
                            "status": "stream_timeout",
                            "phase": "stream_timeout",
                            "status_message": "SSE stream duration elapsed; reconnect to continue receiving job updates.",
                            "retryable": True,
                            "transport": "sse",
                        }
                        self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        break

                    job = resolve_sse_job_value(job_id)
                    if not job:
                        self.wfile.write(f"data: {json.dumps({'ok': False, 'type': 'error', 'task_id': job_id, 'job_id': job_id, 'error': 'job not found'})}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        break

                    status = str(job.get("status", "unknown"))
                    progress = enrich_progress(dict(job.get("progress", {})))
                    progress.setdefault("task_id", job_id)
                    progress.setdefault("job_id", job_id)
                    progress.setdefault("status", status)
                    event_type = _sse_event_type(status)
                    payload = {
                        "ok": True,
                        "type": event_type,
                        "job_id": job_id,
                        "task_id": job_id,
                        "status": status,
                        "phase": progress.get("phase", ""),
                        "percent_complete": progress.get("percent_complete"),
                        "eta_seconds": progress.get("eta_seconds", 0),
                        "status_message": progress.get("status_message", ""),
                        "progress": progress,
                        "error": job.get("error", ""),
                    }
                    if event_type in {"complete", "error"}:
                        payload["result"] = job.get("result")
                    self.wfile.write(f"data: {json.dumps(payload, default=_json_default)}\n\n".encode("utf-8"))
                    self.wfile.flush()

                    if _is_terminal_status(status):
                        break

                    time.sleep(sse_push_interval_value)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def _handle_static_asset(self, request_path: str):
            if not self._is_allowed_local_request():
                self._json({"ok": False, "error_code": "ORIGIN_FORBIDDEN", "error": "forbidden local request origin"}, status=403)
                return
            # P0-4 fix: prevent path traversal (e.g. /assets/../../data/secrets.json)
            normalized = os.path.normpath(request_path)
            if ".." in normalized.split(os.sep) or not normalized.startswith(os.sep + "assets" + os.sep) and not normalized.startswith("/assets/"):
                self._json({"ok": False, "error_code": "ORIGIN_FORBIDDEN", "error": "forbidden asset path"}, status=403)
                return
            asset = resolve_static_asset_value(request_path)
            if asset is None:
                self._json({"ok": False, "error_code": "NOT_FOUND", "error": "not found"}, status=404)
                return
            data, content_type = asset
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self._send_security_headers()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _html(self, html: str, *, extra_headers: list[tuple[str, str]] | None = None):
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self._send_security_headers(html)
            for name, value in extra_headers or []:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, payload: dict, status: int = 200, *, extra_headers: list[tuple[str, str]] | None = None):
            data = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self._send_security_headers()
            # P0-2 fix: CORS headers consistent with _send_json via unified
            # set_cors_headers (now also sets ACAO for allowlisted origins).
            cors_headers: dict[str, str] = {}
            set_cors_headers(self.headers, cors_headers)
            for name, value in cors_headers.items():
                self.send_header(name, value)
            for name, value in extra_headers or []:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_security_headers(self, html: str | None = None):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                content_security_policy_for_html(html),
            )

    return Handler
