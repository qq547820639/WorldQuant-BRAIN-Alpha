"""Candidate selection helpers shared by web check and submit flows."""

from __future__ import annotations

from typing import Any, Protocol


class JobStoreLike(Protocol):
    def get(self, job_id: str) -> dict[str, Any] | None:
        ...


def candidate_from_payload(payload: dict[str, Any], job_store: JobStoreLike) -> dict[str, Any]:
    candidate = payload.get("candidate")
    if isinstance(candidate, dict):
        return candidate
    alpha_id = str(payload.get("alpha_id", ""))
    job = job_store.get(str(payload.get("job_id", ""))) or {}
    pools: list[dict[str, Any]] = []
    result = job.get("result") or {}
    pools.extend(result.get("candidates") or [])
    pools.extend((result.get("summary") or {}).get("passed_candidates") or [])
    data = (job.get("progress") or {}).get("data") or {}
    pools.extend(data.get("candidates") or [])
    pools.extend(data.get("passed_candidates") or [])
    for item in pools:
        if isinstance(item, dict) and item.get("alpha_id") == alpha_id:
            return item
    return {}


def passed_candidates_from_payload(payload: dict[str, Any], job_store: JobStoreLike) -> list[dict[str, Any]]:
    candidates = payload.get("check_candidates")
    if not isinstance(candidates, list):
        candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        job = job_store.get(str(payload.get("job_id", ""))) or {}
        result = job.get("result") or {}
        data = (job.get("progress") or {}).get("data") or {}
        candidates = []
        candidates.extend((result.get("summary") or {}).get("passed_candidates") or [])
        candidates.extend(data.get("passed_candidates") or [])
        candidates.extend(result.get("candidates") or [])
        candidates.extend(data.get("candidates") or [])
    seen = set()
    passed: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        alpha_id = str(candidate.get("alpha_id", ""))
        if not alpha_id or alpha_id in seen:
            continue
        if is_passed_candidate_for_check(candidate):
            seen.add(alpha_id)
            passed.append(candidate)
    return passed


def candidate_official_metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    metrics = candidate.get("official_metrics")
    if isinstance(metrics, dict):
        return metrics
    metrics = candidate.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def official_alpha_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("official_alpha_id") or (candidate.get("official_metrics") or {}).get("official_alpha_id") or "")


def is_passed_candidate_for_check(candidate: dict[str, Any]) -> bool:
    gate = candidate.get("gate") or {}
    if gate.get("submission_ready") or candidate.get("lifecycle_status") == "submission_ready":
        return True
    metrics = candidate_official_metrics(candidate)
    pass_fail = str(metrics.get("pass_fail", "")).strip().upper()
    return pass_fail == "PASS" and bool(official_alpha_id(candidate))
