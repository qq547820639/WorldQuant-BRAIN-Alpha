"""Shared production submission evidence checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.expression_ast import expression_key


REQUIRED_OFFICIAL_METRIC_FIELDS = (
    ("sharpe",),
    ("fitness",),
    ("turnover",),
    ("self_correlation",),
    ("prod_correlation",),
    ("weight_concentration",),
    ("sub_universe_sharpe", "subUniverseSharpe"),
)


def live_submit_readiness_hard_gate(
    candidate: dict[str, Any],
    run_config: Any,
    official_id: str = "",
    *,
    readiness_check: Any | None = None,
) -> dict[str, Any]:
    """Fail-closed gate that proves the same candidate is live-submit eligible."""
    try:
        result = _run_live_submit_readiness_check(run_config, readiness_check=readiness_check)
    except Exception as exc:
        return _readiness_block(
            "SUBMIT_READINESS_CHECK_FAILED",
            "Live submit readiness check failed; production submit is blocked.",
            action="Rerun submit readiness and fix the reported error before submitting.",
            readiness_summary={"error": redact_error_message(exc, max_length=200)},
        )
    return submit_readiness_hard_gate(candidate, result, official_id=official_id)


def submit_readiness_hard_gate(
    candidate: dict[str, Any],
    readiness_result: dict[str, Any],
    *,
    official_id: str = "",
) -> dict[str, Any]:
    """Return ok only when readiness proves this exact candidate is eligible."""
    if not isinstance(readiness_result, dict):
        return _readiness_block(
            "SUBMIT_READINESS_INVALID",
            "Live submit readiness returned an invalid payload; production submit is blocked.",
            action="Rerun submit readiness and inspect its output before submitting.",
            readiness_summary={},
        )

    summary = _readiness_summary(readiness_result)
    if readiness_result.get("ok") is False:
        return _readiness_block(
            "SUBMIT_READINESS_CHECK_FAILED",
            "Live submit readiness reported an evidence error; production submit is blocked.",
            action="Fix the submit-readiness evidence and rerun the gate before submitting.",
            readiness_summary=summary,
        )
    if not readiness_result.get("ready_to_submit") or _safe_int(readiness_result.get("eligible_count")) <= 0:
        return _readiness_block(
            "SUBMIT_READINESS_NOT_READY",
            "check_live_submit_readiness.py has not reported a submit-ready candidate.",
            action="Run official checks, refresh readiness, and submit only after ready_to_submit=true.",
            readiness_summary=summary,
        )

    eligible_candidates = readiness_result.get("eligible_candidates")
    if not isinstance(eligible_candidates, list) or not eligible_candidates:
        return _readiness_block(
            "SUBMIT_READINESS_ELIGIBLE_EVIDENCE_MISSING",
            "Readiness is green globally but did not include auditable eligible candidate evidence.",
            action="Rerun submit readiness with complete candidate evidence before submitting.",
            readiness_summary=summary,
        )

    target = _candidate_match_keys(candidate, official_id=official_id)
    if not target["official_alpha_id"] or not target["expression_key"]:
        return _readiness_block(
            "SUBMIT_READINESS_CANDIDATE_EVIDENCE_INSUFFICIENT",
            "Candidate is missing the official Alpha ID or expression needed to prove readiness.",
            action="Refresh the candidate from official simulation evidence before submitting.",
            readiness_summary=summary,
        )

    for item in eligible_candidates:
        if isinstance(item, dict) and _readiness_candidate_matches(target, item):
            return {
                "ok": True,
                "readiness_summary": summary,
                "matched_readiness_candidate": {
                    "alpha_id": str(item.get("alpha_id") or ""),
                    "official_alpha_id": str(item.get("official_alpha_id") or ""),
                    "job_id": str(item.get("job_id") or ""),
                    "job_ledger": str(item.get("job_ledger") or ""),
                },
            }

    return _readiness_block(
        "SUBMIT_READINESS_CANDIDATE_MISMATCH",
        "Live submit readiness did not prove this same official Alpha ID and expression are eligible.",
        action="Select the candidate shown as eligible by check_live_submit_readiness.py, or rerun official checks for this candidate.",
        readiness_summary=summary,
    )


def missing_official_metric_fields(metrics: dict[str, Any]) -> list[str]:
    """Return canonical metric field groups missing from official evidence."""
    missing: list[str] = []
    for aliases in REQUIRED_OFFICIAL_METRIC_FIELDS:
        if not any(metrics.get(alias) not in ("", None) for alias in aliases):
            missing.append("/".join(aliases))
    return missing


def _run_live_submit_readiness_check(run_config: Any, *, readiness_check: Any | None) -> dict[str, Any]:
    if readiness_check is None:
        from scripts.check_live_submit_readiness import check_live_submit_readiness

        readiness_check = check_live_submit_readiness
    storage_dir = str(getattr(getattr(run_config, "ops", run_config), "storage_dir", "") or "")
    jobs_path = Path(storage_dir) / "jobs_production.json" if storage_dir else None
    if jobs_path is not None:
        return readiness_check(jobs_path)
    return readiness_check()


def _candidate_match_keys(candidate: dict[str, Any], *, official_id: str = "") -> dict[str, str]:
    metrics = candidate.get("official_metrics") if isinstance(candidate.get("official_metrics"), dict) else {}
    expression = str(candidate.get("expression") or "").strip()
    return {
        "alpha_id": str(candidate.get("alpha_id") or "").strip(),
        "official_alpha_id": str(official_id or candidate.get("official_alpha_id") or metrics.get("official_alpha_id") or "").strip(),
        "expression_key": expression_key(expression) if expression else "",
    }


def _readiness_candidate_matches(target: dict[str, str], item: dict[str, Any]) -> bool:
    item_expression = str(item.get("expression") or "").strip()
    item_keys = {
        "alpha_id": str(item.get("alpha_id") or "").strip(),
        "official_alpha_id": str(item.get("official_alpha_id") or "").strip(),
        "expression_key": expression_key(item_expression) if item_expression else "",
    }
    if item_keys["official_alpha_id"] != target["official_alpha_id"]:
        return False
    if item_keys["expression_key"] != target["expression_key"]:
        return False
    if target["alpha_id"] and item_keys["alpha_id"] and item_keys["alpha_id"] != target["alpha_id"]:
        return False
    if item.get("eligible") is False:
        return False
    blocking_reasons = item.get("blocking_reasons")
    return not blocking_reasons


def _readiness_block(
    error_code: str,
    error: str,
    *,
    action: str,
    readiness_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": error_code,
        "error_category": "readiness",
        "error": error,
        "action": action,
        "readiness_summary": readiness_summary,
        "state_navigation": {
            "schema_version": "abnormal_state_navigation.v1",
            "state": "blocked",
            "reason_code": error_code,
            "title": "提交就绪门禁未通过",
            "summary": "check_live_submit_readiness.py 未证明当前候选可以真实提交，已在调用官方提交 API 前阻断。",
            "target_view": "submit",
            "primary_action": "刷新官方检查和提交就绪证据后再提交。",
        },
    }


def _readiness_summary(result: dict[str, Any]) -> dict[str, Any]:
    findings = result.get("findings") if isinstance(result.get("findings"), list) else []
    return {
        "schema_version": result.get("schema_version", ""),
        "source": "check_live_submit_readiness.py",
        "ok": result.get("ok"),
        "ready_to_submit": bool(result.get("ready_to_submit")),
        "eligible_count": _safe_int(result.get("eligible_count")),
        "candidate_count": _safe_int(result.get("candidate_count")),
        "ledger_eligible_count": _safe_int(result.get("ledger_eligible_count")),
        "job_family_eligible_count": _safe_int(result.get("job_family_eligible_count")),
        "latest_job_id": str(result.get("latest_job_id") or ""),
        "finding_codes": [str(item.get("code") or "") for item in findings if isinstance(item, dict) and item.get("code")][:8],
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
