"""Submit-readiness payload service shared by web route entrypoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from brain_alpha_ops.redaction import redact_error_message


ReadinessCheck = Callable[[], dict[str, Any]]


def run_live_submit_readiness_check() -> dict[str, Any]:
    from scripts.check_live_submit_readiness import check_live_submit_readiness

    return check_live_submit_readiness()


def submit_readiness_payload(run_check: ReadinessCheck | None = None) -> dict[str, Any]:
    checker = run_check or run_live_submit_readiness_check
    try:
        result = checker()
    except Exception as exc:
        result = {"ok": False, "error": redact_error_message(exc)}
    if not isinstance(result, dict):
        result = {"ok": False, "error": "submit readiness check returned an invalid payload"}
    return compact_submit_readiness_payload(result)


def compact_submit_readiness_payload(result: dict[str, Any]) -> dict[str, Any]:
    summary_counts = dict(result.get("summary_counts") or {})
    best_candidate = result.get("best_candidate") if isinstance(result.get("best_candidate"), dict) else {}
    production_gap_summary = (
        result.get("production_gap_summary") if isinstance(result.get("production_gap_summary"), dict) else {}
    )
    payload = {
        "ok": bool(result.get("ok", True)),
        "source": "check_live_submit_readiness.py",
        "official_api_called": False,
        "ready_to_submit": bool(result.get("ready_to_submit")),
        "ledger_ready_to_submit": bool(result.get("ledger_ready_to_submit")),
        "job_family_ready_to_submit": bool(result.get("job_family_ready_to_submit")),
        "candidate_count": safe_int(result.get("candidate_count")),
        "ledger_candidate_count": safe_int(result.get("ledger_candidate_count")),
        "job_family_candidate_count": safe_int(result.get("job_family_candidate_count")),
        "eligible_count": safe_int(result.get("eligible_count")),
        "ledger_eligible_count": safe_int(result.get("ledger_eligible_count")),
        "job_family_eligible_count": safe_int(result.get("job_family_eligible_count")),
        "latest_job_id": str(result.get("latest_job_id") or ""),
        "latest_job_status": str(result.get("latest_job_status") or ""),
        "summary_counts": summary_counts,
        "top_blocking_reasons": counter_rows(result.get("latest_blocking_reason_counts")),
        "top_family_blocking_reasons": counter_rows(result.get("job_family_blocking_reason_counts")),
        "production_gaps": [
            {"code": str(row.get("code") or ""), "message": str(row.get("message") or "")}
            for row in production_gap_summary.get("gaps", [])
            if isinstance(row, dict)
        ],
        "findings": [
            {"code": str(row.get("code") or ""), "message": str(row.get("message") or "")}
            for row in result.get("findings", [])
            if isinstance(row, dict)
        ],
        "best_candidate": {
            "alpha_id": str(best_candidate.get("alpha_id") or ""),
            "official_alpha_id": str(best_candidate.get("official_alpha_id") or ""),
            "lifecycle_status": str(best_candidate.get("lifecycle_status") or ""),
            "score": best_candidate.get("score"),
            "decision_band": str(best_candidate.get("decision_band") or ""),
            "local_backtest_passed": bool(best_candidate.get("local_backtest_passed")),
            "max_similarity": best_candidate.get("max_similarity"),
            "risk_level": str(best_candidate.get("risk_level") or ""),
            "blocking_reasons": [
                str(reason) for reason in best_candidate.get("blocking_reasons", []) if str(reason)
            ],
        },
        "required_next_steps": submit_readiness_next_steps(result),
    }
    payload["ready"] = payload["ready_to_submit"]
    return payload


def counter_rows(counter: object) -> list[dict[str, int]]:
    if not isinstance(counter, dict):
        return []
    rows: list[tuple[str, int]] = []
    for key, value in counter.items():
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        rows.append((str(key), count))
    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(rows, key=lambda item: (-item[1], item[0]))
    ]


def submit_readiness_next_steps(result: dict[str, Any]) -> list[str]:
    if result.get("ready_to_submit"):
        return ["review final submission intent before any real submit"]
    steps = ["run official simulation/check in a trusted environment"]
    if safe_int(result.get("eligible_count")) <= 0:
        steps.append("resolve local blockers before submit review")
    return steps


def safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
