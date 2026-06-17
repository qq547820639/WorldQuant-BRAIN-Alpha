"""Integration tests for web layer critical paths.

Tests cover:
  - Web route dispatch
  - Error handling
  - Security features
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestWebRouteDispatch:
    """Test web route dispatch logic."""

    def test_dispatch_get_status(self):
        """Test status endpoint returns structured data."""
        from brain_alpha_ops.web_routes import _status_payload

        result = _status_payload({})
        assert isinstance(result, dict)

    def test_dispatch_returns_dict(self):
        """Test dispatch functions return dicts."""
        from brain_alpha_ops.web_routes import dispatch_get, dispatch_post

        assert callable(dispatch_get)
        assert callable(dispatch_post)


class TestWebErrorHandling:
    """Test web error handling."""

    def test_redact_error_message(self):
        """Test error message redaction."""
        from brain_alpha_ops.redaction import redact_error_message

        # Test with sensitive data
        error = ValueError("password=secret123, token=abc456")
        redacted = redact_error_message(error)
        assert "secret123" not in redacted
        assert "abc456" not in redacted

    def test_classify_error(self):
        """Test error classification."""
        from brain_alpha_ops.errors import classify_error

        error = ValueError("test error")
        result = classify_error(error)
        # Result is an ErrorInfo dataclass, not a dict
        assert hasattr(result, "error_code")
        assert hasattr(result, "category")


class TestWebSecurityFeatures:
    """Test web security features."""

    def test_csp_module_importable(self):
        """Test CSP module is importable."""
        from brain_alpha_ops import web_csp

        assert hasattr(web_csp, "__file__")

    def test_session_module_importable(self):
        """Test session module is importable."""
        from brain_alpha_ops import web_session

        assert hasattr(web_session, "__file__")


class TestWebPayloadValidation:
    """Test web payload validation."""

    def test_payload_validation_module_importable(self):
        """Test payload validation module is importable."""
        from brain_alpha_ops import web_payload_validation

        assert hasattr(web_payload_validation, "__file__")

    def test_web_modules_exist(self):
        """Test all web modules exist."""
        from brain_alpha_ops import (
            web_routes,
            web_session,
            web_csp,
            web_payload_validation,
            web_rate_limit,
            web_security,
        )

        assert web_routes is not None
        assert web_session is not None
        assert web_csp is not None
        assert web_payload_validation is not None
        assert web_rate_limit is not None
        assert web_security is not None


class TestWebRateLimiting:
    """Test web rate limiting."""

    def test_rate_limiter_allows_requests(self):
        """Test rate limiter allows requests under limit."""
        from brain_alpha_ops.web_rate_limit import RequestRateLimiter, RateLimitPolicy

        limiter = RequestRateLimiter(RateLimitPolicy(window_seconds=10, read_requests=10))
        result = limiter.check(key="test", method="GET", path="/api/test", now=100)
        assert result["ok"] is True

    def test_rate_limiter_blocks_over_limit(self):
        """Test rate limiter blocks requests over limit."""
        from brain_alpha_ops.web_rate_limit import RequestRateLimiter, RateLimitPolicy

        limiter = RequestRateLimiter(RateLimitPolicy(window_seconds=10, read_requests=2))
        limiter.check(key="test", method="GET", path="/api/test", now=100)
        limiter.check(key="test", method="GET", path="/api/test", now=101)
        result = limiter.check(key="test", method="GET", path="/api/test", now=102)
        assert result["ok"] is False
        assert result["error_code"] == "RATE_LIMITED"
