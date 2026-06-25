"""Server lifecycle, CLI entry point, and stub functions."""
from __future__ import annotations

import json
import os
import sys
from contextlib import nullcontext

from ._logging import logger


def _server_lock(web):
    lock = getattr(web, "SERVER_LOCK", None)
    return lock if hasattr(lock, "__enter__") else nullcontext()


def shutdown_server(web):
    with _server_lock(web):
        server = web.SERVER
        web.SERVER = None
    web._shutdown_server_service(server, web.SERVER_STOP)


def serve(
    web,
    port: int | None = None,
    open_browser: bool = True,
    host: str | None = None,
    session_ttl_seconds: int | None = None,
    allow_multiple_sessions: bool | None = None,
    allow_remote: bool = False,
    secure_cookies: bool | None = None,
) -> str:
    host = web.HOST if host is None else host
    run_config = web.load_run_config()
    web.web_session.set_remote_policy(
        allow_remote=allow_remote,
        admin_token_env=str(getattr(run_config.web, "admin_token_env", web.web_session.DEFAULT_ADMIN_TOKEN_ENV)),
    )
    web.web_session.require_remote_admin_token()
    web.configure_session_policy(
        session_ttl_seconds,
        allow_multiple_sessions,
        secure_cookies=bool(allow_remote) if secure_cookies is None else secure_cookies,
    )
    url, server = web._serve_service(
        port=port,
        open_browser=open_browser,
        host=host,
        default_port=web.DEFAULT_PORT,
        handler_class=web.Handler,
        stop_event=web.SERVER_STOP,
        configure_session_policy=web.configure_session_policy,
        normalize_host=web.normalize_host,
        loopback_bind_hosts=web.LOOPBACK_BIND_HOSTS,
        allow_remote=allow_remote,
        session_ttl_seconds=session_ttl_seconds,
        allow_multiple_sessions=allow_multiple_sessions,
        secure_cookies=web.web_session.SESSION_MANAGER.secure_cookies,
    )
    with _server_lock(web):
        web.SERVER = server
    return url


def smoke_test_server(web, port: int | None = None) -> dict:
    return web._smoke_test_server_service(
        port=port,
        default_port=web.DEFAULT_PORT,
        serve_func=web.serve,
        shutdown_func=web.shutdown_server,
        parse_cookies=web._parse_cookies,
        cookie_name=web.SESSION_COOKIE_NAME,
        csrf_for_session=web._csrf_for_session,
    )


def main(web, argv: list[str] | None = None) -> int:
    import argparse

    def safe_print(message: str) -> None:
        stream = getattr(sys, "stdout", None)
        if stream is None:
            return
        try:
            print(message)
        except Exception:
            logger.warning("failed to write web runtime CLI output", exc_info=True)
            return

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--frontend", choices=("inline", "react"), default="")
    args = parser.parse_args(argv)
    if args.frontend:
        env_name = getattr(getattr(web, "web_html", None), "WEB_FRONTEND_ENV", "BRAIN_ALPHA_OPS_WEB_FRONTEND")
        os.environ[env_name] = args.frontend
        reset_cache = getattr(getattr(web, "web_html", None), "reset_html_cache", None)
        if callable(reset_cache):
            reset_cache()
    run_config = web.load_run_config(args.config or None)
    selected_port = run_config.web.port if args.port is None else args.port
    if args.smoke_test:
        web.config_from_payload({"environment": "production"})
        result = web.smoke_test_server(port=selected_port)
        safe_print(json.dumps({"ok": True, "status": "web ready", **result}, ensure_ascii=False))
        return 0
    url = web.serve(
        port=selected_port,
        open_browser=run_config.web.open_browser and not args.no_browser,
        host=run_config.web.host,
        session_ttl_seconds=run_config.web.session_ttl_seconds,
        allow_multiple_sessions=run_config.web.allow_multiple_sessions,
        allow_remote=run_config.web.allow_remote,
        secure_cookies=run_config.web.secure_cookies or run_config.web.allow_remote,
    )
    safe_print("BRAIN Alpha Ops 已启动")
    safe_print(f"访问地址：{url}")
    safe_print("关闭此窗口或按 Ctrl+C 可停止本地服务。")
    try:
        while not web.SERVER_STOP.wait(3600):
            pass
    except KeyboardInterrupt:
        web.shutdown_server()
    return 0


def compute_run_stats(data, run_config):
    """Compute summary statistics from pipeline results."""
    return {"candidates": 0, "simulations": 0, "submissions": 0}


def status_category(*args, **kwargs):
    """Return status category string."""
    return "idle"
