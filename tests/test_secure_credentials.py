"""Tests for brain_alpha_ops.secure_credentials — credential management safety."""
import os
import pytest
from brain_alpha_ops.secure_credentials import (
    validate_credential_envs,
    CredentialBundle,
    ResolutionTrace,
    resolve_credentials,
    require_env,
)


class TestCredentialBundle:
    def test_repr_is_masked(self):
        cb = CredentialBundle(username="test", password="secret123")
        r = repr(cb)
        assert "secret123" not in r
        assert "CredentialBundle" in r

    def test_empty_bundle(self):
        cb = CredentialBundle(username="", password="", token="")
        assert cb.username == ""
        assert cb.password == ""
        assert cb.token == ""

    def test_has_credentials_detects_username_password(self):
        cb = CredentialBundle(username="u", password="p")
        assert cb.has_credentials is True

    def test_has_credentials_detects_token(self):
        cb = CredentialBundle(token="t")
        assert cb.has_credentials is True

    def test_has_credentials_false_when_empty(self):
        cb = CredentialBundle()
        assert cb.has_credentials is False

    def test_auth_method_detects_token(self):
        cb = CredentialBundle(token="t")
        assert cb.auth_method == "token"

    def test_auth_method_detects_userpass(self):
        cb = CredentialBundle(username="u", password="p")
        assert cb.auth_method == "userpass"

    def test_auth_method_none_when_empty(self):
        cb = CredentialBundle()
        assert cb.auth_method == "none"

    def test_masked_never_exposes_actual_values(self):
        cb = CredentialBundle(username="myuser", password="mypassword", token="mytoken")
        m = cb.masked()
        assert m["has_username"] is True
        assert m["has_password"] is True
        assert m["has_token"] is True
        assert "myuser" not in str(m)
        assert "mypassword" not in str(m)
        assert "mytoken" not in str(m)


class TestResolutionTrace:
    def test_fields_present(self):
        rt = ResolutionTrace(
            source="environment", key="username", present=True, length=8, masked="my***"
        )
        assert rt.source == "environment"
        assert rt.key == "username"
        assert rt.present is True
        assert rt.length == 8
        assert rt.masked == "my***"


class TestResolveCredentials:
    def test_all_empty_returns_empty_bundle(self):
        cb = resolve_credentials()
        assert cb.username == ""
        assert cb.password == ""
        assert cb.token == ""
        assert cb.has_credentials is False

    def test_explicit_args_take_precedence(self, monkeypatch):
        monkeypatch.setenv("BRAIN_USERNAME", "env_user")
        monkeypatch.setenv("BRAIN_PASSWORD", "env_pass")
        cb = resolve_credentials(username="explicit_user", password="explicit_pass")
        assert cb.username == "explicit_user"
        assert cb.password == "explicit_pass"

    def test_env_fallback(self, monkeypatch):
        monkeypatch.setenv("BRAIN_USERNAME", "env_user")
        monkeypatch.setenv("BRAIN_TOKEN", "env_token")
        cb = resolve_credentials()
        assert cb.username == "env_user"
        assert cb.token == "env_token"

    def test_trace_records_all_keys(self):
        cb = resolve_credentials(username="u", password="p")
        trace_keys = {t.key for t in cb.trace}
        assert "username" in trace_keys
        assert "password" in trace_keys
        assert "token" in trace_keys

    def test_explicit_args_trace_marked_correctly(self):
        cb = resolve_credentials(username="u")
        username_trace = next(t for t in cb.trace if t.key == "username")
        assert username_trace.source == "explicit_argument"
        assert username_trace.present is True

    def test_missing_credential_trace_marked_none(self):
        cb = resolve_credentials()
        username_trace = next(t for t in cb.trace if t.key == "username")
        assert username_trace.source == "none"
        assert username_trace.present is False


class TestValidateCredentialEnvs:
    def test_all_missing_returns_all_names(self):
        old_user = os.environ.pop("BRAIN_USERNAME", None)
        old_pass = os.environ.pop("BRAIN_PASSWORD", None)
        old_token = os.environ.pop("BRAIN_TOKEN", None)
        try:
            missing = validate_credential_envs()
            assert "BRAIN_USERNAME" in missing
        finally:
            if old_user is not None:
                os.environ["BRAIN_USERNAME"] = old_user
            if old_pass is not None:
                os.environ["BRAIN_PASSWORD"] = old_pass
            if old_token is not None:
                os.environ["BRAIN_TOKEN"] = old_token

    def test_token_set_alone_passes(self, monkeypatch):
        monkeypatch.setenv("BRAIN_TOKEN", "valid_token")
        monkeypatch.delenv("BRAIN_USERNAME", raising=False)
        monkeypatch.delenv("BRAIN_PASSWORD", raising=False)
        missing = validate_credential_envs()
        assert len(missing) == 0

    def test_username_password_set_passes(self, monkeypatch):
        monkeypatch.setenv("BRAIN_USERNAME", "u")
        monkeypatch.setenv("BRAIN_PASSWORD", "p")
        monkeypatch.delenv("BRAIN_TOKEN", raising=False)
        missing = validate_credential_envs()
        assert len(missing) == 0

    def test_only_username_without_password_fails(self, monkeypatch):
        monkeypatch.setenv("BRAIN_USERNAME", "u")
        monkeypatch.delenv("BRAIN_PASSWORD", raising=False)
        monkeypatch.delenv("BRAIN_TOKEN", raising=False)
        missing = validate_credential_envs()
        assert len(missing) > 0


class TestRequireEnv:
    def test_missing_raises_runtime_error(self):
        with pytest.raises(RuntimeError):
            require_env("BRAIN_ALPHA_OPS_NONEXISTENT_VAR_XYZ123")

    def test_present_returns_value(self, monkeypatch):
        monkeypatch.setenv("BRAIN_ALPHA_OPS_TEST_VAR", "hello")
        result = require_env("BRAIN_ALPHA_OPS_TEST_VAR")
        assert result == "hello"
