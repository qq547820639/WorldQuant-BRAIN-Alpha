"""HTTP handler factory for the local web console."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from typing import Any, Callable
import json
import time


def create_handler_class(
    *,
    server_version: str,
    max_body_bytes: int,
    dispatch_get: Callable[[Any, Any, Any], None],
    dispatch_post: Callable[[Any, Any, Any], None],
    dispatch_context: Callable[[], Any],
    web_session: Any,
    jobs: Any,
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
    resolve_sse_job_value = resolve_sse_job or (lambda job_id: jobs.get(job_id))
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
            dispatch_post(self, urlparse(self.path), dispatch_context())

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
                csrf_header=str(self.headers.get("X-Brain-Alpha-CSRF", "")),
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
                        self.wfile.write(f"data: {json.dumps({'ok': False, 'error': 'sse stream timeout'})}\n\n".encode("utf-8"))
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
                    self.wfile.write(f"data: {json.dumps(payload, default=str)}\n\n".encode("utf-8"))
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
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self._send_security_headers()
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


def _is_terminal_status(status: str) -> bool:
    return str(status or "").lower() in {
        "completed",
        "completed_with_warnings",
        "stopped",
        "failed",
        "cancelled",
        "canceled",
    }


def _sse_event_type(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized == "failed":
        return "error"
    if _is_terminal_status(normalized):
        return "complete"
    return "progress"
