"""Web runtime server and lifecycle bindings."""

from __future__ import annotations

import threading

from brain_alpha_ops.runtime_constants import WebDefaults as _WebDefaults

from ._helpers import _app_context, _runtime_facade, _web


def test_connection(payload):
    return _runtime_facade().test_connection(_app_context(), payload)


def handler_dispatch_context():
    return _runtime_facade().handler_dispatch_context(_app_context())


def lookup_sse_job(job_id):
    return _runtime_facade().lookup_sse_job(_app_context(), job_id)


def run_job(job_id, payload):
    return _runtime_facade().run_job(_app_context(), job_id, payload)


def start_thread(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def compute_run_stats(data, run_config):
    return _web()._compute_run_stats_service(data, run_config)


def lifecycle_from_job(job):
    return _runtime_facade().lifecycle_from_job(_app_context(), job)


def alpha_lifecycle_history(**kwargs):
    return _runtime_facade().alpha_lifecycle_history(_app_context(), **kwargs)


def maybe_archive_lifecycle():
    return _runtime_facade().maybe_archive_lifecycle(_app_context())


def find_free_port(start=_WebDefaults.PORT, host=_WebDefaults.HOST):
    return _runtime_facade().find_free_port(_app_context(), start, host)


def shutdown_server():
    return _runtime_facade().shutdown_server(_app_context())


def serve(
    port=None,
    open_browser=True,
    host=_WebDefaults.HOST,
    session_ttl_seconds=None,
    allow_multiple_sessions=None,
    allow_remote=False,
    secure_cookies=None,
):
    return _runtime_facade().serve(
        _app_context(),
        port=port,
        open_browser=open_browser,
        host=host,
        session_ttl_seconds=session_ttl_seconds,
        allow_multiple_sessions=allow_multiple_sessions,
        allow_remote=allow_remote,
        secure_cookies=secure_cookies,
    )


def smoke_test_server(port=None):
    return _runtime_facade().smoke_test_server(_app_context(), port=port)


def main(argv=None):
    return _runtime_facade().main(_app_context(), argv)
