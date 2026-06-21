"""Tests for _launch_monitor.py — production monitor helpers."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _launch_monitor import sanitized_child_env, SENSITIVE_CHILD_ENV_KEYS, SAFE_CHILD_ENV_KEYS


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

    def test_unknown_keys_stripped(self):
        """Keys not in SAFE_CHILD_ENV_KEYS should be stripped."""
        source = {"HOME": "/home", "RANDOM_UNKNOWN_KEY": "value"}
        result = sanitized_child_env(source)
        assert "HOME" in result
        assert "RANDOM_UNKNOWN_KEY" not in result

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
