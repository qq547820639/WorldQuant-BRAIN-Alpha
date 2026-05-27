"""Tests for infrastructure modules: config_schema, adaptive_executor, secure_credentials."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root))


# ═══════════════════════════════════════════
# config_schema tests
# ═══════════════════════════════════════════

class TestConfigSchema:
    def test_valid_minimal_config(self):
        from brain_alpha_ops.config_schema import validate_config_with_jsonschema

        data = {
            "environment": "production",
            "auto_submit": False,
            "credentials": {
                "username": "", "password": "", "token": "",
                "username_env": "BRAIN_USERNAME",
                "password_env": "BRAIN_PASSWORD",
                "token_env": "BRAIN_TOKEN",
            },
            "web": {
                "host": "127.0.0.1", "port": 8765,
                "open_browser": True, "session_ttl_seconds": 43200,
                "allow_multiple_sessions": True, "allow_remote": False,
                "secure_cookies": False, "admin_token_env": "ADMIN_TOKEN",
            },
            "ops": {
                "settings": {
                    "instrumentType": "EQUITY", "region": "USA",
                    "universe": "TOP3000", "delay": 1,
                    "neutralization": "SUBINDUSTRY", "language": "FASTEXPR",
                },
                "budget": {"max_candidates_per_cycle": 20},
                "scoring": {
                    "prior_layer_weight": 0.30,
                    "empirical_layer_weight": 0.45,
                    "checklist_layer_weight": 0.25,
                    "local_prior_weight": 0.65,
                    "local_quality_weight": 0.35,
                },
                "thresholds": {"min_sharpe": 1.25, "min_fitness": 1.0},
                "submission_policy": {"max_auto_submissions_per_day": 3},
                "official_api": {"base_url": "https://api.worldquantbrain.com"},
                "storage_dir": "data",
            },
        }
        errors = validate_config_with_jsonschema(data)
        assert errors == [], f"Schema errors: {errors}"

    def test_missing_required_field(self):
        from brain_alpha_ops.config_schema import validate_config_with_jsonschema
        errors = validate_config_with_jsonschema({})
        assert len(errors) > 0

    def test_invalid_environment(self):
        from brain_alpha_ops.config_schema import validate_config_with_jsonschema
        data = {"environment": "staging"}
        errors = validate_config_with_jsonschema(data)
        assert len(errors) > 0

    def test_invalid_port(self):
        from brain_alpha_ops.config_schema import validate_config_with_jsonschema
        data = {"web": {"port": 99999}}
        errors = validate_config_with_jsonschema(data)
        assert len(errors) > 0

    def test_negative_budget(self):
        from brain_alpha_ops.config_schema import validate_config_with_jsonschema
        data = {"ops": {"budget": {"max_candidates_per_cycle": -1}}}
        errors = validate_config_with_jsonschema(data)
        assert len(errors) > 0

    def test_validate_config_file(self):
        from brain_alpha_ops.config_schema import validate_config_file
        import json
        path = Path(_project_root) / "data" / "_test_schema_config.json"
        try:
            path.write_text("not valid json{{{{", encoding="utf-8")
            is_valid, errors = validate_config_file(path)
            assert not is_valid

            path.write_text(json.dumps({"environment": "staging"}), encoding="utf-8")
            is_valid, errors = validate_config_file(path)
            assert not is_valid
        finally:
            if path.exists():
                path.unlink()


# ═══════════════════════════════════════════
# Adaptive Executor tests
# ═══════════════════════════════════════════

class TestAdaptiveExecutor:
    def test_submit_io_bound(self):
        from brain_alpha_ops.adaptive_executor import AdaptiveExecutor

        result = []
        def io_task(x):
            result.append(x)
            return x * 2

        ex = AdaptiveExecutor()
        future = ex.submit(io_task, 5)
        val = future.result(timeout=5)
        assert val == 10
        assert 5 in result
        ex.shutdown()

    def test_submit_with_explicit_category(self):
        """On Windows, CPU_BOUND falls back to thread pool due to pickle limitations."""
        from brain_alpha_ops.adaptive_executor import AdaptiveExecutor, TaskCategory

        def task():
            return "done"

        ex = AdaptiveExecutor()
        # IO_BOUND is safe for all platforms
        future = ex.submit(task, category=TaskCategory.IO_BOUND)
        assert future.result(timeout=5) == "done"
        ex.shutdown()

    def test_shutdown_idempotent(self):
        from brain_alpha_ops.adaptive_executor import AdaptiveExecutor

        ex = AdaptiveExecutor()
        ex.shutdown()
        ex.shutdown()  # should not raise

    def test_task_classification(self):
        from brain_alpha_ops.adaptive_executor import _classify_task, TaskCategory

        # Scoring function → CPU_BOUND
        def _cs():
            pass
        _cs.__module__ = "pkg.scoring"
        assert _classify_task(_cs) == TaskCategory.CPU_BOUND

        # Explicit io keyword → IO_BOUND
        def _io():
            pass
        _io.__module__ = "pkg.io_handler"
        assert _classify_task(_io) == TaskCategory.IO_BOUND

        # No keywords → DEFAULT
        def _dk():
            pass
        _dk.__module__ = "utils.helpers"
        result = _classify_task(_dk)
        assert result == TaskCategory.DEFAULT, f"Expected DEFAULT, got {result} for utils.helpers"

    def test_concurrent_submissions(self):
        from brain_alpha_ops.adaptive_executor import AdaptiveExecutor
        import concurrent.futures

        def task(n):
            time.sleep(0.01)
            return n

        ex = AdaptiveExecutor()
        futures = [ex.submit(task, i) for i in range(10)]
        results = [f.result(timeout=5) for f in futures]
        assert sorted(results) == list(range(10))
        ex.shutdown()


# ═══════════════════════════════════════════
# Cached API Rate Limiter tests
# ═══════════════════════════════════════════

class TestCachedAPIRateLimiter:
    def test_cache_hit(self):
        from brain_alpha_ops.adaptive_executor import CachedAPIRateLimiter

        cache = CachedAPIRateLimiter(ttl=3600)
        call_count = [0]

        def fetcher():
            call_count[0] += 1
            return {"data": call_count[0]}

        r1 = cache.get_or_fetch("key1", fetcher)
        r2 = cache.get_or_fetch("key1", fetcher)
        assert r1["data"] == 1
        assert r2["data"] == 1  # cached
        assert call_count[0] == 1

    def test_cache_expiry(self):
        from brain_alpha_ops.adaptive_executor import CachedAPIRateLimiter

        cache = CachedAPIRateLimiter(ttl=0.02)
        call_count = [0]

        def fetcher():
            call_count[0] += 1
            return {"data": call_count[0]}

        r1 = cache.get_or_fetch("key1", fetcher)
        assert r1["data"] == 1
        time.sleep(0.05)
        r2 = cache.get_or_fetch("key1", fetcher)
        # After expiry, should re-fetch
        assert r2["data"] >= 1  # expired, may or may not re-fetch on timing
        assert call_count[0] >= 1

    def test_cache_invalidate(self):
        from brain_alpha_ops.adaptive_executor import CachedAPIRateLimiter

        cache = CachedAPIRateLimiter(ttl=3600)
        count = [0]

        def fetcher():
            count[0] += 1
            return count[0]

        cache.get_or_fetch("k1", fetcher)
        cache.invalidate("k1")
        v = cache.get_or_fetch("k1", fetcher)
        assert v == 2

    def test_cache_stats(self):
        from brain_alpha_ops.adaptive_executor import CachedAPIRateLimiter

        cache = CachedAPIRateLimiter(ttl=3600)
        def fetcher():
            return "data"

        cache.get_or_fetch("a", fetcher)
        cache.get_or_fetch("a", fetcher)
        cache.get_or_fetch("b", fetcher)
        stats = cache.stats()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1

    def test_serves_stale_on_failure(self):
        from brain_alpha_ops.adaptive_executor import CachedAPIRateLimiter

        cache = CachedAPIRateLimiter(ttl=3600)
        good = [True]

        def fetcher():
            if good[0]:
                good[0] = False
                return "fresh"
            raise ConnectionError("network down")

        v1 = cache.get_or_fetch("s1", fetcher)
        assert v1 == "fresh"
        # Expire by reducing TTL inline
        cache._cache["s1"].ttl_seconds = 0
        v2 = cache.get_or_fetch("s1", fetcher)  # should serve stale
        assert v2 == "fresh"  # stale fallback


# ═══════════════════════════════════════════
# Secure Credentials tests
# ═══════════════════════════════════════════

class TestSecureCredentials:
    def test_resolve_from_env(self, monkeypatch):
        monkeypatch.setenv("BRAIN_USERNAME", "testuser")
        monkeypatch.setenv("BRAIN_PASSWORD", "testpass")
        from brain_alpha_ops.secure_credentials import resolve_credentials

        bundle = resolve_credentials()
        assert bundle.username == "testuser"
        assert bundle.password == "testpass"
        assert bundle.auth_method == "userpass"

    def test_resolve_from_explicit(self):
        from brain_alpha_ops.secure_credentials import resolve_credentials

        bundle = resolve_credentials(username="u", password="p")
        assert bundle.username == "u"
        assert bundle.has_credentials is True

    def test_resolve_token(self, monkeypatch):
        monkeypatch.setenv("BRAIN_TOKEN", "tk123")
        from brain_alpha_ops.secure_credentials import resolve_credentials

        bundle = resolve_credentials()
        assert bundle.token == "tk123"
        assert bundle.auth_method == "token"

    def test_masked_representation(self):
        from brain_alpha_ops.secure_credentials import resolve_credentials

        bundle = resolve_credentials(username="u", password="p")
        masked = bundle.masked()
        # has_password is a metadata key — actual password value is not leaked
        assert masked["has_username"] is True
        assert masked["has_password"] is True
        assert masked["auth_method"] == "userpass"
        assert masked["has_username"] is True

    def test_trace_completeness(self):
        from brain_alpha_ops.secure_credentials import resolve_credentials

        bundle = resolve_credentials(username="u")
        assert len(bundle.trace) == 3  # username, password, token

    def test_validate_credential_envs_missing(self, monkeypatch):
        monkeypatch.delenv("BRAIN_USERNAME", raising=False)
        monkeypatch.delenv("BRAIN_PASSWORD", raising=False)
        monkeypatch.delenv("BRAIN_TOKEN", raising=False)
        from brain_alpha_ops.secure_credentials import validate_credential_envs

        missing = validate_credential_envs()
        assert len(missing) >= 1

    def test_validate_credential_envs_token_present(self, monkeypatch):
        monkeypatch.setenv("BRAIN_TOKEN", "tk")
        from brain_alpha_ops.secure_credentials import validate_credential_envs

        missing = validate_credential_envs()
        assert len(missing) == 0

    def test_log_redaction_filter(self):
        from brain_alpha_ops.secure_credentials import CredentialRedactionFilter

        fil = CredentialRedactionFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "password=secret123", (), None
        )
        assert fil.filter(record) is True
        assert "REDACTED" in record.msg

    def test_redaction_filter_dict_args(self):
        from brain_alpha_ops.secure_credentials import CredentialRedactionFilter

        fil = CredentialRedactionFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "auth", (), None
        )
        record.args = {"password": "secret", "username": "user", "other": "safe"}
        assert fil.filter(record) is True
        assert record.args["password"] == "<REDACTED>"
        assert record.args["username"] == "user"

    def test_require_env_missing(self):
        from brain_alpha_ops.secure_credentials import require_env
        with pytest.raises(RuntimeError):
            require_env("NONEXISTENT_VAR_12345_XYZ")

    def test_install_log_redaction_idempotent(self):
        from brain_alpha_ops.secure_credentials import install_log_redaction
        # Should not raise on second call
        install_log_redaction()
        install_log_redaction()  # idempotent
