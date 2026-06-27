"""Redaction helpers and constants for ``brain_ui_runner``.

Extracted into a sibling module to keep ``brain_ui_runner.py`` within the
project's 350-line budget while preserving the public/private symbol surface
that tests and downstream modules rely on.
"""
from __future__ import annotations

import re

from brain_alpha_ops.redaction import redact_text

LIVE_BROWSER_OPT_IN_ENV = "BRAIN_BROWSER_E2E_LIVE"
_REAL_BRAIN_HOSTS = ("brain.worldquant.com", "platform.worldquantbrain.com")
_COOKIE_PAIR_RE = re.compile(r"(?i)(\b(?:set-)?cookie\s*:\s*)([^;\n\r]+(?:;[^\n\r]*)?)")
_COOKIE_VALUE_RE = re.compile(r"(?i)(\b\w+\s*=\s*)[^;\s]+")
_SENSITIVE_HTML_FIELD_RE = re.compile(
    r"(?is)(<(?:input|textarea)\b(?=[^>]*(?:type|name|id)\s*=\s*['\"]?"
    r"[^'\"\s>]*(?:password|token|secret|csrf|session|cookie|authorization|auth)"
    r"[^'\"\s>]*)[^>]*\bvalue\s*=\s*)(['\"]?)(.*?)(\2)([^>]*>)"
)
_DEFAULT_PAGE_TIMEOUT_MS = 30000


def _redact_text(value: str) -> str:
    text = redact_text(value)
    text = _COOKIE_PAIR_RE.sub(
        lambda match: match.group(1) + _COOKIE_VALUE_RE.sub(
            lambda cookie_match: f"{cookie_match.group(1)}<redacted>",
            match.group(2),
        ),
        text,
    )
    text = _SENSITIVE_HTML_FIELD_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>{match.group(4)}{match.group(5)}",
        text,
    )
    return text


def _redact_url(value: str) -> str:
    text = _redact_text(value)
    if "#" in text:
        text = text.split("#", 1)[0]
    if "?" not in text:
        return text
    return text.split("?", 1)[0] + "?[redacted-query]"


def _looks_like_login_page(lowered_text: str) -> bool:
    login_tokens = ("sign in", "log in", "login", "password")
    submit_tokens = ("submit alpha", "confirm submit", "alpha submitted")
    return any(token in lowered_text for token in login_tokens) and not any(token in lowered_text for token in submit_tokens)


def _unexpected_modal(text: str) -> bool:
    lowered = text.lower()
    expected = ("submit", "confirm", "are you sure", "approval")
    return not any(token in lowered for token in expected)
