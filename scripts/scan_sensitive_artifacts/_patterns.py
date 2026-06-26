"""Sensitive-artifact scan patterns, constants, and match-actionability helpers.

Split from the former ``scan_sensitive_artifacts.py`` monolith (Workstream F3.9).
Holds the compiled finding patterns, known-secret hash allowlist, scan
directory/glob configuration, and the per-match predicates that decide whether
a regex hit is an actionable secret versus a placeholder/fixture.
"""

from __future__ import annotations

import hashlib
import re

DEFAULT_SCAN_DIRS = ("data",)
DEFAULT_SCAN_GLOBS = ("*.log", "*.json", "*.jsonl", "*.txt", "*.md", "*.err", "*.ps1", "*.bat", "*.cmd")
DEFAULT_ROOT_FILES = ("server.out.log", "server.err.log", "server.verify.out.log", "server.verify.err.log")
# Critical credential-handling modules always scanned (even without --include-all)
# so that hardcoding regressions in to_dict / kill-switch / env-var paths are
# caught by local `python scripts/scan_sensitive_artifacts.py` runs, not only CI.
CRITICAL_CREDENTIAL_FILES = (
    "brain_alpha_ops/config_models.py",
    "brain_alpha_ops/runtime_constants.py",
    "brain_alpha_ops/secure_credentials.py",
)
SKIP_DIRS = {
    ".git",
    ".playwright-cli",
    ".codex_pydeps",
    ".codex_tmp_quantgpt_src",
    ".mypy_cache",
    ".nox",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".superdesign",
    ".codebuddy",
    ".workbuddy",
    "_codex_tools",
    "build",
    "dist",
    "env",
    "node_modules",
    "output",
    "venv",
    "_archive_before_rebuild_20260512_152528",
}
DEFAULT_ONLY_SKIP_DIRS = {"tests"}
TEXT_SUFFIXES = {".bat", ".cfg", ".cmd", ".conf", ".env", ".err", ".ini", ".json", ".jsonl", ".log", ".md", ".ps1", ".py", ".txt", ".yaml", ".yml"}
GIT_HISTORY_SKIP_DIRS = SKIP_DIRS
KNOWN_SECRET_HASHES = {
    "known_brain_account_identifier_sha256": "74c04d520e8f5c6d8d6a2f98f4952e9e2f2b155efa5f3efc1199d3e09587e373",
    "known_brain_password_sha256": "01ea3c54ef81c1a74977131ffa3e418ed82d050e88e81bcb1331f860eaa28197",
}
KNOWN_SECRET_HASHES_BY_DIGEST = {digest: label for label, digest in KNOWN_SECRET_HASHES.items()}

SECRET_KEY_NAME_PATTERN = (
    r"[A-Z0-9_-]*"
    r"(?:"
    r"access[-_]?token|"
    r"refresh[-_]?token|"
    r"id[-_]?token|"
    r"api[-_]?key|"
    r"csrf(?:[-_]?token)?|"
    r"password|"
    r"passwd|"
    r"secret|"
    r"session[-_]?(?:id|key|token)|"
    r"token"
    r")"
)
SECRET_KEY_PATTERN = (
    r"(?i)(?:"
    rf"['\"]?\b({SECRET_KEY_NAME_PATTERN})\b['\"]?"
    r"|['\"]session['\"]"
    r")\s*[:=]\s*['\"]?[^'\",\s;]{8,}"
)

FINDING_PATTERNS = {
    "auth_header": re.compile(r"(?i)\b(authorization)\s*[:=]\s*(basic|bearer)\s+[A-Za-z0-9._~+/=-]+"),
    "bearer_token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    "basic_auth": re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]{20,}"),
    "cookie": re.compile(r"(?i)\b(set-cookie|cookie)\s*[:=]\s*[^,\s;]{8,}"),
    "secret_key": re.compile(SECRET_KEY_PATTERN),
}


def _candidate_secret_tokens(line: str) -> set[str]:
    tokens: set[str] = set()
    for match in re.finditer(r"[A-Za-z0-9][A-Za-z0-9._@+\-/=]{3,}", line):
        token = match.group(0).strip("'\"`.,;:()[]{}<>")
        if token:
            tokens.add(token)
            if "@" in token:
                tokens.add(token.split("@", 1)[0])
    return tokens


def _match_is_placeholder_fixture(match: re.Match, path, root) -> bool:  # type: ignore[no-untyped-def]
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        relative_parts = path.parts
    if not relative_parts or relative_parts[0] not in {"tests", "docs"}:
        return False
    lowered = str(match.group(0) or "").lower()
    return any(
        marker in lowered
        for marker in (
            "secret-token",
            "secret-xyz",
            "secret-password",
            "secret-local-",
            "secret-expression-",
            "secret-progress-",
            "secret-plugin-",
            "wrong-password",
            "wrong_password",
            "fixture-token",
            "dummy-token",
            "placeholder-token",
            "fresh-token",
            "page-token",
            "current-page-token",
            "not-scanned-by-default",
            "current_token",
            "<redacted>",
            "redacted-by-test",
            "auth failed for ***@***",
            "sk-local-secret",
            "local-token",
            "cloud-token",
            "live-key",
            "guidance-token",
            "guidance-password",
            "observability-password",
            "plain-password",
            "plain-token",
            "rotated-token",
            "session-password",
            "basic-password",
            "stored-password",
            "first-password",
            "test-key",
            "test-token",
            "session-token",
            "stale-token",
            "bad-token",
            "stub-token",
            "secret456",
            "secret-123",
            "secret-456",
            "secret-api-key",
            "secret-session-id",
            "access-secret",
            "admin-secret",
            "auth-secret",
            "csrf-header-secret",
            "csrf-secret",
            "id-secret",
            "refresh-secret",
            "session-secret",
            "super-secret",
            "not-allowlisted",
            "index damaged token",
            "provider down token",
            "token=<redacted>",
            "cookie=session_",
            "session_1",
            "csrf_1",
            "stream_1",
        )
    )


def _secret_key_match_is_actionable(match: re.Match, line: str, path) -> bool:  # type: ignore[no-untyped-def]
    token = str(match.group(0) or "")
    value = token.split("=", 1)[-1] if "=" in token else token.split(":", 1)[-1]
    value = value.strip().strip("'\"`").rstrip(")]},")
    lowered_line = line.lower()
    lowered_value = value.lower()
    if len(value) < 8:
        return False
    if lowered_value in {"api_key", "csrf_token", "password", "session_id", "token", "username"}:
        return False
    if lowered_value.startswith("...") or lowered_value.startswith("__brain_alpha_ops_"):
        return False
    if "redacted" in lowered_value:
        return False
    if "os.getenv" in lowered_line or "os.environ" in lowered_line:
        return False
    if any(lowered_value.startswith(prefix) for prefix in ("args.", "self.", "result.", "req.", "data.", "auth_data.")):
        return False
    if any(marker in value for marker in ("(", ")", "[", "]", "{", "}")):
        return False
    if re.fullmatch(r"[A-Z][A-Z0-9_]+", value):
        return False
    if re.fullmatch(r"__?[A-Z0-9_]+__?", value):
        return False
    if path.suffix.lower() == ".py" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?", value):
        return False
    if lowered_value in {"your_password", "your_password_here", "your_token", "admin_jwt_token"}:
        return False
    if any(marker in lowered_value for marker in ("placeholder", "dummy", "example", "fixture", "wrong-password", "wrong_password")):
        return False
    if lowered_value.startswith(("secret-token", "secret-cookie", "session-cookie")):
        return False
    if lowered_value in {"secret", "secret_token", "secret-token"}:
        return False
    return True


def _cookie_match_is_actionable(line: str) -> bool:
    lowered = line.lower()
    if "<id>" in lowered or "<redacted>" in lowered or "<cookie>" in lowered:
        return False
    value = line.split("=", 1)[-1] if "=" in line else line.split(":", 1)[-1]
    value = value.strip().strip("'\"`").rstrip(")]},")
    lowered_value = value.lower()
    if "(" in value or ")" in value:
        return False
    if "{session_id}" in lowered:
        return False
    if lowered_value.startswith(("manager.", "web.", "self.", "ctx.")):
        return False
    if lowered_value.startswith(("session_", "session-cookie")) or "cookie=session_" in lowered or "cookie=session-cookie" in lowered:
        return False
    return True
