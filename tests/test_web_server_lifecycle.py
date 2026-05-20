from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from brain_alpha_ops.web_server_lifecycle import display_host_for_bind, serve, smoke_test_server


class _Server:
    def __init__(self, address, handler_class):
        self.address = address
        self.handler_class = handler_class
        self.served = False
        self.shutdown_called = False
        self.closed = False

    def serve_forever(self):
        self.served = True

    def shutdown(self):
        self.shutdown_called = True

    def server_close(self):
        self.closed = True


class _Thread:
    def __init__(self, *, target, daemon):
        self.target = target
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True
        self.target()


class _StopEvent:
    def __init__(self):
        self.cleared = False
        self.set_called = False

    def clear(self):
        self.cleared = True

    def set(self):
        self.set_called = True


def test_serve_normalizes_host_checks_remote_policy_and_starts_thread():
    stop_event = _StopEvent()
    opened = []
    configured = []
    servers = []

    def server_factory(address, handler_class):
        server = _Server(address, handler_class)
        servers.append(server)
        return server

    url, server = serve(
        port=9999,
        open_browser=True,
        host="",
        default_port=8765,
        handler_class=object,
        stop_event=stop_event,
        configure_session_policy=lambda ttl, multiple: configured.append((ttl, multiple)),
        normalize_host=lambda host: "127.0.0.1" if not host else host,
        loopback_bind_hosts={"127.0.0.1"},
        allow_remote=False,
        session_ttl_seconds=60,
        allow_multiple_sessions=False,
        server_factory=server_factory,
        browser_open=opened.append,
        thread_factory=lambda **kwargs: _Thread(**kwargs),
    )

    assert url == "http://127.0.0.1:9999/"
    assert server is servers[0]
    assert server.address == ("127.0.0.1", 9999)
    assert server.served is True
    assert stop_event.cleared is True
    assert configured == [(60, False)]
    assert opened == [url]

    with pytest.raises(ValueError, match="allow_remote"):
        serve(
            port=9998,
            open_browser=False,
            host="0.0.0.0",
            default_port=8765,
            handler_class=object,
            stop_event=_StopEvent(),
            configure_session_policy=lambda ttl, multiple: None,
            normalize_host=lambda host: host or "127.0.0.1",
            loopback_bind_hosts={"127.0.0.1"},
            allow_remote=False,
            server_factory=server_factory,
            thread_factory=lambda **kwargs: _Thread(**kwargs),
        )


def test_display_host_for_bind_uses_loopback_for_wildcard():
    assert display_host_for_bind("0.0.0.0") == "127.0.0.1"
    assert display_host_for_bind("::") == "127.0.0.1"
    assert display_host_for_bind("localhost") == "localhost"


class _Response:
    def __init__(self, body, headers=None):
        self.body = body
        self.headers = headers or {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_smoke_test_server_exercises_root_and_config_api():
    calls = []
    shutdowns = []

    def fake_urlopen(target, timeout):
        calls.append(target)
        if isinstance(target, str):
            return _Response(b"<html>BRAIN Alpha Ops</html>", {"Set-Cookie": "brain_alpha_ops_session=s1; Path=/"})
        return _Response(json.dumps({"ok": True}).encode("utf-8"))

    result = smoke_test_server(
        port=7777,
        default_port=8765,
        serve_func=lambda **kwargs: "http://127.0.0.1:7777/",
        shutdown_func=lambda: shutdowns.append(True),
        parse_cookies=lambda header: {"brain_alpha_ops_session": "s1"},
        cookie_name="brain_alpha_ops_session",
        csrf_for_session=lambda session_id: "csrf1",
        urlopen=fake_urlopen,
        request_factory=lambda url, headers: SimpleNamespace(url=url, headers=headers),
    )

    assert result == {"ok": True, "url": "http://127.0.0.1:7777/", "config_ok": True}
    assert shutdowns == [True]
    assert calls[1].headers["X-Brain-Alpha-CSRF"] == "csrf1"


def test_smoke_test_server_always_shutdowns_on_failure():
    shutdowns = []

    with pytest.raises(RuntimeError, match="valid local session"):
        smoke_test_server(
            port=None,
            default_port=8765,
            serve_func=lambda **kwargs: "http://127.0.0.1:8765/",
            shutdown_func=lambda: shutdowns.append(True),
            parse_cookies=lambda header: {},
            cookie_name="brain_alpha_ops_session",
            csrf_for_session=lambda session_id: "",
            urlopen=lambda target, timeout: _Response(b"<html>BRAIN Alpha Ops</html>", {"Set-Cookie": ""}),
        )

    assert shutdowns == [True]
