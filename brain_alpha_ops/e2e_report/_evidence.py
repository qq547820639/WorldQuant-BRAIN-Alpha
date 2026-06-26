"""Evidence file helpers for E2E report."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_text
from brain_alpha_ops.e2e_report._constants import (
    IMAGE_SUFFIXES,
    TEXT_PREVIEW_BYTES,
    _display_path,
    _read_text,
)
from brain_alpha_ops.e2e_report._ledger import _compact_value

def _index_evidence_files(root: Path, evidence_path: Path) -> list[dict[str, Any]]:
    if not evidence_path.is_dir():
        return []
    indexed: list[dict[str, Any]] = []
    for path in sorted(item for item in evidence_path.iterdir() if item.is_file()):
        try:
            stat = path.stat()
        except OSError:
            continue
        indexed.append(
            {
                "path": _display_path(path, root),
                "category": _classify_evidence_file(path),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            }
        )
    return indexed


def _classify_evidence_file(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "screenshot"
    if name.startswith("console-") or suffix in {".log", ".err"}:
        return "console_log"
    if suffix == ".json" and "summary" in name:
        return "summary_json"
    if name.endswith(".dom.txt") or name.endswith(".dom.yml") or name.endswith(".dom.yaml"):
        return "dom_snapshot"
    if suffix in {".yml", ".yaml", ".txt"}:
        return "dom_snapshot"
    return "other"


def _is_notable_console_line(line: str) -> bool:
    lowered = line.lower()
    return any(lowered.startswith(m) for m in ("[error]", "[warning]", "failed")) or any(f" {m}" in lowered or lowered.startswith(m) for m in ("error", "warning",))  # N-06: narrower matching


def _console_line_severity(line: str) -> str:
    lowered = line.lower()
    if "[error]" in lowered or "error" in lowered or "failed" in lowered:
        return "error"
    if "[warning]" in lowered or "warning" in lowered:
        return "warning"
    if "[verbose]" in lowered:
        return "verbose"
    return "info"


def _read_console_logs(root: Path, evidence_path: Path, *, max_lines: int) -> list[dict[str, Any]]:
    if not evidence_path.is_dir():
        return []
    logs = [
        path
        for path in evidence_path.iterdir()
        if path.is_file() and _classify_evidence_file(path) == "console_log"
    ]
    rows: list[dict[str, Any]] = []
    for path in sorted(logs, key=lambda item: item.stat().st_mtime, reverse=True):
        text = _read_text(path, max_bytes=TEXT_PREVIEW_BYTES)
        lines = text.splitlines()
        notable = [line for line in lines if _is_notable_console_line(line)]
        severities = Counter(_console_line_severity(line) for line in lines)
        rows.append(
            {
                "path": _display_path(path, root),
                "line_count": len(lines),
                "notable_count": len(notable),
                "severity_counts": dict(sorted(severities.items())),
            }
        )
    return rows


def _read_summary_jsons(root: Path, evidence_path: Path) -> list[dict[str, Any]]:
    if not evidence_path.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(evidence_path.glob("*summary*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            summary = _compact_value(data)
            ok = True
            error = ""
        except (OSError, json.JSONDecodeError) as exc:
            summary = {}
            ok = False
            error = redact_text(exc, max_length=240)
        rows.append(
            {
                "path": _display_path(path, root),
                "ok": ok,
                "error": error,
                "summary": summary,
            }
        )
    return rows
