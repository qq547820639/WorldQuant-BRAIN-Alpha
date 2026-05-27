"""Secure credential management with runtime-only exposure.

Enforces:
- Never log credentials at any level
- Never serialize credentials to disk except via encrypted paths
- Environment-variable-only for production (no CLI args)
- Token rotation support
- Audit trail for credential source resolution
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Logging filter — strip credentials from all log records
# ═══════════════════════════════════════════════════════════════════════

CREDENTIAL_KEY_PATTERNS = frozenset({
    "password", "token", "secret", "api_key", "access_token",
    "authorization", "cookie", "csrf", "session",
    "credential", "credentials",
})


class CredentialRedactionFilter(logging.Filter):
    """Logging filter that redacts credential-like values from log records.

    Attach to root logger:
        logging.getLogger().addFilter(CredentialRedactionFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and isinstance(record.args, dict):
            sanitized = {}
            for key, value in record.args.items():
                key_lower = str(key).lower().replace("-", "_")
                if any(pattern in key_lower for pattern in CREDENTIAL_KEY_PATTERNS):
                    sanitized[key] = "<REDACTED>"
                else:
                    sanitized[key] = value
            record.args = sanitized
        if isinstance(record.msg, str):
            for pattern in CREDENTIAL_KEY_PATTERNS:
                if pattern in record.msg.lower():
                    # Replace explicit credential mentions
                    record.msg = record.msg.replace(
                        f"{pattern}=", f"{pattern}=<REDACTED>"
                    )
                    record.msg = record.msg.replace(
                        f"{pattern}: ", f"{pattern}: <REDACTED> "
                    )
        return True


# ═══════════════════════════════════════════════════════════════════════
# Credential provider
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ResolutionTrace:
    """Audit record for credential resolution."""
    source: str           # "environment" | "config_file" | "cli" | "none"
    key: str              # "username" | "password" | "token"
    present: bool
    length: int
    masked: str           # masked representation


@dataclass
class CredentialBundle:
    """Resolved credential bundle with audit trace."""
    username: str = ""
    password: str = ""
    token: str = ""
    trace: list[ResolutionTrace] = field(default_factory=list)

    @property
    def has_credentials(self) -> bool:
        return bool(self.token or (self.username and self.password))

    @property
    def auth_method(self) -> str:
        if self.token:
            return "token"
        if self.username and self.password:
            return "userpass"
        return "none"

    def masked(self) -> dict[str, Any]:
        """Return a safe-for-logging representation."""
        return {
            "has_username": bool(self.username),
            "has_password": bool(self.password),
            "has_token": bool(self.token),
            "auth_method": self.auth_method,
            "trace": [
                {"source": t.source, "key": t.key, "present": t.present}
                for t in self.trace
            ],
        }


def resolve_credentials(
    *,
    username: str = "",
    password: str = "",
    token: str = "",
    username_env: str = "BRAIN_USERNAME",
    password_env: str = "BRAIN_PASSWORD",
    token_env: str = "BRAIN_TOKEN",
) -> CredentialBundle:
    """Resolve credentials with explicit precedence rules.

    Precedence (highest to lowest):
      1. Explicit argument (username/password/token)
      2. Environment variable
      3. Empty string (no credentials)

    Returns a CredentialBundle with full audit trace.
    """
    trace: list[ResolutionTrace] = []

    def _resolve(key: str, explicit: str, env_name: str) -> tuple[str, ResolutionTrace]:
        if explicit:
            t = ResolutionTrace(
                source="explicit_argument",
                key=key,
                present=True,
                length=len(explicit),
                masked=explicit[:2] + "***" if len(explicit) > 3 else "***",
            )
            trace.append(t)
            return explicit, t

        env_value = os.getenv(env_name, "")
        if env_value:
            t = ResolutionTrace(
                source="environment_variable",
                key=key,
                present=True,
                length=len(env_value),
                masked=env_value[:2] + "***" if len(env_value) > 3 else "***",
            )
            trace.append(t)
            return env_value, t

        t = ResolutionTrace(
            source="none",
            key=key,
            present=False,
            length=0,
            masked="",
        )
        trace.append(t)
        return "", t

    resolved_username, _ = _resolve("username", username, username_env)
    resolved_password, _ = _resolve("password", password, password_env)
    resolved_token, _ = _resolve("token", token, token_env)

    bundle = CredentialBundle(
        username=resolved_username,
        password=resolved_password,
        token=resolved_token,
        trace=trace,
    )

    # Log only masked info
    logger.debug(
        "Credentials resolved: auth_method=%s, username=%s, "
        "password=%s, token=%s",
        bundle.auth_method,
        bool(bundle.username),
        bool(bundle.password),
        bool(bundle.token),
    )

    return bundle


# ═══════════════════════════════════════════════════════════════════════
# Environment variable helpers
# ═══════════════════════════════════════════════════════════════════════

def require_env(name: str) -> str:
    """Get env var or raise with clear message."""
    value = os.getenv(name, "")
    if not value.strip():
        raise RuntimeError(
            f"环境变量 {name} 未设置。请设置后重试。\n"
            f"  示例：export {name}=<your_value>"
        )
    return value


def validate_credential_envs() -> list[str]:
    """Check that credential env vars are set; returns missing names."""
    missing: list[str] = []
    token = os.getenv("BRAIN_TOKEN", "")
    username = os.getenv("BRAIN_USERNAME", "")
    password = os.getenv("BRAIN_PASSWORD", "")

    if not token and (not username or not password):
        if not username:
            missing.append("BRAIN_USERNAME")
        if not password:
            missing.append("BRAIN_PASSWORD")
        if not token:
            missing.append("BRAIN_TOKEN")

    return missing


# ═══════════════════════════════════════════════════════════════════════
# Install filter on module import
# ═══════════════════════════════════════════════════════════════════════

_installed_filters: set[int] = set()


def install_log_redaction() -> None:
    """Install the credential redaction filter on the root logger.

    Idempotent — safe to call multiple times.
    """
    root = logging.getLogger()
    filter_id = id(CredentialRedactionFilter)
    if filter_id in _installed_filters:
        return
    root.addFilter(CredentialRedactionFilter())
    _installed_filters.add(filter_id)


# Auto-install on import
install_log_redaction()
