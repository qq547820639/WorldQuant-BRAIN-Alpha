"""Security scan script — scans codebase for common security issues.

Checks for:
  1. Leaked secrets (API keys, tokens, passwords)
  2. Hardcoded credentials (username/password assignments)
  3. Insecure requests (http:// URLs)
  4. CORS misconfiguration (Access-Control-Allow-Origin: *)
  5. Dangerous file writes (os.system, subprocess with shell=True)
  6. Test artifact leaks (test data, mock credentials in production paths)

Outputs a JSON report. Exit code 1 if blocking items found (for CI gating).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git", ".venv", "node_modules", "__pycache__", ".mypy_cache",
    ".ruff_cache", ".pytest_cache", "build", "dist", ".playwright-cli",
    ".codex_pydeps", ".codex_tmp_quantgpt_src", ".superdesign",
    ".codebuddy", ".workbuddy", "_codex_tools", "output",
}
TEXT_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".env", ".sh", ".bat", ".ps1",
    ".md", ".txt", ".html", ".css",
}

SECRET_PATTERNS = [
    (r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "hardcoded API key"),
    (r"(?:secret|secret[_-]?key)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "hardcoded secret"),
    (r"(?:token|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "hardcoded token"),
    (r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", "embedded Bearer token"),
]

CREDENTIAL_PATTERNS = [
    (r"(?:password|passwd|pwd)\s*[:=]\s*['\"][^'\"\\s]{4,}['\"]", "hardcoded password"),
    (r"(?:username|user)\s*[:=]\s*['\"][^'\"\\s]{4,}['\"]", "hardcoded username"),
]

INSECURE_URL_PATTERN = re.compile(r"""(?:requests?\.(?:get|post|put|delete|patch)\s*\(\s*['\"]http://|fetch\s*\(\s*['\"]http://|url\s*=\s*['\"]http://)['\"]""")

CORS_PATTERN = re.compile(r"""Access[_-]Control[_-]Allow[_-]Origin['\"]?\s*[:=]\s*['\"]?\*['\"]?""", re.IGNORECASE)

DANGEROUS_WRITE_PATTERNS = [
    (r"os\.system\s*\(", "os.system() call"),
    (r"subprocess\..*shell\s*=\s*True", "subprocess with shell=True"),
    (r"eval\s*\(", "eval() call"),
    (r"exec\s*\(", "exec() call"),
]

TEST_ARTIFACT_PATTERNS = [
    (r"['\"](?:test_user|test_pass|mock_token|fake_key|dummy_secret)['\"]", "test artifact credential"),
    (r"known_brain_(?:account|password)_sha256", "test secret hash"),
]


def _should_skip(path: Path) -> bool:
    parts = path.relative_to(ROOT).parts
    return any(p in SKIP_DIRS for p in parts)


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def scan_file(path: Path) -> list[dict[str, Any]]:
    """Scan a single file for security issues."""
    findings = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return findings

    lines = content.splitlines()
    rel = str(path.relative_to(ROOT))

    all_patterns = [
        (SECRET_PATTERNS, "secret_leak", "blocking"),
        (CREDENTIAL_PATTERNS, "hardcoded_credential", "blocking"),
        (DANGEROUS_WRITE_PATTERNS, "dangerous_call", "blocking"),
        (TEST_ARTIFACT_PATTERNS, "test_artifact_leak", "warning"),
    ]

    for line_num, line in enumerate(lines, 1):
        for pattern_set, category, severity in all_patterns:
            for pattern, description in pattern_set:
                if re.search(pattern, line):
                    findings.append({
                        "file": rel,
                        "line": line_num,
                        "category": category,
                        "description": description,
                        "severity": severity,
                    })

    for line_num, line in enumerate(lines, 1):
        if INSECURE_URL_PATTERN.search(line):
            findings.append({
                "file": rel,
                "line": line_num,
                "category": "insecure_url",
                "description": "HTTP URL used instead of HTTPS",
                "severity": "warning",
            })

    for line_num, line in enumerate(lines, 1):
        if CORS_PATTERN.search(line):
            findings.append({
                "file": rel,
                "line": line_num,
                "category": "cors_misconfig",
                "description": "CORS wildcard (*) detected",
                "severity": "blocking",
            })

    return findings


def scan_repository(root: Path | None = None) -> dict[str, Any]:
    """Scan the entire repository for security issues."""
    root = root or ROOT
    all_findings: list[dict[str, Any]] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip(path):
            continue
        if not _is_text_file(path):
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
        except OSError:
            continue
        all_findings.extend(scan_file(path))

    blocking = [f for f in all_findings if f["severity"] == "blocking"]
    warnings = [f for f in all_findings if f["severity"] == "warning"]

    return {
        "total_findings": len(all_findings),
        "blocking": len(blocking),
        "warnings": len(warnings),
        "blocking_items": blocking,
        "warning_items": warnings,
        "categories": _count_by_category(all_findings),
    }


def _count_by_category(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        cat = f["category"]
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Security scan for WorldQuant-BRAIN-Alpha")
    parser.add_argument("--root", type=str, default=None, help="Root directory to scan")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--fail-on-warnings", action="store_true", help="Exit 1 on warnings too")
    args = parser.parse_args()

    root = Path(args.root) if args.root else ROOT
    report = scan_repository(root)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Security Scan Report")
        print(f"{'=' * 40}")
        print(f"Total findings: {report['total_findings']}")
        print(f"Blocking:       {report['blocking']}")
        print(f"Warnings:       {report['warnings']}")
        print()
        if report["categories"]:
            print("By category:")
            for cat, count in sorted(report["categories"].items()):
                print(f"  {cat}: {count}")
            print()
        for item in report["blocking_items"]:
            print(f"[BLOCKING] {item['file']}:{item['line']} — {item['description']}")
        for item in report["warning_items"]:
            print(f"[WARNING]  {item['file']}:{item['line']} — {item['description']}")

    has_blocking = report["blocking"] > 0
    has_warnings = report["warnings"] > 0
    if has_blocking or (args.fail_on_warnings and has_warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
