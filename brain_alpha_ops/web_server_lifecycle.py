"""Server lifecycle helpers for the local web console."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import socket
import socketserver
import threading
from typing import Any, Callable
import urllib.request
import webbrowser


class SafeThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def server_bind(self) -> None:
        # Avoid HTTPServer.server_bind -> socket.getfqdn reverse lookup, which
        # can raise UnicodeDecodeError on some Windows hosts.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host if host else "localhost"
        self.server_port = port


def find_free_port(start: int, *, host: str, scan_limit: int = 100) -> int:
    for port in range(start, start + scan_limit):
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
    configure_session_policy: Callable[[int | None, bool | None], None],
    normalize_host: Callable[[str | None], str],
    loopback_bind_hosts: set[str] | frozenset[str],
    allow_remote: bool,
    session_ttl_seconds: int | None = None,
    allow_multiple_sessions: bool | None = None,
    server_factory: Callable[[tuple[str, int], type], ThreadingHTTPServer] = SafeThreadingHTTPServer,
    browser_open: Callable[[str], Any] = webbrowser.open,
    thread_factory: Callable[..., threading.Thread] = threading.Thread,
) -> tuple[str, ThreadingHTTPServer]:
    stop_event.clear()
    configure_session_policy(session_ttl_seconds, allow_multiple_sessions)
    bind_host = normalize_host(host)
    if bind_host not in loopback_bind_hosts and not allow_remote:
        raise ValueError("remote web bind requires web.allow_remote=true")
    bind_port = find_free_port(start=port or default_port, host=bind_host)
    server = server_factory((bind_host, bind_port), handler_class)
    url = f"http://{display_host_for_bind(bind_host)}:{bind_port}/"
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
    url = serve_func(port=port or default_port, open_browser=False)
    try:
        root_response = urlopen(url, timeout=5)
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
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("ok") is not True:
            raise RuntimeError(f"config API smoke check failed: {payload}")
        return {"ok": True, "url": url, "config_ok": True}
    finally:
        shutdown_func()
