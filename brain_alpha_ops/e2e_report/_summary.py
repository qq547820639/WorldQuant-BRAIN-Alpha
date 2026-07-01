"""E2E artifact summary builder and markdown renderer."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.e2e_report._constants import (
    CONSOLE_PREVIEW_LINES,
    DEFAULT_EVIDENCE_DIR,
    DEFAULT_JOB_LEDGER_PATHS,
    JOB_PREVIEW_LIMIT,
    SCHEMA_VERSION,
    _display_path,
    _resolve_under_root,
)
from brain_alpha_ops.e2e_report._evidence import (
    _index_evidence_files,
    _read_console_logs,
    _read_summary_jsons,
)
from brain_alpha_ops.e2e_report._ledger import _read_job_ledger
from brain_alpha_ops.e2e_report._contract import _read_web_console_contract
from brain_alpha_ops.e2e_report._constants import _markdown_cell

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
