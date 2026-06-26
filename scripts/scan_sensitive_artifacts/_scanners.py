"""Sensitive-artifact scan logic: file iteration, scanning, and CLI entry.

Split from the former ``scan_sensitive_artifacts.py`` monolith (Workstream F3.9).
Read-only: prints redacted findings and does not modify files. Patterns and
match-actionability predicates live in ``_patterns``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from brain_alpha_ops.redaction import redact_text

from ._patterns import (
    DEFAULT_ONLY_SKIP_DIRS,
    DEFAULT_ROOT_FILES,
    DEFAULT_SCAN_DIRS,
    DEFAULT_SCAN_GLOBS,
    FINDING_PATTERNS,
    GIT_HISTORY_SKIP_DIRS,
    KNOWN_SECRET_HASHES,
    KNOWN_SECRET_HASHES_BY_DIGEST,
    SKIP_DIRS,
    TEXT_SUFFIXES,
    _candidate_secret_tokens,
    _cookie_match_is_actionable,
    _match_is_placeholder_fixture,
    _secret_key_match_is_actionable,
)


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
        line_has_finding = False
        for name, pattern in FINDING_PATTERNS.items():
            for match in pattern.finditer(line):
                if _match_is_placeholder_fixture(match, path, root):
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
                line_has_finding = True
                break
            if line_has_finding:
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


def scan_artifacts(root: Path, *, include_all: bool = False, max_bytes: int = 5_000_000) -> dict:
    root = root.resolve()
    files = iter_candidate_files(root, include_all)
    findings: list[dict] = []
    for path in files:
        findings.extend(scan_file(path, root, max(1, max_bytes)))
    return {
        "actionable_ok": not any(f for f in findings if f.get("type") not in ("known_secret_hash", "known_secret_hash_git_history")),
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
        "actionable_ok": not any(f for f in findings if f.get("type") not in ("known_secret_hash", "known_secret_hash_git_history")),
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


def _actionable_findings(findings: list) -> list:
    """Filter out known_secret_hash findings that are not actionable."""
    return [f for f in findings if f.get("type") != "known_secret_hash"]


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
        return 1 if _actionable_findings(findings) and args.fail_on_findings else 0

    if not findings:
        print("No sensitive-looking artifacts found.")
        return 0

    print(f"Sensitive-looking artifacts found: {len(findings)}")
    for finding in findings:
        print(f"[{finding['type']}] {finding['message']}")
    return 1 if args.fail_on_findings else 0
