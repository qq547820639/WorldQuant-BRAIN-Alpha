"""Ledger auditing helpers for live submit readiness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.live_submit_readiness_assessment import (
    assess_candidate as _assess_candidate,
    best_candidate as _best_candidate,
)

from ._candidates import (
    _blocking_reason_counts,
    _candidate_key,
    _dedupe_assessed_candidates,
    _dedupe_candidates,
    _merge_chain_summaries,
)
from ._constants import DEFAULT_JOB_LEDGER_GLOB, DEFAULT_SIMILARITY_THRESHOLD, SCHEMA_VERSION
from ._thresholds import _int, _threshold_summary


def _read_jobs_ledger(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"jobs ledger not found: {path}"
    except json.JSONDecodeError as exc:
        return None, f"jobs ledger is not valid JSON: {exc}"

    jobs = payload.get("jobs") if isinstance(payload, dict) else {}
    if not isinstance(jobs, dict) or not jobs:
        return None, f"jobs ledger does not contain any jobs: {path}"
    return jobs, None


def _job_ledger_paths(path: Path, related_jobs_paths: list[str | Path] | None) -> list[Path]:
    if related_jobs_paths is not None:
        paths = [Path(item) for item in related_jobs_paths]
    else:
        paths = sorted(path.parent.glob(DEFAULT_JOB_LEDGER_GLOB))
    if path not in paths:
        paths.append(path)
    unique: list[Path] = []
    seen: set[str] = set()
    for ledger_path in sorted(paths, key=lambda item: (item != path, item.name)):
        key = str(ledger_path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ledger_path)
    return unique


def _audit_ledger(
    jobs_path: Path,
    jobs: dict[str, Any],
    *,
    thresholds: QualityThresholds,
    similarity_threshold: float,
) -> dict[str, Any]:
    job_audits = _audit_jobs(jobs, thresholds=thresholds, similarity_threshold=similarity_threshold)
    latest_job_id = _latest_job_id(jobs)
    latest_job = jobs.get(latest_job_id) or {}
    latest_audit = next((item for item in job_audits if item["job_id"] == latest_job_id), {})
    assessed = [
        dict(item, job_id=latest_job_id, job_ledger=str(jobs_path), candidate_source="job_ledger")
        for item in (latest_audit.get("candidates") or [])
    ]
    eligible = [item for item in assessed if item["eligible"]]
    ledger_eligible = [
        dict(candidate, job_id=audit["job_id"], job_ledger=str(jobs_path), candidate_source="job_ledger")
        for audit in job_audits
        for candidate in audit["eligible_candidates"]
    ]
    ledger_candidates = [
        dict(candidate, job_id=audit["job_id"], job_ledger=str(jobs_path), candidate_source="job_ledger")
        for audit in job_audits
        for candidate in audit["candidates"]
    ]
    summary = ((latest_job.get("result") or {}).get("summary") or {}) if isinstance(latest_job, dict) else {}
    max_similarity_values = [
        item["max_similarity"] for item in assessed if isinstance(item.get("max_similarity"), (int, float))
    ]
    max_similarity = max(max_similarity_values) if max_similarity_values else None
    return {
        "jobs": str(jobs_path),
        "job_ledger": jobs_path.name,
        "jobs_checked": len(job_audits),
        "latest_job_id": latest_job_id,
        "latest_job_status": str(latest_job.get("status") or ""),
        "candidate_count": len(assessed),
        "eligible_count": len(eligible),
        "ledger_candidate_count": sum(int(item["candidate_count"]) for item in job_audits),
        "ledger_eligible_count": len(ledger_eligible),
        "ledger_ready_to_submit": bool(ledger_eligible),
        "ready_to_submit": bool(eligible),
        "human_confirmation_required": bool(eligible),
        "similarity_threshold": similarity_threshold,
        "threshold_summary": _threshold_summary(thresholds),
        "max_similarity": max_similarity,
        "summary_counts": {
            "submission_ready": _int(summary.get("submission_ready")),
            "ready_results_count": _int(summary.get("ready_results_count")),
            "official_validation_passed": _int(summary.get("official_validation_passed")),
            "officially_simulated": _int(summary.get("officially_simulated")),
            "submitted_this_run": _int(summary.get("submitted_this_run")),
            "auto_submitted": _int(summary.get("auto_submitted")),
        },
        "best_candidate": _best_candidate(assessed),
        "job_audits": job_audits,
        "chain_summary": _merge_chain_summaries(job_audits),
        "candidate_evidence_findings": [
            dict(finding, jobs=str(jobs_path), job_ledger=jobs_path.name)
            for audit in job_audits
            for finding in audit.get("candidate_evidence_findings", [])
        ],
        "eligible_candidates": eligible,
        "ledger_eligible_candidates": ledger_eligible,
        "latest_candidates": assessed,
        "candidates": ledger_candidates,
    }


def _error_ledger_audit(jobs_path: Path, message: str) -> dict[str, Any]:
    return {
        "jobs": str(jobs_path),
        "job_ledger": jobs_path.name,
        "jobs_checked": 0,
        "latest_job_id": "",
        "latest_job_status": "",
        "candidate_count": 0,
        "eligible_count": 0,
        "ledger_candidate_count": 0,
        "ledger_eligible_count": 0,
        "ledger_ready_to_submit": False,
        "ready_to_submit": False,
        "human_confirmation_required": False,
        "similarity_threshold": DEFAULT_SIMILARITY_THRESHOLD,
        "threshold_summary": _threshold_summary(QualityThresholds()),
        "max_similarity": None,
        "summary_counts": {},
        "best_candidate": {},
        "job_audits": [],
        "chain_summary": {},
        "eligible_candidates": [],
        "ledger_eligible_candidates": [],
        "latest_candidates": [],
        "candidates": [],
        "error": message,
    }


def _audit_candidate_ledger(
    candidates_path: Path,
    *,
    thresholds: QualityThresholds,
    similarity_threshold: float,
) -> dict[str, Any]:
    candidates, error, exists = _read_candidate_ledger(candidates_path)
    if error:
        return {
            "candidate_ledger": str(candidates_path),
            "exists": exists,
            "candidate_count": 0,
            "eligible_count": 0,
            "ready_to_submit": False,
            "candidates": [],
            "eligible_candidates": [],
            "best_candidate": {},
            "blocking_reason_counts": {},
            "findings": [{"code": "candidate_ledger_error", "message": error, "candidate_ledger": str(candidates_path)}],
            "error": error,
        }
    assessed = [
        dict(
            _assess_candidate(item, thresholds=thresholds, similarity_threshold=similarity_threshold),
            candidate_source="candidate_ledger",
            candidate_ledger=str(candidates_path),
        )
        for item in candidates
    ]
    assessed = _dedupe_assessed_candidates(assessed)
    eligible = [item for item in assessed if item["eligible"]]
    return {
        "candidate_ledger": str(candidates_path),
        "exists": exists,
        "candidate_count": len(assessed),
        "eligible_count": len(eligible),
        "ready_to_submit": bool(eligible),
        "candidates": assessed,
        "eligible_candidates": eligible,
        "best_candidate": _best_candidate(assessed),
        "blocking_reason_counts": _blocking_reason_counts(assessed),
        "findings": [],
    }


def _read_candidate_ledger(candidates_path: Path) -> tuple[list[dict[str, Any]], str | None, bool]:
    try:
        raw = candidates_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], None, False

    candidates: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return [], f"candidate ledger is not valid JSONL at line {line_number}: {exc}", True
        if not isinstance(payload, dict):
            return [], f"candidate ledger line {line_number} is not a JSON object", True
        candidates.append(payload)
    return candidates, None, True


def _latest_job_id(jobs: dict[str, Any]) -> str:
    def sort_key(job_id: str) -> tuple[int, str]:
        suffix = job_id.rsplit("_", 1)[-1]
        return (_int(suffix), job_id)

    return sorted((str(job_id) for job_id in jobs), key=sort_key)[-1]


def _audit_jobs(
    jobs: dict[str, Any],
    *,
    thresholds: QualityThresholds,
    similarity_threshold: float,
) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for job_id in sorted((str(job_id) for job_id in jobs), key=lambda item: (_int(item.rsplit("_", 1)[-1]), item)):
        job = jobs.get(job_id) or {}
        if not isinstance(job, dict):
            job = {}
        candidates, evidence_findings = _collect_candidates(job)
        assessed_candidates = [
            _assess_candidate(item, thresholds=thresholds, similarity_threshold=similarity_threshold)
            for item in candidates
        ]
        eligible = [dict(item, job_id=job_id) for item in assessed_candidates if item["eligible"]]
        audits.append(
            {
                "job_id": job_id,
                "status": str(job.get("status") or ""),
                "candidate_count": len(assessed_candidates),
                "eligible_count": len(eligible),
                "candidates": assessed_candidates,
                "eligible_candidates": eligible,
                "chain_summary": _job_chain_summary(job),
                "candidate_evidence_findings": [
                    dict(finding, job_id=job_id)
                    for finding in evidence_findings
                ],
            }
        )
    return audits


def _collect_candidates(job: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    result = job.get("result") or {}
    progress_data = (job.get("progress") or {}).get("data") or {}
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    pool_sources = (
        ("progress.candidates", progress_data, "candidates"),
        ("progress.passed_candidates", progress_data, "passed_candidates"),
        ("result.candidates", result, "candidates"),
        ("summary.passed_candidates", summary, "passed_candidates"),
    )
    candidates: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []
    seen: set[str] = set()
    for source, container, pool_key in pool_sources:
        pool, source_findings = _candidate_pool_from_container(container, pool_key, source=source)
        findings.extend(source_findings)
        for candidate in pool:
            if not isinstance(candidate, dict):
                continue
            candidate_key = _candidate_key(candidate)
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            candidates.append(candidate)
    return candidates, findings


def _job_chain_summary(job: dict[str, Any]) -> dict[str, Any]:
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    return {
        "local_only_jobs": 1 if summary.get("local_only") is True else 0,
        "official_api_called_jobs": 1 if summary.get("official_api_called") is True else 0,
        "official_validation_passed": _int(summary.get("official_validation_passed")),
        "officially_simulated": _int(summary.get("officially_simulated")),
        "submission_ready": _int(summary.get("submission_ready")),
        "submitted_this_run": _int(summary.get("submitted_this_run")),
    }


def _candidate_pool_from_container(
    container: dict[str, Any],
    key: str,
    *,
    source: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    direct = container.get(key)
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, dict)], []

    candidates: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []
    preview = container.get(f"{key}_preview")
    if isinstance(preview, list):
        candidates.extend(item for item in preview if isinstance(item, dict))
    elif isinstance(direct, dict) and isinstance(direct.get("items_preview"), list):
        preview = direct.get("items_preview") or []
        candidates.extend(item for item in preview if isinstance(item, dict))

    evidence = container.get(f"{key}_submission_evidence")
    if isinstance(evidence, list):
        candidates.extend(item for item in evidence if isinstance(item, dict))
    candidates = _dedupe_candidates(candidates)

    raw_count = container.get(f"{key}_count")
    if raw_count is None and isinstance(direct, dict):
        raw_count = direct.get("items_count")
    total_count = _int(raw_count)
    if total_count and len(candidates) < total_count:
        findings.append(
            {
                "code": "candidate_pool_truncated",
                "source": source,
                "message": (
                    f"{source} only contains {len(candidates)} auditable candidate(s) for "
                    f"{total_count} persisted candidate(s); rerun the job after complete "
                    "submission-evidence persistence is available to audit hidden candidates."
                ),
            }
        )
    return candidates, findings
