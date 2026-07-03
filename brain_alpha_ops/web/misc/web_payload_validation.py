"""Request payload validation, server lifecycle, and sync-status payload helpers for the local web console.

Consolidated from the former ``web_payload_validation.py`` (request payload
validators + constants), ``web_server_lifecycle.py`` (``ThreadingHTTPServer``
subclass, free-port finder, ``serve`` / ``shutdown_server`` /
``smoke_test_server``), and ``web_sync_status_payload.py`` (sync job history,
official-context cache summary, and SQLite index snapshot helpers). The payload
section enforces bounds for every local web route body; the server-lifecycle
section hosts the canonical server factory and bind/shutdown helpers used by the
CLI entrypoint and the smoke test; the sync-status section produces small JSON
payloads consumed by the web console's status/snapshot endpoints.
"""

from __future__ import annotations

import json
import logging
import math
import re
import socket
import socketserver
import sys
import threading
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.redaction import redact_text
from brain_alpha_ops.research.expression_sqlite_index import ExpressionSqliteIndex
from brain_alpha_ops.research.record_sqlite_index import RecordSqliteIndex
from brain_alpha_ops.runtime_constants import ContextRefreshDefaults, WebDefaults

MAX_GENERATE_CANDIDATES = 100
MAX_ALPHA_ID_LENGTH = 128
MAX_BATCH_ALPHA_IDS = 100
MAX_ASSISTANT_TEXT_LENGTH = 200_000
MAX_SIMULATION_TIMEOUT_SECONDS = 3600
# P0-3 fix (2026-06-13): the Web payload layer must accept every value the
# canonical ``ALLOWED_SYNC_RANGES`` allows. The previous literal here (without
# ``1d``) silently dropped 1d-window requests from the agent tool path.
ALLOWED_SYNC_RANGES: frozenset[str] = ContextRefreshDefaults.ALLOWED_SYNC_RANGES
ALPHA_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


# ═══════════════════════ Payload validation helpers ════════════════════
def validate_json_object_payload(payload: dict[str, Any] | None) -> str:
    """Verify the request body is a JSON object. Returns "" on success or a user-facing error message."""
    if not isinstance(payload, dict):
        return "request body must be a JSON object"
    return ""


def validate_generate_candidates_payload(payload: dict[str, Any] | None) -> str:
    """Validate /api/candidates/generate payload: ensures count/candidates are well-formed numerics."""
    error = validate_json_object_payload(payload)
    if error:
        return error
    for field in ("count", "candidates"):
        if field not in payload or payload.get(field) in ("", None):
            continue
        try:
            count = int(payload[field])
        except (TypeError, ValueError):
            return f"{field} must be an integer between 1 and {MAX_GENERATE_CANDIDATES}"
        if count < 1 or count > MAX_GENERATE_CANDIDATES:
            return f"{field} must be between 1 and {MAX_GENERATE_CANDIDATES}"
    mode = str(payload.get("automation_mode") or payload.get("automationMode") or "").strip()
    if mode == "maintain_candidate_pool":
        for field, lower in (
            ("target_pool_size", 1),
            ("targetPoolSize", 1),
            ("existing_pool_size", 0),
            ("existingPoolSize", 0),
            ("pool_deficit", 0),
            ("poolDeficit", 0),
        ):
            if field not in payload or payload.get(field) in ("", None):
                continue
            try:
                value = int(payload[field])
            except (TypeError, ValueError):
                return f"{field} must be an integer between {lower} and {MAX_GENERATE_CANDIDATES}"
            if value < lower or value > MAX_GENERATE_CANDIDATES:
                return f"{field} must be between {lower} and {MAX_GENERATE_CANDIDATES}"
    return ""


def validate_submit_batch_payload(payload: dict[str, Any] | None) -> str:
    """Validate /api/candidates/submit_batch payload: enforces alpha_ids list, candidate rows, and bounds."""
    error = validate_json_object_payload(payload)
    if error:
        return error
    alpha_ids = payload.get("alpha_ids")
    if not isinstance(alpha_ids, list) or not alpha_ids:
        return "alpha_ids must be a non-empty list of Alpha IDs"
    if len(alpha_ids) > MAX_BATCH_ALPHA_IDS:
        return f"alpha_ids must contain at most {MAX_BATCH_ALPHA_IDS} items"
    for item in alpha_ids:
        error = validate_alpha_id_value(item, "alpha_ids[]")
        if error:
            return error
    raw_candidates = payload.get("submit_candidates")
    if raw_candidates is not None and not isinstance(raw_candidates, list):
        return "submit_candidates must be a list when provided"
    return validate_candidate_rows(raw_candidates, "submit_candidates")


def validate_check_batch_payload(payload: dict[str, Any] | None) -> str:
    """Validate /api/check_batch payload: candidate_ids list, optional fields, batch size limits."""
    if payload is None:
        return ""
    error = validate_json_object_payload(payload)
    if error:
        return error
    candidate_ids = payload.get("candidate_ids")
    if candidate_ids is not None:
        if not isinstance(candidate_ids, list):
            return "candidate_ids must be a list of Alpha IDs"
        for item in candidate_ids:
            error = validate_alpha_id_value(item, "candidate_ids[]")
            if error:
                return error
    mode = payload.get("mode")
    if mode is not None and str(mode) not in {"quick", "all"}:
        return "mode must be quick or all"
    for field in ("check_candidates", "candidates"):
        error = validate_candidate_rows(payload.get(field), field)
        if error:
            return error
    return ""


def validate_simulation_payload(payload: dict[str, Any] | None) -> str:
    """Validate /api/candidates/simulate payload: candidate_ids, workflow_plan, timeouts, and bounds."""
    error = validate_json_object_payload(payload)
    if error:
        return error
    error = _validate_candidate_id_list(payload.get("candidate_ids"), "candidate_ids", required=False)
    if error:
        return error
    workflow_plan = payload.get("workflow_plan")
    if workflow_plan is not None:
        if not isinstance(workflow_plan, dict):
            return "workflow_plan must be an object when provided"
        validator = workflow_plan.get("validator")
        if validator is not None:
            if not isinstance(validator, dict):
                return "workflow_plan.validator must be an object when provided"
            for field in ("next_candidate_ids", "candidate_ids"):
                error = _validate_candidate_id_list(
                    validator.get(field),
                    f"workflow_plan.validator.{field}",
                    required=False,
                )
                if error:
                    return error
    error = _validate_numeric_field(payload, "min_score", minimum=0.0, maximum=100.0, integer=False)
    if error:
        return error
    error = _validate_numeric_field(
        payload,
        "max_simulations",
        minimum=0,
        maximum=MAX_BATCH_ALPHA_IDS,
        integer=True,
    )
    if error:
        return error
    for field in ("poll_timeout", "stall_timeout"):
        error = _validate_numeric_field(
            payload,
            field,
            minimum=0.0,
            maximum=float(MAX_SIMULATION_TIMEOUT_SECONDS),
            integer=False,
        )
        if error:
            return error
    return ""


def validate_candidate_rows(value: Any, field: str) -> str:
    """Validate a list of candidate-row dicts; returns "" on success or a user-facing error message."""
    if value is None:
        return ""
    if not isinstance(value, list):
        return f"{field} must be a list when provided"
    if len(value) > MAX_BATCH_ALPHA_IDS:
        return f"{field} must contain at most {MAX_BATCH_ALPHA_IDS} items"
    for row in value:
        if not isinstance(row, dict):
            return f"{field}[] must be an object"
        for key in ("alpha_id", "official_alpha_id", "simulation_id"):
            if key not in row or row.get(key) in ("", None):
                continue
            error = validate_alpha_id_value(row.get(key), f"{field}[].{key}")
            if error:
                return error
    return ""


def _validate_candidate_id_list(value: Any, field: str, *, required: bool) -> str:
    """Validate a list of candidate/alpha IDs against the alpha-id pattern and length limits."""
    if value is None:
        return f"{field} must be a list of Alpha IDs" if required else ""
    if not isinstance(value, list):
        return f"{field} must be a list of Alpha IDs"
    if len(value) > MAX_BATCH_ALPHA_IDS:
        return f"{field} must contain at most {MAX_BATCH_ALPHA_IDS} items"
    for item in value:
        error = validate_alpha_id_value(item, f"{field}[]")
        if error:
            return error
    return ""


def _validate_numeric_field(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int | float,
    maximum: int | float,
    integer: bool,
) -> str:
    """Validate an optional numeric field with bounds; treats empty/None as absent."""
    if field not in payload or payload.get(field) in ("", None):
        return ""
    value = payload.get(field)
    if isinstance(value, bool):
        expected = "integer" if integer else "number"
        return f"{field} must be a finite {expected} between {minimum:g} and {maximum:g}"
    expected = "integer" if integer else "number"
    try:
        numeric_float = float(value)
    except (TypeError, ValueError):
        return f"{field} must be a finite {expected} between {minimum:g} and {maximum:g}"
    if not math.isfinite(numeric_float):
        return f"{field} must be a finite {expected} between {minimum:g} and {maximum:g}"
    if integer and not numeric_float.is_integer():
        return f"{field} must be a finite integer between {minimum:g} and {maximum:g}"
    numeric = int(numeric_float) if integer else numeric_float
    if numeric < minimum or numeric > maximum:
        return f"{field} must be a finite {expected} between {minimum:g} and {maximum:g}"
    return ""


def validate_job_cancel_payload(payload: dict[str, Any] | None, *, field: str = "job_id") -> str:
    """Validate /api/{job}/cancel payloads: ensures job_id is a well-formed non-empty string."""
    error = validate_json_object_payload(payload)
    if error:
        return error
    job_id = payload.get(field)
    if not isinstance(job_id, str) or not job_id.strip():
        return f"{field} must be a non-empty string"
    if len(job_id.strip()) > MAX_ALPHA_ID_LENGTH:
        return f"{field} must be {MAX_ALPHA_ID_LENGTH} characters or fewer"
    if not ALPHA_ID_PATTERN.fullmatch(job_id.strip()):
        return f"{field} may only contain letters, numbers, underscore, dash, dot, or colon"
    return ""


def validate_assistant_text_payload(payload: dict[str, Any] | None) -> str:
    """Validate /api/assistant/parse payload: ensures raw_output or text is a non-empty bounded string."""
    error = validate_json_object_payload(payload)
    if error:
        return error
    raw_output = payload.get("raw_output") if payload.get("raw_output") is not None else payload.get("text")
    if not isinstance(raw_output, str) or not raw_output.strip():
        return "raw_output or text must be a non-empty string"
    if len(raw_output) > MAX_ASSISTANT_TEXT_LENGTH:
        return f"raw_output or text must be {MAX_ASSISTANT_TEXT_LENGTH} characters or fewer"
    return ""


def validate_assistant_guidance_save_payload(payload: dict[str, Any] | None) -> str:
    """Validate /api/assistant/guidance save payload: accepts either assistant_guidance object or raw text."""
    error = validate_json_object_payload(payload)
    if error:
        return error
    supplied_guidance = payload.get("assistant_guidance")
    if supplied_guidance is not None:
        if not isinstance(supplied_guidance, dict):
            return "assistant_guidance must be an object"
        if not supplied_guidance:
            return "assistant_guidance must not be empty"
        return ""
    raw_output = (
        payload.get("assistant_response")
        if payload.get("assistant_response") is not None
        else payload.get("raw_output")
        if payload.get("raw_output") is not None
        else payload.get("text")
    )
    if not isinstance(raw_output, str) or not raw_output.strip():
        return "assistant_response, raw_output, text, or assistant_guidance is required"
    if len(raw_output) > MAX_ASSISTANT_TEXT_LENGTH:
        return f"assistant_response, raw_output, or text must be {MAX_ASSISTANT_TEXT_LENGTH} characters or fewer"
    return ""


def validate_assistant_cross_review_payload(payload: dict[str, Any] | None) -> str:
    """Validate /api/assistant/cross_review payload: requires request_pack object and primary_response."""
    error = validate_json_object_payload(payload)
    if error:
        return error
    request_pack = payload.get("request_pack") if payload.get("request_pack") is not None else payload.get("request")
    if not isinstance(request_pack, dict):
        return "request_pack must be an object"
    if payload.get("primary_response") is None and payload.get("primary") is None:
        return "primary_response is required"
    return ""


def validate_alpha_action_payload(payload: dict[str, Any] | None) -> str:
    """Validate alpha-action payloads: accepts top-level alpha_id/official_alpha_id/simulation_id or a candidate object."""
    error = validate_json_object_payload(payload)
    if error:
        return error
    candidate = payload.get("candidate")
    if candidate is not None and not isinstance(candidate, dict):
        return "candidate must be an object when provided"
    for field in ("alpha_id", "official_alpha_id", "simulation_id"):
        if field in payload and payload.get(field) not in ("", None):
            error = validate_alpha_id_value(payload.get(field), field)
            if error:
                return error
    if isinstance(candidate, dict):
        for field in ("alpha_id", "official_alpha_id", "simulation_id"):
            if field in candidate and candidate.get(field) not in ("", None):
                error = validate_alpha_id_value(candidate.get(field), f"candidate.{field}")
                if error:
                    return error
    has_top_level_id = any(str(payload.get(field) or "").strip() for field in ("alpha_id", "official_alpha_id", "simulation_id"))
    has_candidate = isinstance(candidate, dict) and bool(candidate)
    if not has_top_level_id and not has_candidate:
        return "candidate or alpha_id is required"
    return ""


def validate_sync_alphas_payload(payload: dict[str, Any] | None) -> str:
    """Validate /api/sync_alphas payload: optional syncRange against the allowed ranges enum."""
    error = validate_json_object_payload(payload)
    if error:
        return error
    sync_range = payload.get("syncRange") if payload.get("syncRange") not in ("", None) else payload.get("range")
    if sync_range not in ("", None) and str(sync_range) not in ALLOWED_SYNC_RANGES:
        return "syncRange must be one of 3d, 7d, recent, 6months, all"
    return ""


def validate_alpha_id_value(value: Any, field: str) -> str:
    """Validate a single alpha/candidate/simulation ID against the canonical pattern and length."""
    if not isinstance(value, str):
        return f"{field} must be a string Alpha ID"
    text = value.strip()
    if not text:
        return f"{field} must be a non-empty Alpha ID"
    if len(text) > MAX_ALPHA_ID_LENGTH:
        return f"{field} must be {MAX_ALPHA_ID_LENGTH} characters or fewer"
    if not ALPHA_ID_PATTERN.fullmatch(text):
        return f"{field} may only contain letters, numbers, underscore, dash, dot, or colon"
    return ""


# ═══════════════════════ Server lifecycle helpers ══════════════════════
# Consolidated from web_server_lifecycle.py. The canonical server factory,
# free-port finder, and serve/shutdown/smoke-test helpers live here.
class SafeThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:
        _exc_type, exc, _tb = sys.exc_info()
        if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError)):
            return
        super().handle_error(request, client_address)

    def server_bind(self) -> None:
        # Avoid HTTPServer.server_bind -> socket.getfqdn reverse lookup, which
        # can raise UnicodeDecodeError on some Windows hosts.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host) if host else "localhost"
        self.server_port = int(port)


def find_free_port(start: int, *, host: str, scan_limit: int = 10000) -> int:
    upper = min(65535, start + max(1, scan_limit))
    for port in range(start, upper + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free local port found")


def display_host_for_bind(host: str) -> str:
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


def _server_port(server: ThreadingHTTPServer, fallback: int) -> int:
    port = getattr(server, "server_port", None)
    if isinstance(port, int) and port > 0:
        return port
    server_address = getattr(server, "server_address", None)
    if isinstance(server_address, tuple) and len(server_address) >= 2:
        try:
            resolved = int(server_address[1])
        except (TypeError, ValueError):
            pass
        else:
            if resolved >= 0:
                return resolved
    return fallback


def shutdown_server(server: ThreadingHTTPServer | None, stop_event: threading.Event) -> None:
    stop_event.set()
    if server:
        server.shutdown()
        server.server_close()


def serve(
    *,
    port: int | None,
    open_browser: bool,
    host: str,
    default_port: int,
    handler_class: type,
    stop_event: threading.Event,
    configure_session_policy: Callable[..., None],
    normalize_host: Callable[[str | None], str],
    loopback_bind_hosts: set[str] | frozenset[str],
    allow_remote: bool,
    session_ttl_seconds: int | None = None,
    allow_multiple_sessions: bool | None = None,
    secure_cookies: bool | None = None,
    server_factory: Callable[[tuple[str, int], type], ThreadingHTTPServer] = SafeThreadingHTTPServer,
    browser_open: Callable[[str], Any] = webbrowser.open,
    thread_factory: Callable[..., threading.Thread] = threading.Thread,
) -> tuple[str, ThreadingHTTPServer]:
    stop_event.clear()
    configure_session_policy(session_ttl_seconds, allow_multiple_sessions, secure_cookies)
    bind_host = normalize_host(host)
    if bind_host not in loopback_bind_hosts and not allow_remote:
        raise ValueError("remote web bind requires web.allow_remote=true")
    requested_port = default_port if port is None else port
    if requested_port == 0:
        bind_port = 0
    else:
        try:
            bind_port = find_free_port(start=requested_port, host=bind_host)
        except RuntimeError:
            if server_factory is SafeThreadingHTTPServer:
                raise
            # Unit tests and embedding callers may supply a fake server factory
            # that does not need a real socket probe.
            bind_port = requested_port
    server = server_factory((bind_host, bind_port), handler_class)
    actual_port = _server_port(server, bind_port)
    url = f"http://{display_host_for_bind(bind_host)}:{actual_port}/"
    if open_browser:
        browser_open(url)
    thread_factory(target=server.serve_forever, daemon=True).start()
    return url, server


def smoke_test_server(
    *,
    port: int | None,
    default_port: int,
    serve_func: Callable[..., str],
    shutdown_func: Callable[[], None],
    parse_cookies: Callable[[str], dict[str, str]],
    cookie_name: str,
    csrf_for_session: Callable[[str], str],
    urlopen: Callable[..., Any] = urllib.request.urlopen,
    request_factory: Callable[..., urllib.request.Request] = urllib.request.Request,
) -> dict[str, Any]:
    url = serve_func(port=default_port if port is None else port, open_browser=False)
    try:
        root_response = urlopen(url, timeout=WebDefaults.SMOKE_TEST_TIMEOUT)
        root_html = root_response.read().decode("utf-8", errors="replace")
        if "BRAIN Alpha Ops" not in root_html:
            raise RuntimeError("web root did not render console HTML")
        cookie_header = root_response.headers.get("Set-Cookie", "")
        session_id = parse_cookies(cookie_header).get(cookie_name, "")
        csrf_token = csrf_for_session(session_id)
        if not session_id or not csrf_token:
            raise RuntimeError("web root did not issue a valid local session")

        request = request_factory(
            url + "api/config",
            headers={
                "Cookie": f"{cookie_name}={session_id}",
                "X-Brain-Alpha-CSRF": csrf_token,
            },
        )
        with urlopen(request, timeout=WebDefaults.SMOKE_TEST_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("ok") is not True:
            raise RuntimeError(f"config API smoke check failed: {payload}")
        return {"ok": True, "url": url, "config_ok": True}
    finally:
        shutdown_func()


# ═══════════════════════ Sync status & SQLite index payload helpers ══════
# Consolidated from web_sync_status_payload.py.

logger = logging.getLogger(__name__)

LoadConfig = Callable[[], RunConfig]
WebError = Callable[[Exception, str], dict[str, Any]]


# ═══════════════════════ Sync status payload helpers ═══════════════════════


def with_sync_history(payload: dict[str, Any], ctx: Any, *, limit: int) -> dict[str, Any]:
    if limit <= 0:
        return {**payload, "sync_history": []}
    try:
        rows = ctx.sync_jobs.all(limit=limit)
    except Exception as exc:
        logger.warning("failed to read sync job history", exc_info=True)
        return {**payload, "sync_history": [], "sync_history_error": redact_text(str(exc))}
    return {
        **payload,
        "sync_history": [
            sync_history_item(job_id, row, ctx)
            for job_id, row in rows
            if isinstance(row, dict)
        ],
    }


def sync_history_item(job_id: str, row: dict[str, Any], ctx: Any) -> dict[str, Any]:
    progress = ctx.enrich_progress(dict(row.get("progress") or {}))
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    status = str(row.get("status") or progress.get("status") or "unknown")
    updated_at = _float_value(row.get("updated_at"))
    updated_at_ms = int(updated_at * 1000) if updated_at > 0 else _int_value(progress.get("updated_at_ms"))
    message = str(progress.get("status_message") or progress.get("message") or row.get("error") or "").strip()
    return {
        "job_id": job_id,
        "task_id": job_id,
        "status": status,
        "phase": str(progress.get("phase") or row.get("phase") or ""),
        "status_message": redact_text(message),
        "updated_at": updated_at,
        "updated_at_ms": updated_at_ms,
        "context_only": bool(progress.get("context_only") or result.get("context_only")),
        "scanned": _first_int(progress, result, "scanned"),
        "total": _first_int(progress, result, "total", "total_count"),
        "api_reported_total": _first_int(progress, result, "api_reported_total"),
        "filter_window_count": _first_int(progress, result, "filter_window_count"),
        "added": _first_int(progress, result, "added"),
        "updated": _first_int(progress, result, "updated"),
        "skipped": _first_int(progress, result, "skipped"),
        "failed": _first_int(progress, result, "failed"),
    }


def with_official_context_cache(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    try:
        counts = ctx.official_context_file_counts()
    except Exception as exc:
        logger.warning("failed to read official context cache summary for sync status", exc_info=True)
        return {**payload, "official_context_cache": {"ok": False, "error": redact_text(str(exc))}}
    cache = {
        "ok": True,
        "fields_count": int(counts.get("fields_count", 0) or 0),
        "operators_count": int(counts.get("operators_count", 0) or 0),
        "datasets_count": int(counts.get("datasets_count", 0) or 0),
    }
    manifest = counts.get("context_cache_manifest")
    if isinstance(manifest, dict):
        cache["manifest"] = {
            "complete": bool(manifest.get("complete")),
            "is_stale": bool(manifest.get("is_stale")),
            "missing_files": list(manifest.get("missing_files") or []),
            "stale_files": list(manifest.get("stale_files") or manifest.get("expired_files") or []),
            "invalid_files": list(manifest.get("invalid_files") or []),
            "record_counts": dict(manifest.get("record_counts") or {}),
        }
    return {**payload, "official_context_cache": cache}


def _first_int(progress: dict[str, Any], result: dict[str, Any], *keys: str) -> int:
    for source in (progress, result):
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = _int_value(source.get(key))
            if value > 0:
                return value
    return 0


def _int_value(value: Any) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _float_value(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number > 0 else 0.0


# ═══════════════════════ SQLite index web helpers ══════════════════════════


def _default_web_error(exc: Exception, error_code: str) -> dict[str, Any]:
    from brain_alpha_ops.redaction import redact_error_message
    return {"ok": False, "error_code": error_code, "error": redact_error_message(exc)}


def sqlite_index_snapshot(
    *,
    top_n: int = 10,
    load_config: LoadConfig = load_run_config,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        storage_dir = config.ops.storage_dir
        expression_index = ExpressionSqliteIndex(storage_dir).summary(top_n=top_n)
        record_index = RecordSqliteIndex(storage_dir).summary()
        return {
            "ok": True,
            "schema_version": "sqlite_index_snapshot.v1",
            "source": "sqlite_index_cache",
            "storage_dir": str(storage_dir),
            "expression_index": expression_index,
            "record_index": record_index,
            "has_missing_index": expression_index.get("ok") is False or record_index.get("ok") is False,
            "has_stale_index": bool(expression_index.get("is_stale") or record_index.get("is_stale")),
        }
    except Exception as exc:
        return web_error(exc, "SQLITE_INDEX_SNAPSHOT_ERROR")


def sqlite_expression_lookup_payload(
    *,
    expression: str,
    top_n: int = 10,
    min_similarity: float = 0.75,
    max_scan_rows: int = 2000,
    load_config: LoadConfig = load_run_config,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        return ExpressionSqliteIndex(config.ops.storage_dir).lookup(
            expression,
            top_n=top_n,
            min_similarity=min_similarity,
            max_scan_rows=max_scan_rows,
        )
    except Exception as exc:
        return web_error(exc, "SQLITE_EXPRESSION_LOOKUP_ERROR")


def sqlite_record_lookup_payload(
    *,
    alpha_id: str,
    limit: int = 50,
    load_config: LoadConfig = load_run_config,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        return RecordSqliteIndex(config.ops.storage_dir).lookup_alpha(alpha_id, limit=limit)
    except Exception as exc:
        return web_error(exc, "SQLITE_RECORD_LOOKUP_ERROR")
