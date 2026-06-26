"""URL building, origin validation, retry, and response parsing helpers."""

from __future__ import annotations

import json
import logging
import random
import urllib.parse
from typing import Any

from brain_alpha_ops.brain_api.base import BrainAPIError

_logger = logging.getLogger("brain_alpha_ops.brain_api.official_helpers")


ALLOWED_OFFICIAL_API_HOSTS = frozenset({"api.worldquantbrain.com"})
RESERVED_OFFLINE_TEST_HOST_SUFFIXES = (".test", ".invalid")


def build_official_url(base: str, path_or_url: str, query: dict | None) -> str:
    if ".." in path_or_url:
        raise BrainAPIError("refusing path traversal in official API path")
    base_parts = urllib.parse.urlparse(base)
    _validate_official_api_origin(base_parts, label="base_url")
    if path_or_url.startswith(("http://", "https://")):
        target_parts = urllib.parse.urlparse(path_or_url)
        _validate_official_api_origin(target_parts, label="target URL")
        base_origin = (base_parts.scheme.lower(), base_parts.netloc.lower())
        target_origin = (target_parts.scheme.lower(), target_parts.netloc.lower())
        if target_origin != base_origin:
            raise BrainAPIError("refusing cross-origin official API URL")
        url = path_or_url
    else:
        url = base.rstrip("/") + "/" + path_or_url.lstrip("/")
    if query:
        clean = {k: v for k, v in query.items() if v not in ("", None)}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    return url


def _validate_official_api_origin(parts: urllib.parse.ParseResult, *, label: str) -> None:
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    if scheme != "https" or not hostname:
        raise BrainAPIError(f"{label} must be an https URL with a host")
    try:
        hostname.encode("ascii")
    except UnicodeEncodeError as exc:
        raise BrainAPIError(f"{label} host contains non-ASCII characters") from exc
    if hostname in ALLOWED_OFFICIAL_API_HOSTS:
        return
    if hostname.endswith(RESERVED_OFFLINE_TEST_HOST_SUFFIXES):
        return
    raise BrainAPIError(f"{label} host {hostname!r} is not a known BRAIN API endpoint")


def retry_after(headers) -> float | None:
    value = headers.get("Retry-After") if headers else None
    if value in (None, ""):
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def retryable_status(status_code: int | None) -> bool:
    if status_code is None:
        return False
    return int(status_code) in {408, 429, 500, 502, 503, 504}


def retry_delay(headers, attempt: int, base_seconds: float) -> float:
    """Compute the back-off delay before retrying a request.

    P2-2 refactor: previously ``base * (attempt + 1)`` (linear); now
    ``base * 2^attempt * (0.5 + random()/2)`` (exponential with jitter) so
    concurrent retries don't synchronise.  The ``Retry-After`` header still
    wins when present.
    """
    retry_after_value = retry_after(headers)
    if retry_after_value is not None:
        return retry_after_value
    base = max(0.0, float(base_seconds))
    # 0.5..1.0 jitter; 2^attempt exponential envelope.
    jitter = 0.5 + random.random() / 2.0
    return base * (2 ** max(0, int(attempt))) * jitter


def parse_response(raw: str) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        _logger.warning("API returned non-JSON response (first 200 chars): %s", raw[:200])
        raise BrainAPIError("API returned non-JSON response", payload={"raw_preview": raw[:500]})


def looks_non_production_alpha_id(value: str) -> bool:
    text = str(value or "").strip().lower()
    prefixes = (
        "mock_",
        "mock-",
        "demo_",
        "demo-",
        "dry_run_",
        "dry-run-",
        "dryrun_",
        "test_",
        "test-",
        "fake_",
        "fake-",
        "sample_",
        "sample-",
        "stub_",
        "stub-",
        "prod_stub_",
        "prod_stub-",
        "prod-stub_",
        "prod-stub-",
    )
    non_production_values = {
        "mock",
        "demo",
        "dry-run",
        "dry_run",
        "dryrun",
        "test",
        "testing",
        "fake",
        "sample",
        "stub",
        "prod_stub",
        "prod-stub",
    }
    return bool(text and (text in non_production_values or text.startswith(prefixes)))
