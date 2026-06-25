"""Markdown rendering and JSON serialization for diagnostic snapshots.

The renderer produces a compact one-page Markdown report that operators can
read in the web console or save to disk for audit trails.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_one_page_markdown(snapshot: dict[str, Any]) -> str:
    """Render the diagnosis as a compact one-page Markdown report."""
    redline = snapshot["redline"]
    context = snapshot["official_context"]
    refresh = snapshot.get("official_refresh", {})
    scoring = snapshot["scoring_probe"]
    history = snapshot.get("history_replay", {})
    lines = [
        "# Alpha Production Diagnosis and Gap Matrix",
        "",
        f"- Generated: {snapshot['generated_at']}",
        f"- Environment: {snapshot['environment']}",
        f"- Verdict: {_report_verdict(snapshot)}",
        f"- Red lines: {redline['overall']} ({redline['passed']}/{redline['total_checks']} passed, {redline['failed']} blocking)",
        f"- Official context: fields={context['fields']}, operators={context['operators']}, datasets={context['datasets']}",
        (
            f"- Parameter audit: hash={snapshot.get('parameter_audit', {}).get('config_hash', '')[:12]}, "
            f"sections={len(snapshot.get('parameter_audit', {}).get('traceable_sections', []))}, "
            f"thresholds_zero_deviation={snapshot.get('parameter_audit', {}).get('thresholds_zero_deviation', False)}"
        ),
        (
            f"- Context validation: blocking_ok={snapshot.get('official_context_validation', {}).get('blocking_ok', False)}, "
            f"p1_findings={snapshot.get('official_context_validation', {}).get('p1_count', 0)}, "
            f"dataset_field_count_sum={snapshot.get('official_context_validation', {}).get('lineage', {}).get('dataset_field_count_sum', 0)}"
        ),
        (
            f"- Official refresh: status={refresh.get('status', 'unknown')}, "
            f"source={refresh.get('source', 'unknown')}, files={refresh.get('file_count', 0)}, "
            f"stale={refresh.get('stale_count', 0)}, last_attempt={refresh.get('last_attempt_status', 'not_recorded')}"
        ),
        f"- Scoring probe: status={scoring['api_status']}, zero_deviation={scoring['zero_deviation']}, score={scoring['total_score']}",
        (
            f"- History replay: capability={history.get('capability', 'unknown')}, "
            f"history_count={history.get('history_count', 0)}, "
            f"latest_comparison={history.get('latest_comparison_available', False)}"
        ),
        "",
        "## Gap Matrix",
        "",
        "| Dimension | State | Gap | Severity | Evidence | Upgrade |",
        "|---|---|---|---|---|---|",
    ]
    for row in snapshot["gap_matrix"]:
        lines.append(
            "| {dimension} | {current_state} | {gap} | {severity} | {evidence} | {upgrade} |".format(
                **{key: _md_cell(value) for key, value in row.items()}
            )
        )
    lines.extend(["", "## Priority Attack List", ""])
    if snapshot["priority_items"]:
        for item in snapshot["priority_items"]:
            lines.append(
                f"- **{item['priority']} {item['area']}**: {item['finding']} "
                f"Fix: {item['fix']} Validation: `{item['validation']}`"
            )
    else:
        lines.append("- No blocking or executable attack item remains in the current diagnostic snapshot.")
    lines.extend(["", "## Current Execution Checklist", ""])
    completed = snapshot.get("completed_items") or []
    unfinished = snapshot.get("unfinished_items") or []
    lines.append("### Completed")
    for item in completed:
        lines.append(f"- [x] {item}")
    lines.append("")
    lines.append("### Unfinished")
    if unfinished:
        for item in unfinished:
            lines.append(f"- [ ] {item}")
    else:
        lines.append("- None in the current local code checklist.")
    lines.extend(["", "## QuantGPT-Aligned Upgrade Plan", ""])
    for item in snapshot["upgrade_plan"]:
        lines.append(f"- **{item['priority']} {item['area']}**: {item['recommendation']}")
    return "\n".join(lines) + "\n"


def write_diagnostic_report(path: str | Path, snapshot: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_one_page_markdown(snapshot), encoding="utf-8")
    return target


def snapshot_to_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _report_verdict(snapshot: dict[str, Any]) -> str:
    refresh = snapshot.get("official_refresh") or {}
    if refresh.get("last_attempt_ok") is False:
        return "ACTION REQUIRED"
    if any(str(item).startswith("P0 ") or str(item).startswith("P1 ") for item in snapshot.get("unfinished_items") or []):
        return "ACTION REQUIRED"
    return "PASS" if snapshot.get("ok") else "ACTION REQUIRED"
