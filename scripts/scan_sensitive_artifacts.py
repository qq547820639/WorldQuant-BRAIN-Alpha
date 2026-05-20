"""Scan local logs/data for accidentally persisted credentials.

This script is read-only. It prints redacted findings and does not modify files.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
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
    ".codex_pydeps",
    ".codex_tmp_quantgpt_src",
    "__pycache__",
    ".pytest_cache",
    ".superdesign",
    ".workbuddy",
    "build",
    "dist",
    "tests",
    "_archive_before_rebuild_20260512_152528",
}
TEXT_SUFFIXES = {".bat", ".cfg", ".cmd", ".conf", ".env", ".err", ".ini", ".json", ".jsonl", ".log", ".md", ".ps1", ".py", ".txt", ".yaml", ".yml"}

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
            if _is_skipped(current, root):
                dirnames[:] = []
                continue
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
            for filename in filenames:
                path = current / filename
                if path.suffix.lower() in TEXT_SUFFIXES:
                    paths.add(path)
    else:
        for directory in DEFAULT_SCAN_DIRS:
            scan_root = root / directory
            if scan_root.exists():
                for pattern in DEFAULT_SCAN_GLOBS:
                    paths.update(path for path in scan_root.rglob(pattern) if path.is_file() and not _is_skipped(path, root))
        for filename in DEFAULT_ROOT_FILES:
            path = root / filename
            if path.is_file():
                paths.add(path)
    return sorted(paths)


def _is_skipped(path: Path, root: Path) -> bool:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        relative_parts = path.parts
    return any(
        part in SKIP_DIRS
        or part.startswith(".codex_tmp_")
        or part.startswith("build_")
        or part.startswith("dist_")
        for part in relative_parts
    )


def scan_file(path: Path, root: Path, max_bytes: int) -> list[dict]:
    try:
        if path.stat().st_size > max_bytes:
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    findings: list[dict] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in FINDING_PATTERNS.items():
            match = pattern.search(line)
            if not match:
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


def _secret_key_match_is_actionable(match: re.Match, line: str, path: Path) -> bool:
    token = str(match.group(0) or "")
    value = token.split("=", 1)[-1] if "=" in token else token.split(":", 1)[-1]
    value = value.strip().strip("'\"`").rstrip(")]},")
    lowered_line = line.lower()
    lowered_value = value.lower()
    if len(value) < 8:
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
    if any(marker in lowered_value for marker in ("placeholder", "dummy", "example", "wrong-password", "wrong_password")):
        return False
    return True


def _cookie_match_is_actionable(line: str) -> bool:
    lowered = line.lower()
    if "<id>" in lowered or "<redacted>" in lowered or "<cookie>" in lowered:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan logs/data for accidentally persisted credentials.")
    parser.add_argument("--root", default=".", help="Workspace root to scan.")
    parser.add_argument("--include-all", action="store_true", help="Scan all text-like files outside skipped directories.")
    parser.add_argument("--max-bytes", type=int, default=5_000_000, help="Skip files larger than this size.")
    parser.add_argument("--fail-on-findings", action="store_true", help="Exit with code 1 when findings are present.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = scan_artifacts(Path(args.root), include_all=args.include_all, max_bytes=args.max_bytes)
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
