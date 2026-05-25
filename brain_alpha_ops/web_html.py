"""HTML loading and rendering helpers for the local web console."""

from __future__ import annotations

import threading
from pathlib import Path

from brain_alpha_ops.web_csp import (
    content_security_policy_for_html as _content_security_policy_for_html,
    script_hash_sources,
    style_hash_sources,
)


CSRF_TOKEN_PLACEHOLDER = "__BRAIN_ALPHA_OPS_CSRF_TOKEN__"
STREAM_TOKEN_PLACEHOLDER = "__BRAIN_ALPHA_OPS_STREAM_TOKEN__"
MISSING_TEMPLATE_HTML = "<!doctype html><html><body><h1>Template not found</h1></body></html>"

_HTML_CACHE = ""
_HTML_LOCK = threading.RLock()


def default_html_path() -> Path:
    return Path(__file__).resolve().parent / "web" / "index.html"


def load_html(path: Path | None = None) -> str:
    global _HTML_CACHE
    if path is None:
        with _HTML_LOCK:
            if _HTML_CACHE:
                return _HTML_CACHE
            template_path = default_html_path()
            html = template_path.read_text(encoding="utf-8") if template_path.is_file() else MISSING_TEMPLATE_HTML
            _HTML_CACHE = html
            return html
    template_path = path
    with _HTML_LOCK:
        return template_path.read_text(encoding="utf-8") if template_path.is_file() else MISSING_TEMPLATE_HTML


def reset_html_cache() -> None:
    global _HTML_CACHE
    with _HTML_LOCK:
        _HTML_CACHE = ""


def render_html(csrf_token: str, stream_token: str, html: str | None = None) -> str:
    source = html if html is not None else load_html()
    return source.replace(CSRF_TOKEN_PLACEHOLDER, csrf_token).replace(STREAM_TOKEN_PLACEHOLDER, stream_token)


def content_security_policy_for_html(html: str | None = None) -> str:
    return _content_security_policy_for_html(html if html is not None else load_html())
