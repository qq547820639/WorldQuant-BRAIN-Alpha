"""Runtime result compaction and JSON-safe helpers for the task store.

These helpers keep the persisted payload narrow: large candidate lists are
replaced with counts + previews, and sensitive fragments are redacted.
"""
from __future__ import annotations

import json
from typing import Any

from brain_alpha_ops.redaction import redact_data

from . import COMPACT_LIST_KEYS, JOB_PREVIEW_ROWS


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _compact_runtime_result(value: Any, *, preview_rows: int = JOB_PREVIEW_ROWS) -> Any:
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in value.items():
            if _should_compact_named_list(key, item):
                compact[f"{key}_count"] = len(item)
                compact[f"{key}_preview"] = [_compact_runtime_result(row, preview_rows=preview_rows) for row in item[:preview_rows]]
                evidence = _submission_evidence_rows(item, preview_rows=preview_rows)
                if evidence:
                    compact[f"{key}_submission_evidence"] = evidence
                continue
            compact[key] = _compact_runtime_result(item, preview_rows=preview_rows)
        return compact
    if isinstance(value, list):
        if len(value) > preview_rows:
            return {
                "items_count": len(value),
                "items_preview": [_compact_runtime_result(item, preview_rows=preview_rows) for item in value[:preview_rows]],
            }
        return [_compact_runtime_result(item, preview_rows=preview_rows) for item in value]
    return value


def _should_compact_named_list(key: str, item: Any) -> bool:
    if not isinstance(item, list):
        return False
    return key in COMPACT_LIST_KEYS or key.endswith("candidates")


def _submission_evidence_rows(items: list[Any], *, preview_rows: int) -> list[Any]:
    evidence: list[Any] = []
    hidden_start = max(0, int(preview_rows or 0))
    seen: set[str] = {
        _submission_evidence_key(item)
        for item in items[:hidden_start]
        if isinstance(item, dict)
    }
    for item in items[hidden_start:]:
        if not isinstance(item, dict):
            continue
        compact = _candidate_submission_audit_evidence(item, preview_rows=preview_rows)
        key = _submission_evidence_key(compact)
        if key in seen:
            continue
        seen.add(key)
        evidence.append(compact)
    return evidence


def _candidate_submission_audit_evidence(candidate: dict[str, Any], *, preview_rows: int) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for key in (
        "alpha_id",
        "official_alpha_id",
        "simulation_id",
        "expression",
        "family",
        "hypothesis",
        "dataset_id",
        "data_fields",
        "operators",
        "alpha_output_config",
        "quality_diagnosis",
        "local_quality",
        "source_tags",
        "lifecycle_status",
        "decision_band",
        "score",
    ):
        if key in candidate:
            evidence[key] = candidate[key]
    for key, nested_keys in (
        ("scorecard", ("total_score", "decision_band", "status", "hard_gate_failed")),
        ("gate", ("submission_ready", "status", "blocking_reasons")),
        (
            "official_metrics",
            (
                "official_alpha_id",
                "pass_fail",
                "sharpe",
                "fitness",
                "turnover",
                "returns",
                "drawdown",
                "correlation",
                "prod_correlation",
            ),
        ),
        (
            "metrics",
            (
                "official_alpha_id",
                "pass_fail",
                "sharpe",
                "fitness",
                "turnover",
                "returns",
                "drawdown",
                "correlation",
                "prod_correlation",
            ),
        ),
        ("cloud_correlation_risk", ("level", "max_similarity", "status", "matched_alpha_id", "matched_expression")),
    ):
        nested = candidate.get(key) if isinstance(candidate.get(key), dict) else {}
        if nested:
            evidence[key] = {
                nested_key: nested[nested_key]
                for nested_key in nested_keys
                if nested_key in nested
            }
    submission = candidate.get("submission") if isinstance(candidate.get("submission"), dict) else {}
    local_backtest = submission.get("local_backtest") if isinstance(submission.get("local_backtest"), dict) else {}
    if local_backtest:
        evidence["submission"] = {
            "local_backtest": {
                key: local_backtest[key]
                for key in ("pass_local", "reasons", "diagnostics")
                if key in local_backtest
            }
        }
    return _compact_runtime_result(evidence, preview_rows=preview_rows)


def _submission_evidence_key(candidate: Any) -> str:
    if not isinstance(candidate, dict):
        return str(id(candidate))
    return str(
        candidate.get("alpha_id")
        or candidate.get("official_alpha_id")
        or candidate.get("simulation_id")
        or candidate.get("expression")
        or id(candidate)
    )


def _job_safe(value: Any) -> Any:
    safe = _json_safe(value)
    if isinstance(safe, dict) and "result" in safe:
        safe = dict(safe)
        safe["result"] = _compact_runtime_result(safe.get("result"))
    return redact_data(
        safe,
        key_fragments=("credential", "secret", "api_key", "session_token", "access_token", "refresh_token"),
    )
