"""Retry tests extracted from ``tests/test_official_adapter.py``.

Covers: 429 retry, 5xx retry, URLError retry, rate-limit backoff.
Full suite in ``test_official_adapter.py``.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.official import OfficialBrainAPI
from brain_alpha_ops.config import OfficialAPIConfig


def test_request_retries_after_429(monkeypatch):
    """HTTP 429 must trigger retry after backoff."""
    attempts = []
    config = OfficialAPIConfig(rate_limit_retry_attempts=2, rate_limit_backoff_seconds=0.01)

    class FakeResponse:
        def __init__(self, data):
            self._data = io.BytesIO(data.encode() if isinstance(data, str) else data)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return self._data.read()

        @property
        def headers(self):
            return {}

    def _fake_open(req, timeout=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(
                req.full_url, 429, "Too Many Requests",
                {"Retry-After": "0.01"}, io.BytesIO(b'{"detail": "rate limited"}')
            )
        return FakeResponse('{"status": "ok"}')

    api = OfficialBrainAPI(config=config, token="test_token")
    monkeypatch.setattr(api._request_client, "_open", _fake_open)
    monkeypatch.setattr(api, "_throttle", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    result, _ = api._request("GET", "/v1/test")
    assert result == {"status": "ok"}
    assert len(attempts) == 3


def test_request_retries_after_transient_5xx(monkeypatch):
    """HTTP 502/503 must trigger retry."""
    attempts = []
    config = OfficialAPIConfig(rate_limit_retry_attempts=2, rate_limit_backoff_seconds=0.01)

    class FakeResponse:
        def __init__(self, data):
            self._data = io.BytesIO(data.encode() if isinstance(data, str) else data)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return self._data.read()
        @property
        def headers(self): return {}

    def _fake_open(req, timeout=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(
                req.full_url, 502, "Bad Gateway",
                {}, io.BytesIO(b'{"detail": "gateway error"}')
            )
        return FakeResponse('{"status": "ok"}')

    api = OfficialBrainAPI(config=config, token="test_token")
    monkeypatch.setattr(api._request_client, "_open", _fake_open)
    monkeypatch.setattr(api, "_throttle", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    result, _ = api._request("GET", "/v1/test")
    assert result == {"status": "ok"}
    assert len(attempts) == 3


def test_request_retries_after_urlerror(monkeypatch):
    """URLError must trigger retry."""
    attempts = []
    config = OfficialAPIConfig(rate_limit_retry_attempts=2, rate_limit_backoff_seconds=0.01)

    class FakeResponse:
        def __init__(self, data):
            self._data = io.BytesIO(data.encode() if isinstance(data, str) else data)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return self._data.read()
        @property
        def headers(self): return {}

    def _fake_open(req, timeout=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.URLError("connection refused")
        return FakeResponse('{"status": "ok"}')

    api = OfficialBrainAPI(config=config, token="test_token")
    monkeypatch.setattr(api._request_client, "_open", _fake_open)
    monkeypatch.setattr(api, "_throttle", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    result, _ = api._request("GET", "/v1/test")
    assert result == {"status": "ok"}
    assert len(attempts) == 3


def test_429_error_exposes_status_code():
    """BrainAPIError from 429 must expose HTTP status code."""
    from brain_alpha_ops.brain_api.official_request import _http_error_code
    code = _http_error_code(429, {"detail": "rate limited"}, "bearer")
    assert code == "RATE_LIMITED"
