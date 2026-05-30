"""HTML loading and rendering helpers for the local web console."""

from __future__ import annotations

import mimetypes
import os
import re
import threading
from pathlib import Path
from urllib.parse import unquote

from brain_alpha_ops.web_csp import (
    content_security_policy_for_html as _content_security_policy_for_html,
    script_hash_sources,
    style_hash_sources,
)


CSRF_TOKEN_PLACEHOLDER = "__BRAIN_ALPHA_OPS_CSRF_TOKEN__"
STREAM_TOKEN_PLACEHOLDER = "__BRAIN_ALPHA_OPS_STREAM_TOKEN__"
MISSING_TEMPLATE_HTML = "<!doctype html><html><body><h1>Template not found</h1></body></html>"
WEB_FRONTEND_ENV = "BRAIN_ALPHA_OPS_WEB_FRONTEND"
INLINE_FRONTEND = "inline"
REACT_FRONTEND = "react"

_HTML_CACHE = ""
_HTML_CACHE_PATH: Path | None = None
_HTML_LOCK = threading.RLock()


def selected_frontend(value: str | None = None) -> str:
    frontend = str(value if value is not None else os.getenv(WEB_FRONTEND_ENV, INLINE_FRONTEND)).strip().lower()
    if frontend not in {INLINE_FRONTEND, REACT_FRONTEND}:
        raise ValueError(f"{WEB_FRONTEND_ENV} must be '{INLINE_FRONTEND}' or '{REACT_FRONTEND}'")
    return frontend


def inline_html_path() -> Path:
    return Path(__file__).resolve().parent / "web" / "index.html"


def react_dist_path() -> Path:
    return Path(__file__).resolve().parent / "web" / "react_app" / "dist"


def default_html_path(frontend: str | None = None) -> Path:
    """Return the primary HTML template path.

    Priority:
      1. Explicit React selection when the build artifact exists.
      2. web/index.html as the canonical production SPA and safe fallback.
      3. React build artifact when the inline SPA is absent.
    """
    inline_path = inline_html_path()
    react_path = react_dist_path() / "index.html"
    if selected_frontend(frontend) == REACT_FRONTEND and react_path.is_file():
        return react_path
    if inline_path.is_file():
        return inline_path
    if react_path.is_file():
        return react_path
    return inline_path


def resolve_react_asset(request_path: str, frontend: str | None = None) -> tuple[bytes, str] | None:
    if selected_frontend(frontend) != REACT_FRONTEND:
        return None
    decoded_path = unquote(str(request_path or ""))
    if not decoded_path.startswith("/assets/"):
        return None
    assets_root = (react_dist_path() / "assets").resolve()
    candidate = (assets_root / decoded_path.removeprefix("/assets/")).resolve()
    try:
        candidate.relative_to(assets_root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return candidate.read_bytes(), content_type


def load_html(path: Path | None = None) -> str:
    global _HTML_CACHE, _HTML_CACHE_PATH
    if path is None:
        with _HTML_LOCK:
            template_path = default_html_path()
            if _HTML_CACHE and _HTML_CACHE_PATH == template_path:
                return _HTML_CACHE
            html = template_path.read_text(encoding="utf-8") if template_path.is_file() else MISSING_TEMPLATE_HTML
            _HTML_CACHE = html
            _HTML_CACHE_PATH = template_path
            return html
    template_path = path
    with _HTML_LOCK:
        return template_path.read_text(encoding="utf-8") if template_path.is_file() else MISSING_TEMPLATE_HTML


def reset_html_cache() -> None:
    global _HTML_CACHE, _HTML_CACHE_PATH
    with _HTML_LOCK:
        _HTML_CACHE = ""
        _HTML_CACHE_PATH = None


def render_html(csrf_token: str, stream_token: str, html: str | None = None) -> str:
    source = html if html is not None else load_html()
    source = _replace_placeholder_value(source, CSRF_TOKEN_PLACEHOLDER, csrf_token)
    return _replace_placeholder_value(source, STREAM_TOKEN_PLACEHOLDER, stream_token)


def _replace_placeholder_value(source: str, placeholder: str, value: str) -> str:
    pattern = rf"(?<![.\w$]){re.escape(placeholder)}(?![\w$])"
    return re.sub(pattern, value, source)


def content_security_policy_for_html(html: str | None = None) -> str:
    return _content_security_policy_for_html(html if html is not None else load_html())
