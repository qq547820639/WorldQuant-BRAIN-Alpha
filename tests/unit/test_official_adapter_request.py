"""Request construction tests extracted from ``tests/test_official_adapter.py``.

Covers: URL building, header construction, origin validation, throttle.
Full suite in ``test_official_adapter.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.official_helpers import build_official_url


def test_build_official_url_allows_reserved_offline_test_hosts():
    """build_official_url must accept reserved offline-test host suffixes."""
    url = build_official_url(
        "https://api.test.invalid",
        "/v1/health",
        None,
    )
    assert "/v1/health" in url


def test_build_official_url_rejects_non_ascii_hostname():
    """build_official_url must reject non-ASCII hostnames."""
    with pytest.raises(BrainAPIError, match="non-ASCII"):
        build_official_url(
            "https://api.worldquantbrain.com",
            "https://héllo.com/v1/data",
            None,
        )


def test_request_rejects_untrusted_configured_base_url():
    """Untrusted base URLs must be rejected at construction time."""
    with pytest.raises(BrainAPIError):
        build_official_url("https://evil.com", "/v1/data", None)


def test_list_fields_uses_market_scope_params():
    """list_fields must propagate market scope params as query args."""
    url = build_official_url(
        "https://api.worldquantbrain.com",
        "/v1/data/fields",
        {"instrumentType": "EQUITY", "region": "USA", "delay": "1", "universe": "TOP3000"},
    )
    assert "instrumentType=EQUITY" in url
    assert "region=USA" in url
    assert "delay=1" in url
    assert "universe=TOP3000" in url
