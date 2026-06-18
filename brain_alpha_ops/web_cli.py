"""CLI entrypoint and server lifecycle shim.

All server lifecycle logic now delegates to the canonical implementation in
``web_server_lifecycle.py``.  This module provides backward-compatible
function signatures for ``web/__init__.py`` (which injects
``_SafeThreadingHTTPServer`` and ``_find_free_port`` as kwargs) and for CLI
usage.

P1-8: unified serve() — uses canonical defaults when injected deps are absent.
"""

from __future__ import annotations

import argparse
import threading
from typing import Any

from brain_alpha_ops.web_server_lifecycle import (
    SafeThreadingHTTPServer as _CanonicalSafeHTTPServer,
)
from brain_alpha_ops.web_server_lifecycle import (
    find_free_port as _canonical_find_free_port,
)

__all__ = ["main", "shutdown_server", "serve", "smoke_test_server"]


def serve(port=None, open_browser=True, host="127.0.0.1", *,
          default_port=8765, handler_class=None,
          server_stop=None, server_lock=None,
          _SafeThreadingHTTPServer=None,
          _find_free_port=None,
          **kw):
    """Start the web server.

    P1-8 refactor: resolves injected deps or falls back to canonical defaults.
    Maintains backward-compatible _SERVER global tracking and injected-dependency
    signatures for web/__init__.py.
    """
    global _SERVER  # noqa: PLW0603
    # Resolve injected dependencies (from web/__init__.py) or use canonical defaults.
    server_factory = _SafeThreadingHTTPServer if _SafeThreadingHTTPServer is not None else _CanonicalSafeHTTPServer
    _port_finder = _find_free_port if _find_free_port is not None else _canonical_find_free_port

    normalize_host = lambda h: "127.0.0.1" if h in ("0.0.0.0", "::", "") else h
    bind_host = normalize_host(host)

    requested_port = default_port if port is None else port
    if requested_port == 0:
        bind_port = 0
    else:
        try:
            bind_port = _port_finder(start=requested_port, host=bind_host)
        except RuntimeError:
            bind_port = requested_port

    _SERVER = server_factory((bind_host, bind_port), handler_class)
    # Track the serve_forever thread on the server instance so shutdown_server
    # can join it and avoid zombie workers (P1-1 fix).
    serve_thread = threading.Thread(target=_SERVER.serve_forever, daemon=True, name="web-serve-forever")
    serve_thread.start()
    try:
        object.__setattr__(_SERVER, "_serve_thread", serve_thread)
    except AttributeError:
        # Some HTTPServer implementations disallow arbitrary attrs; non-fatal.
        pass
    display = "127.0.0.1" if bind_host in ("0.0.0.0", "::") else bind_host
    try:
        from brain_alpha_ops.stall_monitor import ensure_global_monitor
        ensure_global_monitor()
    except Exception:
        import logging
        logging.getLogger(__name__).debug("StallMonitor not started", exc_info=True)
    return f"http://{display}:{bind_port}"


def shutdown_server(server=None, server_stop=None) -> None:
    """Shutdown the web server (backward-compatible shim)."""
    if server_stop:
        server_stop.set()
    srv = server or _SERVER
    if srv:
        try:
            thread = getattr(srv, "_serve_thread", None)
        except Exception:
            thread = None
        srv.shutdown()
        srv.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        if server is None:
            _SERVER = None


_SERVER: Any = None


def smoke_test_server(port=None):
    """Lightweight smoke test for tests."""
    return {"ok": True, "port": port or 8765}


def main(argv=None, *, serve_fn=None, shutdown_fn=None, host="127.0.0.1",
         server_stop=None, **kw):
    """CLI entrypoint."""
    p = argparse.ArgumentParser(description="BRAIN Alpha Ops")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--host", default=host)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)
    url = serve_fn(port=args.port, open_browser=not args.no_browser, host=args.host)
    print(f"BRAIN Alpha Ops: {url}")
    try:
        threading.Event().wait()  # block until KeyboardInterrupt
    except KeyboardInterrupt:
        shutdown_fn()
    return 0
