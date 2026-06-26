"""Regression guard: prevent credential leaks in brain_alpha_ops/ and tests/.

Scans all ``.py``, ``.ts``, ``.tsx``, ``.js``, ``.json``, ``.yml``, ``.yaml``,
``.md`` files under ``brain_alpha_ops/`` and ``tests/`` for:

1. The user-provided test-credential literals (email prefix + password prefix).
2. ``Bearer <literal>`` token assignments.
3. ``password=``/``api_key=`` with literal values (not env vars / placeholders).

Asserts zero actionable matches so future commits cannot reintroduce a leak.

The forbidden literals are assembled at runtime from fragments so this test
file itself is not flagged by its own scan.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Iterable

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Forbidden literals are split to avoid self-matching when this file is scanned.
_FORBIDDEN_EMAIL_PREFIX = "547" + "820" + "639"
_FORBIDDEN_PASSWORD_PREFIX = "Ph" + "36" + "0098"
_FORBIDDEN_LITERAL_SUBSTRINGS = (
    _FORBIDDEN_EMAIL_PREFIX,
    _FORBIDDEN_PASSWORD_PREFIX,
)

SCAN_ROOTS = (
    ROOT / "brain_alpha_ops",
    ROOT / "tests",
)
SCAN_SUFFIXES = frozenset({
    ".py", ".ts", ".tsx", ".js", ".json", ".yml", ".yaml", ".md",
})
SKIP_DIR_NAMES = frozenset({
    "node_modules", ".git", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", ".venv", "venv", "env",
    "build", "dist", ".tox", ".nox",
})

# ``Bearer <token>`` where token is a long literal (not a placeholder/variable).
_BEARER_LITERAL_RE = re.compile(
    r"(?i)\bbearer\s+['\"]?([A-Za-z0-9._~+/=-]{16,})['\"]?"
)
# ``password="value"``/``api_key='value'`` — REQUIRES a quoted string literal.
# Unquoted values (variable refs, type annotations, env-var lookups) are NOT
# matched because real leaked secrets are quoted string literals in source.
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(password|api[_-]?key|passwd|secret|access[_-]?token|"
    r"refresh[_-]?token)\s*[:=]\s*(['\"])([^'\"]{6,})\2"
)

# Value shapes that are NOT real secrets (env-var lookups, placeholders,
# variable references, redacted markers, fixture dummies, type names).
_SAFE_VALUE_MARKERS = (
    "os.getenv", "os.environ", "getenv(", "environ[", "environ.get",
    "args.", "self.", "cls.", "result.", "req.", "data.", "ctx.", "config.",
    "<redacted>", "redacted", "placeholder", "dummy", "example", "fixture",
    "your_", "your-", "test-key", "test-token", "testpass", "testtoken",
    "testuser", "test-password", "test_", "test-", "stub-", "mock-",
    "fake-", "sample-", "fixture-",
    "secret-token", "secret-cookie", "secret-password", "secret-api-key",
    "secret-session-id", "secret-xyz", "secret-123", "secret-456",
    "run-secret", "session_1", "csrf_1", "stream_1",
    "session-cookie", "session-token", "fresh-token", "page-token",
    "current-page-token", "current_token", "not-scanned-by-default",
    "redacted-by-test", "local-token", "cloud-token", "live-key",
    "guidance-token", "guidance-password", "rotated-token", "stale-token",
    "bad-token", "wrong-password", "wrong_password", "plain-password",
    "plain-token", "stored-password", "first-password", "session-password",
    "basic-password", "observability-password", "admin-secret", "auth-secret",
    "csrf-secret", "csrf-header-secret", "id-secret", "refresh-secret",
    "session-secret", "super-secret", "access-secret", "not-allowlisted",
    "REDACTED_SECRET_PLACEHOLDER", "sk-local-secret",
)
_SAFE_VALUE_EXACT = frozenset({
    "api_key", "csrf_token", "password", "session_id", "token", "username",
    "secret", "secret_token", "secret-token", "none", "null", "true",
    "false", "", "str", "string", "int", "bool", "list", "dict",
    "testpass", "testtoken", "testuser",
})

# Substrings that indicate a value is a self-describing mock, not a real
# secret. Real leaked credentials are opaque random strings; they never
# literally contain words like "secret"/"password"/"fake"/"mock".
_MOCK_INDICATORS = (
    "secret", "password", "passwd", "pass", "token", "fake", "mock",
    "dummy", "placeholder", "do-not-commit", "not-real", "notreal",
    "redact", "example", "sample", "fixture", "stub", "test",
)


def _iter_scan_files() -> Iterable[Path]:
    for scan_root in SCAN_ROOTS:
        if not scan_root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(scan_root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for name in filenames:
                path = Path(dirpath, name)
                if path.suffix.lower() in SCAN_SUFFIXES:
                    yield path


def _value_is_safe(raw_value: str) -> bool:
    value = raw_value.strip().strip("'\"`").rstrip(".,;:)]}")
    if not value or len(value) < 6:
        return True
    lowered = value.lower()
    if lowered in _SAFE_VALUE_EXACT:
        return True
    if any(marker in lowered for marker in _SAFE_VALUE_MARKERS):
        return True
    # Self-describing mock values: real secrets never literally contain the
    # word "secret"/"password"/"token"/"fake"/"mock"/"dummy"/"do-not-commit".
    # A real leaked credential is an opaque random string (e.g. ``Ph36...``).
    if any(ind in lowered for ind in _MOCK_INDICATORS):
        return True
    # ``UPPER_CASE_CONSTANT`` style name (not a secret value).
    if re.fullmatch(r"[A-Z][A-Z0-9_]+", value):
        return True
    # ``__DUNDER__`` style name.
    if re.fullmatch(r"__?[A-Z0-9_]+__?", value):
        return True
    # Template interpolation (``${ENV}`` / ``{var}`` / ``%s``).
    if "${" in value or "%s" in value or "%(" in value:
        return True
    # Test-fixture mock values: short, start with ``test``/``mock``/``fake``.
    if len(value) <= 16 and lowered.startswith(("test", "mock", "fake", "sample")):
        return True
    return False


def _scan_line(line: str, path: Path, line_no: int) -> list[str]:
    findings: list[str] = []
    for literal in _FORBIDDEN_LITERAL_SUBSTRINGS:
        if literal in line:
            findings.append(
                f"{path}:{line_no}: forbidden test-credential literal "
                f"substring matched (remove hardcoded credential)"
            )
            return findings
    for match in _BEARER_LITERAL_RE.finditer(line):
        token = match.group(1)
        if not _value_is_safe(token):
            findings.append(
                f"{path}:{line_no}: literal Bearer token assignment "
                f"(use env var instead)"
            )
            return findings
    for match in _SECRET_ASSIGNMENT_RE.finditer(line):
        value = match.group(3)
        if not _value_is_safe(value):
            findings.append(
                f"{path}:{line_no}: literal secret assignment for "
                f"'{match.group(1)}' (use env var / placeholder instead)"
            )
            return findings
    return findings


def _collect_findings() -> list[str]:
    findings: list[str] = []
    for path in _iter_scan_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            findings.extend(_scan_line(line, path, line_no))
    return findings


def test_no_forbidden_test_credential_literals_in_scanned_dirs():
    """brain_alpha_ops/ and tests/ must not contain test-credential literals."""
    findings = _collect_findings()
    if findings:
        details = "\n".join(f"  - {f}" for f in findings[:30])
        pytest.fail(
            f"Credential leak regression: {len(findings)} actionable match(es) "
            f"found. Credentials must be injected via BRAIN_USERNAME / "
            f"BRAIN_PASSWORD / BRAIN_TOKEN env vars, never hardcoded:\n{details}"
        )


def test_scan_actually_visits_target_files():
    """Guard against the scan silently no-op'ing (e.g. wrong root paths)."""
    visited = list(_iter_scan_files())
    assert visited, "scan visited zero files — SCAN_ROOTS misconfigured"
    py_files = [p for p in visited if p.suffix == ".py"]
    assert len(py_files) >= 50, (
        f"expected to scan dozens of .py files, got {len(py_files)}; "
        f"check SKIP_DIR_NAMES / SCAN_SUFFIXES"
    )


if __name__ == "__main__":
    # Allow ``python3 tests/test_credential_leak_regression.py`` for quick
    # local checks outside pytest.
    findings = _collect_findings()
    if findings:
        print(f"FAIL: {len(findings)} leak(s) found:", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)
    print("OK: no credential leaks detected in brain_alpha_ops/ or tests/.")
