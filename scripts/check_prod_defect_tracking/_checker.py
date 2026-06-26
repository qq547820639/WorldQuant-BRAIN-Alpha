"""Production defect tracking evidence validator."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import ConfigValidationError, load_run_config

from ._constants import (
    DEFAULT_CONFIG,
    DEFAULT_JOBS,
    DEFAULT_REPORT,
    EXPECTED_GENERATION_CONFIG,
    EXPECTED_SUBMISSION_POLICY,
    EXPECTED_THRESHOLDS,
    REQUIRED_PROD_007_SNIPPETS,
    REQUIRED_PROD_012_SNIPPETS,
    REQUIRED_PROD_013_SNIPPETS,
    REQUIRED_PROD_014_SNIPPETS,
    REQUIRED_PROD_015_SNIPPETS,
    REQUIRED_PROD_016_SNIPPETS,
    REQUIRED_PROD_017_SNIPPETS,
    REQUIRED_PROD_018_SNIPPETS,
    REQUIRED_PROD_019_SNIPPETS,
    REQUIRED_PROD_020_SNIPPETS,
    REQUIRED_PROD_021_SNIPPETS,
    REQUIRED_PROD_022_SNIPPETS,
    REQUIRED_PROD_023_SNIPPETS,
    REQUIRED_PROD_024_SNIPPETS,
    REQUIRED_PROD_025_SNIPPETS,
    REQUIRED_PROD_IDS,
    REQUIRED_VALIDATION_SNIPPETS,
    SCHEMA_VERSION,
)
from ._gate_invariants import _check_readiness_gate_invariants, _finding


def check_prod_defect_tracking(
    report_path: str | Path = DEFAULT_REPORT,
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    jobs_path: str | Path = DEFAULT_JOBS,
    readiness_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = Path(report_path)
    findings: list[dict[str, str]] = []
    try:
        text = report.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "report": str(report),
            "findings": [_finding("missing_report", str(report), "production defect report does not exist")],
        }

    rows = _tracking_rows(text, findings)
    rows_by_id = {row["id"]: row for row in rows}
    for defect_id in REQUIRED_PROD_IDS:
        if defect_id not in rows_by_id:
            findings.append(_finding("missing_prod_tracking_row", defect_id, "PROD tracking row is missing"))

    prod_007 = rows_by_id.get("PROD-007")
    if prod_007 is not None:
        if prod_007["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_007_status", "CLOSED_CURRENT", "PROD-007 must be tracked as closed for current code"))
        prod_007_text = " | ".join(prod_007.values())
        for snippet in REQUIRED_PROD_007_SNIPPETS:
            if snippet not in prod_007_text:
                findings.append(_finding("prod_007_evidence", snippet, "PROD-007 row is missing required evidence"))

    prod_012 = rows_by_id.get("PROD-012")
    if prod_012 is not None:
        if prod_012["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_012_status", "CLOSED_CURRENT", "PROD-012 must be tracked as closed for current code"))
        prod_012_text = " | ".join(prod_012.values())
        for snippet in REQUIRED_PROD_012_SNIPPETS:
            if snippet not in prod_012_text:
                findings.append(_finding("prod_012_evidence", snippet, "PROD-012 row is missing required evidence"))

    prod_013 = rows_by_id.get("PROD-013")
    if prod_013 is not None:
        if prod_013["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_013_status", "CLOSED_CURRENT", "PROD-013 must be tracked as closed for current code"))
        prod_013_text = " | ".join(prod_013.values())
        for snippet in REQUIRED_PROD_013_SNIPPETS:
            if snippet not in prod_013_text:
                findings.append(_finding("prod_013_evidence", snippet, "PROD-013 row is missing required evidence"))

    prod_014 = rows_by_id.get("PROD-014")
    if prod_014 is not None:
        if prod_014["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_014_status", "CLOSED_CURRENT", "PROD-014 must be tracked as closed for current code"))
        prod_014_text = " | ".join(prod_014.values())
        for snippet in REQUIRED_PROD_014_SNIPPETS:
            if snippet not in prod_014_text:
                findings.append(_finding("prod_014_evidence", snippet, "PROD-014 row is missing required evidence"))

    prod_015 = rows_by_id.get("PROD-015")
    if prod_015 is not None:
        if prod_015["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_015_status", "CLOSED_CURRENT", "PROD-015 must be tracked as closed for current code"))
        prod_015_text = " | ".join(prod_015.values())
        for snippet in REQUIRED_PROD_015_SNIPPETS:
            if snippet not in prod_015_text:
                findings.append(_finding("prod_015_evidence", snippet, "PROD-015 row is missing required evidence"))

    prod_016 = rows_by_id.get("PROD-016")
    if prod_016 is not None:
        if prod_016["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_016_status", "CLOSED_CURRENT", "PROD-016 must be tracked as closed for current code"))
        prod_016_text = " | ".join(prod_016.values())
        for snippet in REQUIRED_PROD_016_SNIPPETS:
            if snippet not in prod_016_text:
                findings.append(_finding("prod_016_evidence", snippet, "PROD-016 row is missing required evidence"))

    prod_017 = rows_by_id.get("PROD-017")
    if prod_017 is not None:
        if prod_017["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_017_status", "CLOSED_CURRENT", "PROD-017 must be tracked as closed for current code"))
        prod_017_text = " | ".join(prod_017.values())
        for snippet in REQUIRED_PROD_017_SNIPPETS:
            if snippet not in prod_017_text:
                findings.append(_finding("prod_017_evidence", snippet, "PROD-017 row is missing required evidence"))

    prod_018 = rows_by_id.get("PROD-018")
    if prod_018 is not None:
        if prod_018["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_018_status", "CLOSED_CURRENT", "PROD-018 must be tracked as closed for current code"))
        prod_018_text = " | ".join(prod_018.values())
        for snippet in REQUIRED_PROD_018_SNIPPETS:
            if snippet not in prod_018_text:
                findings.append(_finding("prod_018_evidence", snippet, "PROD-018 row is missing required evidence"))

    prod_019 = rows_by_id.get("PROD-019")
    if prod_019 is not None:
        if prod_019["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_019_status", "CLOSED_CURRENT", "PROD-019 must be tracked as closed for current code"))
        prod_019_text = " | ".join(prod_019.values())
        for snippet in REQUIRED_PROD_019_SNIPPETS:
            if snippet not in prod_019_text:
                findings.append(_finding("prod_019_evidence", snippet, "PROD-019 row is missing required evidence"))

    prod_020 = rows_by_id.get("PROD-020")
    if prod_020 is not None:
        if prod_020["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_020_status", "CLOSED_CURRENT", "PROD-020 must be tracked as closed for current code"))
        prod_020_text = " | ".join(prod_020.values())
        for snippet in REQUIRED_PROD_020_SNIPPETS:
            if snippet not in prod_020_text:
                findings.append(_finding("prod_020_evidence", snippet, "PROD-020 row is missing required evidence"))

    prod_021 = rows_by_id.get("PROD-021")
    if prod_021 is not None:
        if prod_021["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_021_status", "CLOSED_CURRENT", "PROD-021 must be tracked as closed for current code"))
        prod_021_text = " | ".join(prod_021.values())
        for snippet in REQUIRED_PROD_021_SNIPPETS:
            if snippet not in prod_021_text:
                findings.append(_finding("prod_021_evidence", snippet, "PROD-021 row is missing required evidence"))

    prod_022 = rows_by_id.get("PROD-022")
    if prod_022 is not None:
        if prod_022["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_022_status", "CLOSED_CURRENT", "PROD-022 must be tracked as closed for current code"))
        prod_022_text = " | ".join(prod_022.values())
        for snippet in REQUIRED_PROD_022_SNIPPETS:
            if snippet not in prod_022_text:
                findings.append(_finding("prod_022_evidence", snippet, "PROD-022 row is missing required evidence"))

    prod_023 = rows_by_id.get("PROD-023")
    if prod_023 is not None:
        if prod_023["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_023_status", "CLOSED_CURRENT", "PROD-023 must be tracked as closed for current code"))
        prod_023_text = " | ".join(prod_023.values())
        for snippet in REQUIRED_PROD_023_SNIPPETS:
            if snippet not in prod_023_text:
                findings.append(_finding("prod_023_evidence", snippet, "PROD-023 row is missing required evidence"))

    prod_024 = rows_by_id.get("PROD-024")
    if prod_024 is not None:
        if prod_024["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_024_status", "CLOSED_CURRENT", "PROD-024 must be tracked as closed for current code"))
        prod_024_text = " | ".join(prod_024.values())
        for snippet in REQUIRED_PROD_024_SNIPPETS:
            if snippet not in prod_024_text:
                findings.append(_finding("prod_024_evidence", snippet, "PROD-024 row is missing required evidence"))

    prod_025 = rows_by_id.get("PROD-025")
    if prod_025 is not None:
        if prod_025["status"] != "CLOSED_CURRENT":
            findings.append(_finding("prod_025_status", "CLOSED_CURRENT", "PROD-025 must be tracked as closed for current code"))
        prod_025_text = " | ".join(prod_025.values())
        for snippet in REQUIRED_PROD_025_SNIPPETS:
            if snippet not in prod_025_text:
                findings.append(_finding("prod_025_evidence", snippet, "PROD-025 row is missing required evidence"))

    for snippet in REQUIRED_VALIDATION_SNIPPETS:
        if snippet not in text:
            findings.append(_finding("validation_evidence_missing", snippet, "report is missing validation evidence"))

    config_summary = _check_config_thresholds(config_path, findings)
    if readiness_validation is not None:
        readiness = readiness_validation
    else:
        # Late binding so monkeypatch on
        # ``scripts.check_prod_defect_tracking.check_live_submit_readiness``
        # is honored (tests rely on this attribute lookup path).
        from scripts.check_prod_defect_tracking import check_live_submit_readiness

        readiness = check_live_submit_readiness(jobs_path)
    _check_readiness(readiness, findings)
    _check_readiness_gate_invariants(findings)

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "report": str(report),
        "tracked_prod_count": sum(1 for defect_id in REQUIRED_PROD_IDS if defect_id in rows_by_id),
        "config": str(config_path),
        "config_summary": config_summary,
        "readiness": {
            "ok": bool(readiness.get("ok")),
            "ready_to_submit": bool(readiness.get("ready_to_submit")),
            "eligible_count": int(readiness.get("eligible_count") or 0),
            "ledger_eligible_count": int(readiness.get("ledger_eligible_count") or 0),
            "job_family_eligible_count": int(readiness.get("job_family_eligible_count") or 0),
        },
        "findings": findings,
    }


def _tracking_rows(text: str, findings: list[dict[str, str]]) -> list[dict[str, str]]:
    section = _section(text, "Codex 实施追踪")
    if not section:
        findings.append(_finding("missing_tracking_section", "Codex 实施追踪", "tracking section is missing"))
        return []
    rows: list[dict[str, str]] = []
    in_table = False
    for line in section.splitlines():
        if not line.startswith("|"):
            if in_table:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0] == "缺陷" and cells[1] == "当前状态":
            in_table = True
            continue
        if in_table and cells and set(cells[0]) <= {"-", ":"}:
            continue
        if not in_table:
            continue
        if len(cells) < 4:
            findings.append(_finding("malformed_tracking_row", line, "tracking row has too few cells"))
            continue
        match = re.match(r"^(PROD-\d{3})\b", cells[0])
        if not match:
            continue
        rows.append(
            {
                "id": match.group(1),
                "defect": cells[0],
                "status": cells[1],
                "evidence": cells[2],
                "next_action": "|".join(cells[3:]).strip(),
            }
        )
    return rows


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    next_heading = text.find("\n## ", start + len(marker))
    return text[start:] if next_heading < 0 else text[start:next_heading]


def _check_config_thresholds(config_path: str | Path, findings: list[dict[str, str]]) -> dict[str, Any]:
    path = Path(config_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        findings.append(_finding("missing_config", str(path), "config file does not exist"))
        return {}
    except json.JSONDecodeError as exc:
        findings.append(_finding("invalid_config_json", str(path), f"config JSON is invalid: {exc}"))
        return {}

    ops = payload.get("ops") if isinstance(payload, dict) else {}
    thresholds = ops.get("thresholds") if isinstance(ops, dict) else {}
    submission_policy = ops.get("submission_policy") if isinstance(ops, dict) else {}
    summary: dict[str, Any] = {}
    for key, expected in EXPECTED_THRESHOLDS.items():
        actual = thresholds.get(key)
        summary[key] = actual
        if actual != expected:
            findings.append(_finding("threshold_mismatch", f"{key}={expected!r}", "configured threshold was changed"))
    for key, expected in EXPECTED_SUBMISSION_POLICY.items():
        actual = submission_policy.get(key)
        summary[key] = actual
        if actual != expected:
            findings.append(_finding("submission_policy_mismatch", f"{key}={expected!r}", "submission policy was changed"))
    try:
        runtime_config = load_run_config(path)
    except ConfigValidationError as exc:
        findings.append(_finding("invalid_runtime_config", "load_run_config succeeds", str(exc)))
    else:
        for key, expected in EXPECTED_GENERATION_CONFIG.items():
            actual = getattr(runtime_config.ops.budget, key)
            summary[key] = actual
            if actual != expected:
                findings.append(
                    _finding("generation_config_mismatch", f"{key}={expected!r}", "generation recovery config was changed")
                )
    return summary


def _check_readiness(readiness: dict[str, Any], findings: list[dict[str, str]]) -> None:
    if not readiness.get("ok"):
        findings.append(_finding("readiness_not_ok", "ok=true", "live submit readiness audit failed"))
    expected_zero_fields = ("eligible_count", "ledger_eligible_count", "job_family_eligible_count")
    if readiness.get("ready_to_submit"):
        findings.append(_finding("unexpected_ready_to_submit", "ready_to_submit=false", "report claims no eligible alpha"))
    for field in expected_zero_fields:
        if int(readiness.get(field) or 0) != 0:
            findings.append(_finding("unexpected_eligible_count", f"{field}=0", "report claims no eligible alpha"))
    best_candidate = readiness.get("best_candidate") if isinstance(readiness.get("best_candidate"), dict) else {}
    if best_candidate.get("local_backtest_passed") is False:
        reasons = best_candidate.get("blocking_reasons") if isinstance(best_candidate.get("blocking_reasons"), list) else []
        if "local_backtest_failed" not in reasons:
            findings.append(
                _finding(
                    "missing_local_backtest_blocker",
                    "local_backtest_failed",
                    "failed local backtest must be reflected in live submit readiness blockers",
                )
            )
