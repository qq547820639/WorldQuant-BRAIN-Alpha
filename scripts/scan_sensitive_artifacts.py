"""Scan local logs/data for accidentally persisted credentials.

This script is read-only. It prints redacted findings and does not modify files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain_alpha_ops.redaction import redact_text


DEFAULT_SCAN_DIRS = ("data",)
DEFAULT_SCAN_GLOBS = ("*.log", "*.json", "*.jsonl", "*.txt", "*.md", "*.err", "*.ps1", "*.bat", "*.cmd")
DEFAULT_ROOT_FILES = ("server.out.log", "server.err.log", "server.verify.out.log", "server.verify.err.log")
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

SECRET_KEY_PATTERN = (
    r"(?i)(?:"
    r"['\"]?\b([A-Z0-9_]*_?(?:access_token|api[_-]?key|csrf|password|secret|session[_-]?(?:id|key|token)|token))\b['\"]?"
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


def iter_candidate_files(root: Path, include_all: bool) -> list[Path]:
    paths: set[Path] = set()
    if include_all:
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            if _is_skipped(current, root, include_all=include_all):
                dirnames[:] = []
                continue
            dirnames[:] = [name for name in dirnames if name not in _skip_dirs(include_all)]
            for filename in filenames:
                path = current / filename
                if path.suffix.lower() in TEXT_SUFFIXES:
                    paths.add(path)
    else:
        for directory in DEFAULT_SCAN_DIRS:
            scan_root = root / directory
            if scan_root.exists():
                for pattern in DEFAULT_SCAN_GLOBS:
                    paths.update(path for path in scan_root.rglob(pattern) if path.is_file() and not _is_skipped(path, root, include_all=include_all))
        for filename in DEFAULT_ROOT_FILES:
            path = root / filename
            if path.is_file():
                paths.add(path)
    return sorted(paths)


def _skip_dirs(include_all: bool) -> set[str]:
    return SKIP_DIRS if include_all else SKIP_DIRS | DEFAULT_ONLY_SKIP_DIRS


def _is_skipped(path: Path, root: Path, *, include_all: bool) -> bool:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        relative_parts = path.parts
    skip_dirs = _skip_dirs(include_all)
    return any(
        part in skip_dirs
        or part.endswith(".egg-info")
        or part.startswith(".codex_tmp_")
        or part.startswith("build_")
        or part.startswith("dist_")
        for part in relative_parts
    )


def scan_file(path: Path, root: Path, max_bytes: int) -> list[dict]:
    try:
        size = path.stat().st_size
        if size > max_bytes:
            text = _sample_large_text_file(path, max(1, max_bytes))
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    findings: list[dict] = []
    findings.extend(_scan_known_secret_hashes(text, str(path.relative_to(root))))
    for line_number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in FINDING_PATTERNS.items():
            match = pattern.search(line)
            if not match:
                continue
            if _match_is_placeholder_fixture(line, path, root):
                continue
            if name == "secret_key" and not _secret_key_match_is_actionable(match, line, path):
                continue
            if name == "cookie" and not _cookie_match_is_actionable(line):
                continue
            display_path = str(path.relative_to(root))
            snippet = redact_text(line.strip(), max_length=220)
            findings.append({
                "type": name,
                "path": display_path,
                "line": line_number,
                "snippet": snippet,
                "message": f"{display_path}:{line_number}: {snippet}",
            })
            break
    return findings


def _sample_large_text_file(path: Path, max_bytes: int) -> str:
    """Read bounded head/tail samples from very large text logs."""
    sample_size = max(1, max_bytes // 2)
    with path.open("rb") as handle:
        head = handle.read(sample_size)
        try:
            handle.seek(max(0, path.stat().st_size - sample_size))
        except OSError:
            return head.decode("utf-8", errors="replace")
        tail = handle.read(sample_size)
    return head.decode("utf-8", errors="replace") + "\n" + tail.decode("utf-8", errors="replace")


def _scan_known_secret_hashes(text: str, display_path: str, *, git_object: str = "") -> list[dict]:
    findings: list[dict] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for token in _candidate_secret_tokens(line):
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            label = KNOWN_SECRET_HASHES_BY_DIGEST.get(token_hash)
            if not label:
                continue
            snippet = redact_text(line.replace(token, "<redacted>"), max_length=220)
            finding_type = "known_secret_hash_git_history" if git_object else "known_secret_hash"
            finding = {
                "type": finding_type,
                "path": display_path,
                "line": line_number,
                "secret_label": label,
                "snippet": snippet,
            }
            if git_object:
                finding["git_object"] = git_object[:12]
                finding["message"] = f"{git_object[:12]}:{display_path}:{line_number}: {label}: {snippet}"
            else:
                finding["message"] = f"{display_path}:{line_number}: {label}: {snippet}"
            findings.append(finding)
            break
    return findings


KNOWN_SECRET_HASHES_BY_DIGEST = {digest: label for label, digest in KNOWN_SECRET_HASHES.items()}


def _candidate_secret_tokens(line: str) -> set[str]:
    tokens: set[str] = set()
    for match in re.finditer(r"[A-Za-z0-9][A-Za-z0-9._@+\-/=]{3,}", line):
        token = match.group(0).strip("'\"`.,;:()[]{}<>")
        if token:
            tokens.add(token)
            if "@" in token:
                tokens.add(token.split("@", 1)[0])
    return tokens


def _match_is_placeholder_fixture(line: str, path: Path, root: Path) -> bool:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        relative_parts = path.parts
    if not relative_parts or relative_parts[0] not in {"tests", "docs"}:
        return False
    lowered = line.lower()
    return any(
        marker in lowered
        for marker in (
            "secret-token",
            "wrong-password",
            "wrong_password",
            "fixture-token",
            "dummy-token",
            "placeholder-token",
            "not-scanned-by-default",
            "current_token",
            "<redacted>",
            "redacted-by-test",
            "auth failed for ***@***",
            "sk-local-secret",
            "local-token",
            "cloud-token",
            "guidance-token",
            "guidance-password",
            "observability-password",
            "test-key",
            "test-token",
            "stale-token",
            "bad-token",
            "stub-token",
            "secret456",
            "secret-api-key",
            "secret-session-id",
            "index damaged token",
            "provider down token",
            "token=<redacted>",
            "cookie=session_",
            "session_1",
            "csrf_1",
            "stream_1",
        )
    )


def _secret_key_match_is_actionable(match: re.Match, line: str, path: Path) -> bool:
    token = str(match.group(0) or "")
    value = token.split("=", 1)[-1] if "=" in token else token.split(":", 1)[-1]
    value = value.strip().strip("'\"`").rstrip(")]},")
    lowered_line = line.lower()
    lowered_value = value.lower()
    if len(value) < 8:
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


def scan_artifacts(root: Path, *, include_all: bool = False, max_bytes: int = 5_000_000) -> dict:
    root = root.resolve()
    files = iter_candidate_files(root, include_all)
    findings: list[dict] = []
    for path in files:
        findings.extend(scan_file(path, root, max(1, max_bytes)))
    return {
        "ok": not findings,
        "schema_version": "sensitive_artifact_scan.v1",
        "root": str(root),
        "include_all": include_all,
        "checked": len(files),
        "findings": findings,
    }


def scan_git_history(root: Path, *, max_bytes: int = 5_000_000) -> dict:
    root = root.resolve()
    objects_result = _run_git(root, ["rev-list", "--objects", "--all"])
    if objects_result.returncode != 0:
        return {
            "ok": False,
            "schema_version": "git_history_sensitive_scan.v1",
            "root": str(root),
            "checked": 0,
            "findings": [{
                "type": "git_history_scan_error",
                "path": ".git",
                "line": 0,
                "snippet": redact_text(objects_result.stderr.strip() or objects_result.stdout.strip(), max_length=220),
                "message": "failed to enumerate git history",
            }],
        }
    findings: list[dict] = []
    checked = 0
    seen_objects: set[str] = set()
    for raw_line in objects_result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        object_id, _, rel_path = line.partition(" ")
        if not rel_path or object_id in seen_objects:
            continue
        if _git_history_path_is_skipped(rel_path):
            continue
        if Path(rel_path).suffix.lower() not in TEXT_SUFFIXES:
            continue
        size_result = _run_git(root, ["cat-file", "-s", object_id])
        if size_result.returncode != 0:
            continue
        try:
            if int(size_result.stdout.strip()) > max_bytes:
                continue
        except ValueError:
            continue
        show_result = _run_git(root, ["cat-file", "-p", object_id])
        if show_result.returncode != 0:
            continue
        seen_objects.add(object_id)
        checked += 1
        text = show_result.stdout
        findings.extend(_scan_known_secret_hashes(text, rel_path, git_object=object_id))
    return {
        "ok": not findings,
        "schema_version": "git_history_sensitive_scan.v1",
        "root": str(root),
        "checked": checked,
        "known_secret_hashes": sorted(KNOWN_SECRET_HASHES),
        "findings": findings,
    }


def _run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _git_history_path_is_skipped(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    return any(
        part in GIT_HISTORY_SKIP_DIRS
        or part.endswith(".egg-info")
        or part.startswith(".codex_tmp_")
        or part.startswith("build_")
        or part.startswith("dist_")
        for part in parts
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan logs/data for accidentally persisted credentials.")
    parser.add_argument("--root", default=".", help="Workspace root to scan.")
    parser.add_argument("--include-all", action="store_true", help="Scan all text-like files outside skipped directories.")
    parser.add_argument("--include-git-history", action="store_true", help="Also scan Git history for known leaked secret hashes.")
    parser.add_argument("--max-bytes", type=int, default=5_000_000, help="Skip files larger than this size.")
    parser.add_argument("--fail-on-findings", action="store_true", help="Exit with code 1 when findings are present.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = scan_artifacts(Path(args.root), include_all=args.include_all, max_bytes=args.max_bytes)
    if args.include_git_history:
        history_result = scan_git_history(Path(args.root), max_bytes=args.max_bytes)
        result["git_history"] = history_result
        result["findings"].extend(history_result["findings"])
        result["ok"] = result["ok"] and history_result["ok"]
    findings = result["findings"]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if findings and args.fail_on_findings else 0

    if not findings:
        print("No sensitive-looking artifacts found.")
        return 0

    print(f"Sensitive-looking artifacts found: {len(findings)}")
    for finding in findings:
        print(f"[{finding['type']}] {finding['message']}")
    return 1 if args.fail_on_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
