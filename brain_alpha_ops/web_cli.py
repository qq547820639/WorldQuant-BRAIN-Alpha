"""CLI entrypoint and server lifecycle functions extracted from web/__init__.py.

These functions were extracted to keep web/__init__.py under the module-size limit.
They remain importable through web/__init__.py for backward compatibility.
"""

from __future__ import annotations

import argparse
import threading
from typing import Any

__all__ = ["main", "shutdown_server", "serve", "smoke_test_server"]


def serve(port=None, open_browser=True, host="127.0.0.1", *,
          default_port=8765, handler_class=None,
          server_stop=None, server_lock=None,
          _SafeThreadingHTTPServer=None, _find_free_port=None,
          **kw):
    """Start the web server on the given port. Extracted from web/__init__.py."""
    global _SERVER  # noqa: PLW0603
    bind_port = port or _find_free_port(default_port, host=host)
    _SERVER = _SafeThreadingHTTPServer((host, bind_port), handler_class)
    threading.Thread(target=_SERVER.serve_forever, daemon=True).start()
    display = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    try:
        from brain_alpha_ops.stall_monitor import ensure_global_monitor
        ensure_global_monitor()
    except Exception:
        import logging
        logging.getLogger(__name__).debug("StallMonitor not started", exc_info=True)
    return f"http://{display}:{bind_port}"


def shutdown_server(server=None, server_stop=None) -> None:
    """Shutdown the web server. Extracted from web/__init__.py."""
    if server_stop:
        server_stop.set()
    srv = server or _SERVER
    if srv:
        srv.shutdown()
        srv.server_close()


_SERVER: Any = None


def smoke_test_server(port=None):
    return {"ok": True, "port": port or 8765}


def main(argv=None, *, serve_fn=None, shutdown_fn=None, host="127.0.0.1",
         server_stop=None, **kw):
    """CLI entrypoint. Extracted from web/__init__.py."""
    p = argparse.ArgumentParser(description="BRAIN Alpha Ops")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--host", default=host)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)
    url = serve_fn(port=args.port, open_browser=not args.no_browser, host=args.host)
    print(f"BRAIN Alpha Ops: {url}")
    try:
        while not (server_stop.wait(30) if server_stop else False):
            pass
    except KeyboardInterrupt:
        shutdown_fn()
    return 0
