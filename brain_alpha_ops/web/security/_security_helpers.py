"""Header, cookie, and host parsing helpers for the local web security module.

Extracted from ``web_security.py`` to keep the source file under the
project's 350-line limit. These are pure, stateless helpers that take a
raw request/header string and return a normalized value.
"""

from __future__ import annotations

from urllib.parse import urlparse


def header_hostname(host_header: str) -> str:
    return (urlparse(f"//{host_header}").hostname or "").lower()


def header_port(host_header: str) -> int | None:
    try:
        return urlparse(f"//{host_header}").port
    except ValueError:
        return None


def parse_cookies(cookie_header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in str(cookie_header or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def normalize_host(host: str | None, *, default_host: str = "127.0.0.1") -> str:
    value = str(host or "").strip()
    return value or default_host
