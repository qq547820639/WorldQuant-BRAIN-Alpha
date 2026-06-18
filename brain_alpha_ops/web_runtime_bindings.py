"""Compatibility exports for consolidated web facade bindings."""

from __future__ import annotations

import threading

from brain_alpha_ops.runtime_constants import WebDefaults as _WebDefaults
from brain_alpha_ops.web_candidates.bindings import *  # noqa: F401,F403


def serve(
    port=None,
    open_browser=True,
    host=_WebDefaults.HOST,
    session_ttl_seconds=None,
    allow_multiple_sessions=None,
    allow_remote=False,
    secure_cookies=None,
):
    from brain_alpha_ops import web

    url = web._runtime_facade.serve(
        web._app_context(),
        port=port,
        open_browser=open_browser,
        host=host,
        session_ttl_seconds=session_ttl_seconds,
        allow_multiple_sessions=allow_multiple_sessions,
        allow_remote=allow_remote,
        secure_cookies=secure_cookies,
    )
    _start_watchdog_sweep_thread(web)
    return url


def _start_watchdog_sweep_thread(web) -> None:
    stop_event = getattr(web, "SERVER_STOP", None)
    if stop_event is None:
        return
    existing = getattr(web, "_WATCHDOG_SWEEP_THREAD", None)
    if existing is not None and existing.is_alive():
        return
    thread = threading.Thread(target=_watchdog_sweep_loop, args=(web, stop_event), daemon=True)
    setattr(web, "_WATCHDOG_SWEEP_THREAD", thread)
    thread.start()


def _watchdog_sweep_loop(web, stop_event) -> None:
    interval = _watchdog_sweep_interval(web)
    while not stop_event.wait(interval):
        _watchdog_sweep_once(web)


def _watchdog_sweep_interval(web) -> float:
    timeouts: list[float] = []
    for store in _watchdog_stores(web):
        try:
            timeout = float(getattr(store, "watchdog_timeout_seconds", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if timeout > 0:
            timeouts.append(timeout)
    if not timeouts:
        return 30.0
    return max(5.0, min(30.0, min(timeouts) / 2.0))


def _watchdog_sweep_once(web) -> int:
    changed = 0
    for store in _watchdog_stores(web):
        sweep = getattr(store, "watchdog_sweep", None)
        if not callable(sweep):
            continue
        changed += int(sweep() or 0)
    return changed


def _watchdog_stores(web) -> tuple[object, ...]:
    return tuple(
        store
        for store in (
            getattr(web, "JOBS", None),
            getattr(web, "SYNC_JOBS", None),
            getattr(web, "CHECK_JOBS", None),
            getattr(web, "ASYNC_JOBS", None),
        )
        if store is not None
    )
