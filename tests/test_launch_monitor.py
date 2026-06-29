"""Tests for _launch_monitor.py — production monitor helpers."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _launch_monitor import (
    DANGEROUS_CHILD_ENV_KEYS,
    SAFE_CHILD_ENV_KEYS,
    SENSITIVE_CHILD_ENV_KEYS,
    _is_completion_marker,
    _is_error_line,
    sanitized_child_env,
)


class TestSanitizedChildEnv:
    def test_safe_keys_preserved(self):
        """Whitelisted keys should pass through."""
        source = {"HOME": "/home/test", "PATH": "/usr/bin", "USER": "tester"}
        result = sanitized_child_env(source)
        assert result["HOME"] == "/home/test"
        assert result["PATH"] == "/usr/bin"
        assert result["USER"] == "tester"

    def test_sensitive_keys_stripped(self):
        """Sensitive keys (credentials) must be stripped."""
        source = {
            "HOME": "/home/test",
            "BRAIN_USERNAME": "secret_user",
            "BRAIN_PASSWORD": "secret_pass",
            "BRAIN_TOKEN": "secret_token",
        }
        result = sanitized_child_env(source)
        assert "BRAIN_USERNAME" not in result
        assert "BRAIN_PASSWORD" not in result
        assert "BRAIN_TOKEN" not in result
        assert "HOME" in result

    def test_force_real_submit_stripped(self):
        """BRAIN_ALPHA_FORCE_REAL_SUBMIT must be stripped from child env."""
        source = {"HOME": "/home", "BRAIN_ALPHA_FORCE_REAL_SUBMIT": "1"}
        result = sanitized_child_env(source)
        assert "BRAIN_ALPHA_FORCE_REAL_SUBMIT" not in result

    def test_unknown_keys_preserved(self):
        """Non-dangerous, non-sensitive keys should be preserved (blacklist approach)."""
        source = {"HOME": "/home", "RANDOM_UNKNOWN_KEY": "value"}
        result = sanitized_child_env(source)
        assert "HOME" in result
        assert "RANDOM_UNKNOWN_KEY" in result

    def test_dangerous_system_env_stripped(self):
        """Dangerous system env keys (secrets/CI tokens) must be stripped."""
        source = {
            "HOME": "/home",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "GITHUB_TOKEN": "secret",
            "DATABASE_URL": "postgres://...",
            "PYTHONPATH": "/evil",
        }
        result = sanitized_child_env(source)
        assert "HOME" in result
        assert "AWS_SECRET_ACCESS_KEY" not in result
        assert "GITHUB_TOKEN" not in result
        assert "DATABASE_URL" not in result
        assert "PYTHONPATH" not in result

    def test_brain_business_env_preserved(self):
        """BRAIN_* business env vars (non-sensitive) should be preserved."""
        source = {
            "HOME": "/home",
            "BRAIN_REGION": "usa",
            "BRAIN_ALPHA_OPS_LOG_LEVEL": "DEBUG",
            "BRAIN_ALPHA_OPS_STORAGE_DIR": "/tmp/data",
        }
        result = sanitized_child_env(source)
        assert "HOME" in result
        assert "BRAIN_REGION" in result
        assert "BRAIN_ALPHA_OPS_LOG_LEVEL" in result
        assert "BRAIN_ALPHA_OPS_STORAGE_DIR" in result

    def test_empty_source(self):
        """Empty source produces empty result."""
        result = sanitized_child_env({})
        assert result == {}

    def test_sensitive_env_keys_contains_required(self):
        """SENSITIVE_CHILD_ENV_KEYS must include BRAIN credentials and admin token."""
        assert "BRAIN_USERNAME" in SENSITIVE_CHILD_ENV_KEYS
        assert "BRAIN_PASSWORD" in SENSITIVE_CHILD_ENV_KEYS
        assert "BRAIN_TOKEN" in SENSITIVE_CHILD_ENV_KEYS
        assert "BRAIN_ALPHA_OPS_ADMIN_TOKEN" in SENSITIVE_CHILD_ENV_KEYS
        assert "BRAIN_ALPHA_FORCE_REAL_SUBMIT" in SENSITIVE_CHILD_ENV_KEYS


class TestSafeChildEnvKeys:
    def test_minimal_env_keys_present(self):
        """SAFE_CHILD_ENV_KEYS must have a reasonable set of standard env vars."""
        assert "HOME" in SAFE_CHILD_ENV_KEYS
        assert "PATH" in SAFE_CHILD_ENV_KEYS
        assert "USER" in SAFE_CHILD_ENV_KEYS
        assert "TEMP" in SAFE_CHILD_ENV_KEYS


class TestCompletionMarker:
    def test_loose_done_word_not_treated_as_completion(self):
        """A bare word 'DONE' must NOT trigger completion (F-015)."""
        assert _is_completion_marker("step DONE") is False
        assert _is_completion_marker("DONE loading") is False
        assert _is_completion_marker("all DONE here") is False

    def test_structured_text_markers_trigger_completion(self):
        assert _is_completion_marker("RUN_COMPLETED") is True
        assert _is_completion_marker("pipeline_done signal received") is True
        assert _is_completion_marker("[PIPELINE_COMPLETED]") is True

    def test_json_event_marker_triggers_completion(self):
        assert _is_completion_marker('{"event": "pipeline_done"}') is True
        assert _is_completion_marker('{"event": "completed", "count": 5}') is True
        assert _is_completion_marker('{"status": "done"}') is True

    def test_json_without_completion_event_does_not_trigger(self):
        assert _is_completion_marker('{"event": "progress", "count": 5}') is False
        assert _is_completion_marker('{"level": "info", "msg": "DONE"}') is False

    def test_invalid_json_does_not_trigger(self):
        assert _is_completion_marker("{not valid json}") is False
        assert _is_completion_marker("") is False


class TestErrorLineDetection:
    def test_genuine_error_detected(self):
        assert _is_error_line("ERROR: connection failed") is True
        assert _is_error_line("step 3 failed to execute") is True
        assert _is_error_line("ERROR something broke") is True

    def test_no_error_false_positive_excluded(self):
        assert _is_error_line("validation: no_error") is False
        assert _is_error_line("no_errors found") is False
        assert _is_error_line("result: 0 errors") is False
        assert _is_error_line("error_count=0") is False
        assert _is_error_line("error_count = 0") is False
        assert _is_error_line("errors=0") is False
        assert _is_error_line("0 failed") is False
        assert _is_error_line("0 failures reported") is False

    def test_plain_line_not_error(self):
        assert _is_error_line("loading data...") is False
        assert _is_error_line("step 1 complete") is False


class TestDangerousChildEnvKeys:
    def test_contains_common_secret_envs(self):
        assert "AWS_SECRET_ACCESS_KEY" in DANGEROUS_CHILD_ENV_KEYS
        assert "GITHUB_TOKEN" in DANGEROUS_CHILD_ENV_KEYS
        assert "DATABASE_URL" in DANGEROUS_CHILD_ENV_KEYS
        assert "PYTHONPATH" in DANGEROUS_CHILD_ENV_KEYS
