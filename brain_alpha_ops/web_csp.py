"""Content Security Policy helpers for the local web console."""

from __future__ import annotations

import base64
import hashlib
import re


SCRIPT_BLOCK_PATTERN = re.compile(r"<script(?:\s[^>]*)?>(.*?)</script>", re.IGNORECASE | re.DOTALL)
STYLE_BLOCK_PATTERN = re.compile(r"<style(?:\s[^>]*)?>(.*?)</style>", re.IGNORECASE | re.DOTALL)


def script_hash_sources(html: str) -> str:
    return _hash_sources(html, SCRIPT_BLOCK_PATTERN)


def style_hash_sources(html: str) -> str:
    return _hash_sources(html, STYLE_BLOCK_PATTERN)


def content_security_policy_for_html(html: str) -> str:
    script_hashes = script_hash_sources(html)
    style_hashes = style_hash_sources(html)

    # Detect if the HTML uses CDN scripts (React app) — allow unpkg.com + tailwind CDN
    uses_cdn = "unpkg.com" in html or "cdn.tailwindcss.com" in html
    cdn_sources = " https://unpkg.com https://cdn.tailwindcss.com" if uses_cdn else ""

    script_src = f"script-src 'self'{cdn_sources}" + (f" {script_hashes}" if script_hashes else "")
    style_src = "style-src 'self'" + (f" {style_hashes}" if style_hashes else "")
    return (
        f"default-src 'self'; {script_src}; "
        f"{style_src}; connect-src 'self'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )


def _hash_sources(html: str, pattern: re.Pattern[str]) -> str:
    hashes: list[str] = []
    for match in pattern.finditer(html):
        digest = hashlib.sha256(match.group(1).encode("utf-8")).digest()
        hashes.append("'sha256-" + base64.b64encode(digest).decode("ascii") + "'")
    return " ".join(hashes)
