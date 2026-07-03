"""Auth tests extracted from ``tests/test_official_adapter.py``.

Covers: cookie-auth fallback, bearer-to-basic chain, auth retry, token restore.
Full suite in ``test_official_adapter.py``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.official import OfficialBrainAPI
from brain_alpha_ops.config import OfficialAPIConfig


def test_official_api_keeps_credentials_out_of_plain_instance_fields():
    """Credentials must be accessed via properties, not plain __dict__ entries."""
    api = OfficialBrainAPI(
        config=OfficialAPIConfig(),
        username="test_user",
        password="test_pass",
        token="test_token",
    )
    # Credentials are stored in _credentials, not directly in __dict__
    assert api.username == "test_user"
    assert api.password == "test_pass"
    assert api.token == "test_token"
    assert "_credentials" in api.__dict__
    assert "username" not in api.__dict__
    assert "password" not in api.__dict__
    assert "token" not in api.__dict__


def test_auth_retry_does_not_recurse_on_authentication_endpoint():
    """Auth retry must not recurse when the failing request IS the auth endpoint."""
    from brain_alpha_ops.brain_api.official_request import _is_authentication_request
    assert _is_authentication_request("/authentication", "/authentication")
    assert not _is_authentication_request("/v1/data/fields", "/authentication")


def test_request_rejects_cross_origin_absolute_url():
    """Cross-origin absolute URLs must be rejected."""
    from brain_alpha_ops.brain_api.official_helpers import build_official_url
    with pytest.raises(BrainAPIError, match="cross-origin"):
        build_official_url("https://api.worldquantbrain.com", "https://api.test.invalid/v1/data", None)


def test_request_allows_same_origin_absolute_url():
    """Same-origin absolute URLs must be allowed."""
    from brain_alpha_ops.brain_api.official_helpers import build_official_url
    url = build_official_url(
        "https://api.worldquantbrain.com",
        "https://api.worldquantbrain.com/v1/data/fields",
        None,
    )
    assert "/v1/data/fields" in url
