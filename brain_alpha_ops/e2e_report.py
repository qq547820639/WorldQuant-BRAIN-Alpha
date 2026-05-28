"""Build redacted E2E evidence summaries for delivery reports."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_data, redact_text


SCHEMA_VERSION = "e2e_artifact_summary.v1"
DEFAULT_EVIDENCE_DIR = Path("data/e2e_screenshots")
DEFAULT_JOB_LEDGER_PATHS = (
    Path("data/jobs_sync.json"),
    Path("data/jobs_production.json"),
    Path("data/jobs_check.json"),
)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_PREVIEW_BYTES = 2_000_000
CONSOLE_PREVIEW_LINES = 40
JOB_PREVIEW_LIMIT = 5
LIST_PREVIEW_LIMIT = 8
SKIPPED_RESULT_KEYS = {
    "alphas",
    "alphas_preview",
    "archive",
    "backtests",
    "candidates",
    "candidate_preview",
    "cloud_alphas",
    "lifecycle_records",
    "raw",
    "ready_results",
}
RESULT_SUMMARY_KEYWORDS = (
    "attempted",
    "available",
    "best_score",
    "blocked",
    "cache",
    "cancel",
    "count",
    "deferred",
    "failed",
    "halt",
    "limit",
    "mode",
    "ok",
    "operators",
    "passed",
    "pending",
    "produced",
    "range",
    "ready",
    "rejected",
    "scanned",
    "simulated",
    "skipped",
    "status",
    "submitted",
    "sync",
    "total",
    "updated",
)


def build_e2e_artifact_summary(
    *,
    root: str | Path = ".",
    evidence_dir: str | Path = DEFAULT_EVIDENCE_DIR,
    job_ledger_paths: tuple[str | Path, ...] = DEFAULT_JOB_LEDGER_PATHS,
    console_preview_lines: int = CONSOLE_PREVIEW_LINES,
    job_preview_limit: int = JOB_PREVIEW_LIMIT,
) -> dict[str, Any]:
    """Return a compact, redacted summary of E2E screenshots, logs, and job ledgers."""

    root_path = Path(root).resolve()
    evidence_path = _resolve_under_root(root_path, evidence_dir)
    redacted_keys: set[str] = set()

    files = _index_evidence_files(root_path, evidence_path)
    category_counts = Counter(file["category"] for file in files)
    console_logs = _read_console_logs(
        root_path,
        evidence_path,
        max_lines=max(1, int(console_preview_lines or 1)),
    )
    summaries = _read_summary_jsons(root_path, evidence_path)
    job_ledgers = [
        _read_job_ledger(root_path, path, limit=max(1, int(job_preview_limit or 1)))
        for path in job_ledger_paths
    ]
    web_console_contract = _read_web_console_contract(root_path)

    payload: dict[str, Any] = {
        "ok": evidence_path.is_dir(),
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root_path),
        "evidence_dir": _display_path(evidence_path, root_path),
        "file_counts": dict(sorted(category_counts.items())),
        "files_indexed": len(files),
        "screenshots": [file for file in files if file["category"] == "screenshot"],
        "dom_snapshots": [file for file in files if file["category"] == "dom_snapshot"],
        "console_logs": console_logs,
        "summaries": summaries,
        "web_console_contract": web_console_contract,
        "job_ledgers": job_ledgers,
        "sensitive_handling": {
            "redaction_applied": True,
            "redacted_keys": [],
            "notes": [
                "emails, auth headers, token-like fragments, and sensitive key values are redacted",
                "artifact contents are summarized rather than copied wholesale",
            ],
        },
    }
    if not evidence_path.exists():
        payload["warnings"] = [f"evidence directory not found: {_display_path(evidence_path, root_path)}"]

    redacted = redact_data(payload, redacted_keys=redacted_keys)
    if isinstance(redacted, dict):
        redacted.setdefault("sensitive_handling", {})["redacted_keys"] = sorted(redacted_keys)
    return redacted


def render_markdown_summary(payload: dict[str, Any]) -> str:
    """Render a short Markdown delivery artifact from a summary payload."""

    lines = [
        "# E2E Artifact Summary",
        "",
        f"- Schema: `{payload.get('schema_version', '')}`",
        f"- Generated at: `{payload.get('generated_at', '')}`",
        f"- Evidence directory: `{payload.get('evidence_dir', '')}`",
        f"- Indexed files: `{payload.get('files_indexed', 0)}`",
        f"- Overall status: `{'PASS' if payload.get('ok') else 'WARN'}`",
        "",
        "## Evidence Files",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for category, count in sorted((payload.get("file_counts") or {}).items()):
        lines.append(f"| {category} | {count} |")

    lines.extend([
        "",
        "## Job Ledgers",
        "",
        "| Ledger | Jobs | Latest status | Latest job | Error |",
        "|---|---:|---|---|---|",
    ])
    for ledger in payload.get("job_ledgers") or []:
        latest = ledger.get("latest_job") or {}
        error = _markdown_cell(str(latest.get("error") or ""))
        lines.append(
            "| "
            f"{ledger.get('path', '')} | "
            f"{ledger.get('job_count', 0)} | "
            f"{latest.get('status', '')} | "
            f"{latest.get('job_id', '')} | "
            f"{error or '-'} |"
        )

    lines.extend([
        "",
        "## Browser Summaries",
        "",
        "| File | Service | Connection | Production run | Submitted |",
        "|---|---|---|---|---:|",
    ])
    for summary in payload.get("summaries") or []:
        data = summary.get("summary") or {}
        connection = data.get("connection") or {}
        production = data.get("production_run") or {}
        lines.append(
            "| "
            f"{summary.get('path', '')} | "
            f"{_markdown_cell(str(data.get('service_url') or '')) or '-'} | "
            f"{connection.get('ok', '')} {connection.get('environment', '')} | "
            f"{production.get('status', '')} {production.get('job_id', '')} | "
            f"{production.get('submitted_this_run', 0)} |"
        )

    lines.extend([
        "",
        "## Historical Console Notes",
        "",
        "- These lines come from captured E2E logs; the current shipped HTML contract is checked separately below.",
    ])
    notable_lines: list[str] = []
    for log in payload.get("console_logs") or []:
        severities = ", ".join(f"{key}={value}" for key, value in (log.get("severity_counts") or {}).items())
        notable_lines.append(
            f"- `{log.get('path', '')}`: lines={log.get('line_count', 0)}, "
            f"notable={log.get('notable_count', 0)}, severities={severities or '-'}"
        )
    lines.extend(notable_lines or ["- No console warnings or errors were captured in the preview."])

    contract = payload.get("web_console_contract") or {}
    facts = contract.get("facts") or {}
    lines.extend([
        "",
        "## Current Web Contract",
        "",
        f"- Status: `{'PASS' if contract.get('ok') else 'WARN'}`",
        f"- Favicon links: `{facts.get('favicon_count', 0)}`",
        f"- Connection form: `{facts.get('connection_form_tag') or '-'}`",
        f"- Password field inside form: `{bool(facts.get('password_inside_connection_form'))}`",
        f"- Test connection button: `type={facts.get('conn_test_button_type') or '-'}, action={facts.get('conn_test_button_action') or '-'}`",
        f"- Lifecycle wiring: `{'PASS' if all((facts.get('lifecycle_snippets') or {}).values()) else 'WARN'}`",
    ])

    sensitive = payload.get("sensitive_handling") or {}
    lines.extend([
        "",
        "## Sensitive Handling",
        "",
        f"- Redaction applied: `{bool(sensitive.get('redaction_applied'))}`",
        f"- Redacted keys: `{', '.join(sensitive.get('redacted_keys') or []) or '-'}`",
        "- Full credential values are not copied into this summary.",
        "",
    ])
    return "\n".join(lines)


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


def _read_job_ledger(root: Path, path: str | Path, *, limit: int) -> dict[str, Any]:
    ledger_path = _resolve_under_root(root, path)
    if not ledger_path.is_file():
        return {
            "path": _display_path(ledger_path, root),
            "exists": False,
            "job_count": 0,
            "status_counts": {},
            "latest_job": None,
            "jobs_preview": [],
        }

    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": _display_path(ledger_path, root),
            "exists": True,
            "ok": False,
            "error": redact_text(exc, max_length=240),
            "job_count": 0,
            "status_counts": {},
            "latest_job": None,
            "jobs_preview": [],
        }

    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else {}
    if not isinstance(raw_jobs, dict):
        raw_jobs = {}
    jobs = sorted(
        ((str(job_id), row) for job_id, row in raw_jobs.items() if isinstance(row, dict)),
        key=lambda item: _numeric(item[1].get("updated_at")),
        reverse=True,
    )
    status_counts = Counter(str(row.get("status") or "unknown") for _, row in jobs)
    preview = [_summarize_job(job_id, row) for job_id, row in jobs[:limit]]
    return {
        "path": _display_path(ledger_path, root),
        "exists": True,
        "ok": True,
        "version": payload.get("version") if isinstance(payload, dict) else None,
        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
        "job_count": len(jobs),
        "status_counts": dict(sorted(status_counts.items())),
        "latest_job": preview[0] if preview else None,
        "jobs_preview": preview,
    }


def _read_web_console_contract(root: Path) -> dict[str, Any]:
    html_path = root / "brain_alpha_ops" / "web" / "index.html"
    if not html_path.is_file():
        return {
            "ok": False,
            "schema_version": "web_console_contract_check.v1",
            "html": _display_path(html_path, root),
            "facts": {},
            "findings": [{"code": "missing_html", "expected": str(html_path), "message": "HTML file does not exist"}],
        }
    try:
        from scripts.check_web_console_contract import check_web_console_contract
    except Exception as exc:  # pragma: no cover - defensive for packaged use without scripts.
        return {
            "ok": False,
            "schema_version": "web_console_contract_check.v1",
            "html": _display_path(html_path, root),
            "facts": {},
            "findings": [
                {
                    "code": "checker_unavailable",
                    "expected": "scripts.check_web_console_contract",
                    "message": redact_text(exc, max_length=240),
                }
            ],
        }
    result = check_web_console_contract(html_path)
    result["html"] = _display_path(Path(result.get("html") or html_path), root)
    return result


def _summarize_job(job_id: str, row: dict[str, Any]) -> dict[str, Any]:
    progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    return {
        "job_id": job_id,
        "status": row.get("status"),
        "cancel": bool(row.get("cancel")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "error": redact_text(row.get("error") or "", max_length=240),
        "progress": _compact_value(
            {
                "phase": progress.get("phase"),
                "percent": progress.get("percent"),
                "message": progress.get("message"),
                "status_code": progress.get("status_code"),
                "current": progress.get("current"),
                "total": progress.get("total"),
                "scanned": progress.get("scanned"),
                "failed": progress.get("failed"),
            }
        ),
        "result_summary": _summarize_result(summary or result),
    }


def _summarize_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    summary: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        normalized = key_text.lower()
        if normalized in SKIPPED_RESULT_KEYS or normalized.endswith("_preview"):
            continue
        if isinstance(item, list):
            summary[f"{key_text}_count"] = len(item)
            continue
        if isinstance(item, dict):
            if normalized.endswith("_stats") or normalized.endswith("_counts"):
                summary[key_text] = _compact_value(item, depth=2)
            continue
        if _is_result_summary_key(normalized):
            summary[key_text] = _compact_value(item, depth=2)
        if len(summary) >= 48:
            summary["truncated_keys"] = max(0, len(value) - len(summary))
            break
    return summary


def _is_result_summary_key(normalized_key: str) -> bool:
    return any(keyword in normalized_key for keyword in RESULT_SUMMARY_KEYWORDS)


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _summarize_leaf(value)
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) == "remaining_observations" and isinstance(item, list):
                compact["remaining_observations_count"] = len(item)
                continue
            if len(compact) >= 32:
                compact["truncated_keys"] = max(0, len(value) - len(compact))
                break
            compact[str(key)] = _compact_value(item, depth=depth + 1)
        return compact
    if isinstance(value, list):
        if len(value) > LIST_PREVIEW_LIMIT:
            return {
                "items_count": len(value),
                "items_preview": [_compact_value(item, depth=depth + 1) for item in value[:LIST_PREVIEW_LIMIT]],
            }
        return [_compact_value(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return redact_text(value, max_length=500)
    return value


def _summarize_leaf(value: Any) -> Any:
    if isinstance(value, dict):
        return {"keys_count": len(value), "keys_preview": [str(key) for key in list(value)[:LIST_PREVIEW_LIMIT]]}
    if isinstance(value, list):
        return {"items_count": len(value)}
    if isinstance(value, str):
        return redact_text(value, max_length=240)
    return value


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
    return any(marker in lowered for marker in ("[error]", "[warning]", "error", "warning", "failed"))


def _console_line_severity(line: str) -> str:
    lowered = line.lower()
    if "[error]" in lowered or "error" in lowered or "failed" in lowered:
        return "error"
    if "[warning]" in lowered or "warning" in lowered:
        return "warning"
    if "[verbose]" in lowered:
        return "verbose"
    return "info"


def _read_text(path: Path, *, max_bytes: int) -> str:
    try:
        data = path.read_bytes()[:max(1, max_bytes)]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def _resolve_under_root(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _numeric(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")[:240]
