"""Assistant review and robustness endpoints for the local web API."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.research.anti_overfit import AntiOverfitService
from brain_alpha_ops.research.llm_review import cross_review_assistant_response
from brain_alpha_ops.research.rolling_validation import RollingValidationService


LatestSnapshot = Callable[[], dict[str, Any]]
BoundedFloat = Callable[[Any, float, float], float]

_CANDIDATE_LIST_KEYS = {
    "candidates",
    "passed_candidates",
    "pending_backtest_candidates",
    "accepted_candidates",
    "archive_samples",
    "retained_candidates",
    "ranked_candidates",
    "pool",
}


def anti_overfit_snapshot(
    *,
    candidate_id: str = "",
    latest_result_snapshot: LatestSnapshot,
) -> dict[str, Any]:
    """Find a recent candidate and run deterministic anti-overfit checks."""
    snapshot = latest_result_snapshot()
    candidates = _collect_candidates(snapshot)
    selected = _select_candidate(candidates, candidate_id)
    if selected is None:
        return {
            "ok": False,
            "error_code": "CANDIDATE_NOT_FOUND" if candidate_id else "CANDIDATE_ID_REQUIRED",
            "error_category": "validation",
            "retryable": False,
            "candidate_id": candidate_id,
            "available_candidate_ids": _available_candidate_ids(candidates)[:50],
        }
    report = AntiOverfitService().evaluate(selected)
    return {
        "ok": True,
        "schema_version": "anti_overfit_snapshot.v1",
        "candidate_id": _candidate_identifier(selected),
        "anti_overfit_report": report,
    }


def rolling_validation_snapshot(
    *,
    candidate_id: str = "",
    windows: int = 4,
    latest_result_snapshot: LatestSnapshot,
) -> dict[str, Any]:
    """Find a recent candidate and run rolling validation checks."""
    snapshot = latest_result_snapshot()
    candidates = _collect_candidates(snapshot)
    selected = _select_candidate(candidates, candidate_id)
    if selected is None:
        return {
            "ok": False,
            "error_code": "CANDIDATE_NOT_FOUND" if candidate_id else "CANDIDATE_ID_REQUIRED",
            "error_category": "validation",
            "retryable": False,
            "candidate_id": candidate_id,
            "available_candidate_ids": _available_candidate_ids(candidates)[:50],
        }
    report = RollingValidationService().evaluate(selected, windows=windows)
    return {
        "ok": True,
        "schema_version": "rolling_validation_snapshot.v1",
        "candidate_id": _candidate_identifier(selected),
        "rolling_validation_report": report,
    }


def assistant_cross_review_payload(
    payload: dict[str, Any],
    *,
    bounded_query_float: BoundedFloat,
) -> dict[str, Any]:
    """Normalize a POST payload and run provider-neutral assistant cross-review."""
    request_pack = payload.get("request_pack")
    if request_pack is None:
        request_pack = payload.get("request")
    if not isinstance(request_pack, dict):
        raise ValueError("request_pack must be an object")
    primary = payload.get("primary_response")
    if primary is None:
        primary = payload.get("primary")
    if primary is None:
        raise ValueError("primary_response is required")
    reviewer = payload.get("reviewer_response")
    if reviewer is None:
        reviewer = payload.get("reviewer")
    min_confidence = bounded_query_float(payload.get("min_confidence", 0.6), 0.0, 1.0)
    return cross_review_assistant_response(
        request_pack,
        primary,
        reviewer_response=reviewer,
        min_confidence=min_confidence,
    )


def _collect_candidates(value: Any, *, _depth: int = 0) -> list[dict[str, Any]]:
    if _depth > 8:
        return []
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            rows.extend(_collect_candidates(item, _depth=_depth + 1))
        return rows
    if not isinstance(value, dict):
        return rows
    if _looks_like_candidate(value):
        rows.append(value)
    for key, child in value.items():
        if key in _CANDIDATE_LIST_KEYS or isinstance(child, dict):
            rows.extend(_collect_candidates(child, _depth=_depth + 1))
        elif isinstance(child, list) and key in _CANDIDATE_LIST_KEYS:
            rows.extend(_collect_candidates(child, _depth=_depth + 1))
    return _dedupe_candidates(rows)


def _looks_like_candidate(value: dict[str, Any]) -> bool:
    return bool(
        value.get("expression")
        and (
            value.get("alpha_id")
            or value.get("id")
            or value.get("official_alpha_id")
            or value.get("simulation_id")
        )
    )


def _select_candidate(candidates: list[dict[str, Any]], candidate_id: str) -> dict[str, Any] | None:
    wanted = str(candidate_id or "").strip()
    if wanted:
        for candidate in candidates:
            if wanted in _candidate_identifiers(candidate):
                return candidate
        return None
    return candidates[0] if len(candidates) == 1 else None


def _candidate_identifiers(candidate: dict[str, Any]) -> set[str]:
    metrics = candidate.get("official_metrics") if isinstance(candidate.get("official_metrics"), dict) else {}
    submission = candidate.get("submission") if isinstance(candidate.get("submission"), dict) else {}
    return {
        str(value)
        for value in (
            candidate.get("alpha_id"),
            candidate.get("id"),
            candidate.get("official_alpha_id"),
            candidate.get("simulation_id"),
            metrics.get("official_alpha_id"),
            metrics.get("alpha_id"),
            submission.get("official_alpha_id"),
            submission.get("simulation_id"),
        )
        if str(value or "").strip()
    }


def _candidate_identifier(candidate: dict[str, Any]) -> str:
    ids = _candidate_identifiers(candidate)
    for key in ("alpha_id", "id", "official_alpha_id", "simulation_id"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    return sorted(ids)[0] if ids else ""


def _available_candidate_ids(candidates: list[dict[str, Any]]) -> list[str]:
    return [_candidate_identifier(candidate) for candidate in candidates if _candidate_identifier(candidate)]


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (_candidate_identifier(candidate), str(candidate.get("expression") or ""))
        if key in seen:
            continue
        seen.add(key)
        rows.append(candidate)
    return rows
