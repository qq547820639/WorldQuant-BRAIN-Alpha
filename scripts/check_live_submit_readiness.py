from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


"""Audit whether current local evidence is ready for a live BRAIN submit."""



__all__ = [
    "DEFAULT_CANDIDATE_LEDGER",
    "DEFAULT_CONFIG",
    "DEFAULT_JOB_LEDGER_GLOB",
    "DEFAULT_JOBS",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "ROOT",
    "SCHEMA_VERSION",
    "check_live_submit_readiness",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())


"""Candidate dedupe, merge, and counting helpers."""


from typing import Any

from brain_alpha_ops.live_submit_readiness_assessment import float_or_none as _float_or_none



def _candidate_key(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("alpha_id")
        or candidate.get("official_alpha_id")
        or candidate.get("simulation_id")
        or candidate.get("expression")
        or id(candidate)
    )


def _append_unique(items: list[str], value: str) -> list[str]:
    text = str(value).strip()
    if text and text not in items:
        items.append(text)
    return items


def _merged_string_list(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        items = value if isinstance(value, list) else ([value] if value else [])
        for item in items:
            merged = _append_unique(merged, str(item))
    return merged


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _candidate_evidence_rank(candidate: dict[str, Any]) -> tuple[int, int, float]:
    reasons = candidate.get("blocking_reasons") if isinstance(candidate.get("blocking_reasons"), list) else []
    return (
        1 if candidate.get("eligible") is True else 0,
        -len(reasons),
        _float_or_none(candidate.get("score")) or 0.0,
    )


def _merge_assessed_candidate_evidence(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    base = incoming if _candidate_evidence_rank(incoming) > _candidate_evidence_rank(current) else current
    merged = dict(base)
    blocking_reasons = _merged_string_list(current.get("blocking_reasons"), incoming.get("blocking_reasons"))
    if current.get("eligible") is not incoming.get("eligible"):
        blocking_reasons = _append_unique(blocking_reasons, "duplicate_candidate_conflicting_evidence")
    missing_fields = _merged_string_list(
        current.get("missing_official_metric_fields"),
        incoming.get("missing_official_metric_fields"),
    )
    pending_checks = _merged_string_list(current.get("pending_official_checks"), incoming.get("pending_official_checks"))
    scientific_reasons = _merged_string_list(
        current.get("scientific_readiness_reasons"),
        incoming.get("scientific_readiness_reasons"),
    )
    candidate_sources = _merged_string_list(
        current.get("candidate_sources") or current.get("candidate_source"),
        incoming.get("candidate_sources") or incoming.get("candidate_source"),
    )
    merged["blocking_reasons"] = blocking_reasons
    merged["missing_official_metric_fields"] = missing_fields
    merged["pending_official_checks"] = pending_checks
    merged["scientific_readiness_reasons"] = scientific_reasons
    merged["candidate_sources"] = candidate_sources
    merged["eligible"] = bool(current.get("eligible") and incoming.get("eligible") and not blocking_reasons)
    return merged


def _dedupe_assessed_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = _candidate_key(candidate)
        if key not in deduped:
            deduped[key] = candidate
            order.append(key)
            continue
        deduped[key] = _merge_assessed_candidate_evidence(deduped[key], candidate)
    return [deduped[key] for key in order]


def _blocking_reason_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        reasons = candidate.get("blocking_reasons")
        if not isinstance(reasons, list):
            continue
        for reason in reasons:
            key = str(reason)
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _merge_chain_summaries(items: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "local_only_jobs": 0,
        "official_api_called_jobs": 0,
        "official_validation_passed": 0,
        "officially_simulated": 0,
        "submission_ready": 0,
        "submitted_this_run": 0,
    }
    for item in items:
        summary = item.get("chain_summary") if isinstance(item.get("chain_summary"), dict) else item
        if not isinstance(summary, dict):
            continue
        for key in totals:
            totals[key] += _int(summary.get(key))
    return totals


"""Ledger auditing helpers for live submit readiness."""


import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.live_submit_readiness_assessment import (
    assess_candidate as _assess_candidate,
    best_candidate as _best_candidate,
)



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


"""Constants for live submit readiness audits."""


from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
DEFAULT_JOBS = ROOT / "data" / "jobs_production.json"
DEFAULT_JOB_LEDGER_GLOB = "jobs_*.json"
DEFAULT_CANDIDATE_LEDGER = ROOT / "data" / "candidates.jsonl"
SCHEMA_VERSION = "live_submit_readiness.v1"
DEFAULT_SIMILARITY_THRESHOLD = 0.90


"""Production gap analysis helpers."""


from typing import Any

from brain_alpha_ops.live_submit_readiness_assessment import (
    scientific_audit_gap_messages as _scientific_audit_gap_messages,
)



def _candidate_evidence_incomplete(ledger_audits: list[dict[str, Any]]) -> bool:
    for audit in ledger_audits:
        for finding in audit.get("candidate_evidence_findings") or []:
            if (finding or {}).get("code") == "candidate_pool_truncated":
                return True
    return False


def _production_gap_summary(
    *,
    primary_audit: dict[str, Any],
    latest_blocking_reason_counts: dict[str, int],
    family_blocking_reason_counts: dict[str, int],
    primary_chain_summary: dict[str, Any],
    family_chain_summary: dict[str, Any],
    candidate_evidence_incomplete: bool = False,
    current_ready_to_submit: bool | None = None,
) -> dict[str, Any]:
    gaps: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        if not any(item["code"] == code for item in gaps):
            gaps.append({"code": code, "message": message})

    if primary_audit.get("ready_to_submit") and current_ready_to_submit is not False:
        return {
            "gap_count": 0,
            "gaps": [],
            "latest_blocking_reason_counts": latest_blocking_reason_counts,
            "job_family_blocking_reason_counts": family_blocking_reason_counts,
            "primary_chain_summary": dict(primary_chain_summary),
            "job_family_chain_summary": dict(family_chain_summary),
            "ledger_ready_to_submit": bool(primary_audit.get("ledger_ready_to_submit")),
        }

    if primary_chain_summary.get("official_validation_passed") and not primary_chain_summary.get("officially_simulated"):
        add(
            "official_validation_without_simulation",
            "latest production ledger has official validation evidence but no official simulation metrics",
        )
    if family_chain_summary.get("local_only_jobs"):
        add(
            "local_only_candidate_jobs",
            "related job ledgers include local-only candidate generation jobs that cannot prove submit readiness",
        )
    if candidate_evidence_incomplete:
        add(
            "candidate_evidence_incomplete",
            "candidate ledger evidence is incomplete; rerun with full submission evidence before submit",
        )
    if latest_blocking_reason_counts.get("high_turnover_generation_risk"):
        add("latest_candidate_generation_risk", "latest candidate has a known high-turnover generation pattern")
    if latest_blocking_reason_counts.get("local_backtest_failed"):
        add("latest_candidate_local_backtest_failed", "latest candidate failed local backtest constraints")
    if latest_blocking_reason_counts.get("lifecycle_history_blocked"):
        add("latest_candidate_lifecycle_history_blocked", "latest candidate has local lifecycle history that requires archive before submit")
    if latest_blocking_reason_counts.get("lifecycle_history_failed"):
        add("latest_candidate_lifecycle_history_failed", "latest candidate has local lifecycle history that requires rework before submit")
    if latest_blocking_reason_counts.get("production_decision_lifecycle_blocked"):
        add("latest_candidate_lifecycle_decision_blocked", "latest candidate production decision contains lifecycle-history blocking evidence")
    if latest_blocking_reason_counts.get("production_decision_blocked"):
        add("latest_candidate_production_decision_blocked", "latest candidate production decision is blocked")
    for reason, message in _scientific_audit_gap_messages().items():
        if latest_blocking_reason_counts.get(reason):
            add(f"latest_candidate_{reason}", f"latest candidate {message}")
    if latest_blocking_reason_counts.get("high_cloud_similarity"):
        add("latest_candidate_high_cloud_similarity", "latest candidate is too similar to an existing cloud alpha")
    if family_blocking_reason_counts.get("missing_official_alpha_id"):
        add("candidate_family_missing_official_alpha_id", "candidate family lacks official alpha identifiers")
    if family_blocking_reason_counts.get("missing_official_metrics"):
        add("candidate_family_missing_official_metrics", "candidate family lacks official simulation metrics")
    if family_blocking_reason_counts.get("lifecycle_history_blocked"):
        add("candidate_family_lifecycle_history_blocked", "candidate family contains local lifecycle history that requires archive before submit")
    if family_blocking_reason_counts.get("lifecycle_history_failed"):
        add("candidate_family_lifecycle_history_failed", "candidate family contains local lifecycle history that requires rework before submit")
    for reason, message in _scientific_audit_gap_messages().items():
        if family_blocking_reason_counts.get(reason):
            add(f"candidate_family_{reason}", f"candidate family {message}")
    if family_blocking_reason_counts.get("missing_cloud_similarity"):
        add("candidate_family_missing_cloud_similarity", "candidate family has candidates without cloud similarity evidence")
    if family_blocking_reason_counts.get("decision_band_not_submit_candidate"):
        add("candidate_family_not_submit_band", "candidate family has no candidate in submit_candidate decision band")

    return {
        "gap_count": len(gaps),
        "gaps": gaps,
        "latest_blocking_reason_counts": latest_blocking_reason_counts,
        "job_family_blocking_reason_counts": family_blocking_reason_counts,
        "primary_chain_summary": dict(primary_chain_summary),
        "job_family_chain_summary": dict(family_chain_summary),
        "ledger_ready_to_submit": bool(primary_audit.get("ledger_ready_to_submit")),
    }


def _production_gap_findings(
    primary_audit: dict[str, Any],
    ledger_audits: list[dict[str, Any]],
    family_candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    primary_chain_summary = dict(primary_audit.get("chain_summary") or {})
    family_chain_summary = _merge_chain_summaries(ledger_audits)
    latest_counts = _blocking_reason_counts(primary_audit.get("latest_candidates") or [])
    family_counts = _blocking_reason_counts(family_candidates)
    return [
        {
            "code": gap["code"],
            "message": gap["message"],
        }
        for gap in _production_gap_summary(
            primary_audit=primary_audit,
            latest_blocking_reason_counts=latest_counts,
            family_blocking_reason_counts=family_counts,
            primary_chain_summary=primary_chain_summary,
            family_chain_summary=family_chain_summary,
            candidate_evidence_incomplete=_candidate_evidence_incomplete([primary_audit]),
        )["gaps"]
    ]


"""Human-readable reporting for live submit readiness."""


from typing import Any


def _print_human(result: dict[str, Any]) -> None:
    status = "ready" if result.get("ready_to_submit") else "not ready"
    print(f"live submit readiness {status}: {result['jobs']}")
    print(
        "latest_job={latest_job_id}, jobs_checked={jobs_checked}, candidates={candidate_count}, "
        "eligible={eligible_count}, ledger_eligible={ledger_eligible_count}, "
        "max_similarity={max_similarity}".format(**result)
    )
    print(
        "job_ledgers={job_ledgers_checked}, family_jobs={job_family_jobs_checked}, "
        "family_candidates={job_family_candidate_count}, family_eligible={job_family_eligible_count}".format(**result)
    )
    print(
        "candidate_ledger={candidate_ledger}, candidate_ledger_candidates={candidate_ledger_candidate_count}, "
        "candidate_ledger_eligible={candidate_ledger_eligible_count}".format(**result)
    )
    if result.get("best_candidate"):
        best = result["best_candidate"]
        print(
            "best_candidate={alpha_id}, status={lifecycle_status}, score={score}, reasons={reasons}".format(
                alpha_id=best.get("alpha_id", ""),
                lifecycle_status=best.get("lifecycle_status", ""),
                score=best.get("score"),
                reasons=",".join(best.get("blocking_reasons") or []) or "none",
            )
        )
    for finding in result.get("findings") or []:
        print(f"[{finding['code']}] {finding['message']}")


"""Live submit readiness orchestrator and CLI entry point."""


import argparse
import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.live_submit_readiness_assessment import (
    best_candidate as _best_candidate,
)



def check_live_submit_readiness(
    jobs_path: str | Path = DEFAULT_JOBS,
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    related_jobs_paths: list[str | Path] | None = None,
    candidate_ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(jobs_path)
    candidate_path = Path(candidate_ledger_path) if candidate_ledger_path is not None else path.parent / "candidates.jsonl"
    findings: list[dict[str, str]] = []
    thresholds, threshold_finding = _load_thresholds(config_path)
    if threshold_finding:
        findings.append(threshold_finding)
    jobs, error = _read_jobs_ledger(path)
    if error:
        return _error_result(path, error)

    ledger_paths = _job_ledger_paths(path, related_jobs_paths)
    ledger_audits: list[dict[str, Any]] = []
    family_candidates: list[dict[str, Any]] = []
    family_eligible_candidates: list[dict[str, Any]] = []
    family_max_similarity_values: list[float] = []
    for ledger_path in ledger_paths:
        ledger_jobs, ledger_error = _read_jobs_ledger(ledger_path)
        if ledger_error:
            findings.append({"code": "jobs_ledger_error", "message": ledger_error, "jobs": str(ledger_path)})
            ledger_audits.append(_error_ledger_audit(ledger_path, ledger_error))
            continue
        ledger_audit = _audit_ledger(
            ledger_path,
            ledger_jobs,
            thresholds=thresholds,
            similarity_threshold=similarity_threshold,
        )
        ledger_audits.append(ledger_audit)
        findings.extend(ledger_audit.get("candidate_evidence_findings") or [])
        family_candidates.extend(ledger_audit["candidates"])
        family_eligible_candidates.extend(ledger_audit["ledger_eligible_candidates"])
        family_max_similarity_values.extend(
            item["max_similarity"]
            for item in ledger_audit["candidates"]
            if isinstance(item.get("max_similarity"), (int, float))
        )

    candidate_ledger_audit = _audit_candidate_ledger(
        candidate_path,
        thresholds=thresholds,
        similarity_threshold=similarity_threshold,
    )
    findings.extend(candidate_ledger_audit.get("findings") or [])
    family_candidates = _dedupe_assessed_candidates(
        family_candidates + (candidate_ledger_audit.get("candidates") or [])
    )
    family_eligible_candidates = [item for item in family_candidates if item["eligible"]]
    family_max_similarity_values = [
        item["max_similarity"] for item in family_candidates if isinstance(item.get("max_similarity"), (int, float))
    ]

    primary_audit = next((item for item in ledger_audits if item["jobs"] == str(path)), {})
    primary_latest_candidates = primary_audit.get("latest_candidates") or []
    primary_latest_keys = {
        _candidate_key(item)
        for item in primary_latest_candidates
        if isinstance(item, dict)
    }
    candidate_ledger_current_evidence = [
        item
        for item in (candidate_ledger_audit.get("candidates") or [])
        if _candidate_key(item) in primary_latest_keys
    ]
    assessed = _dedupe_assessed_candidates(primary_latest_candidates + candidate_ledger_current_evidence)
    eligible = [item for item in assessed if item["eligible"]]
    ledger_eligible = primary_audit.get("ledger_eligible_candidates") or []
    best = _best_candidate(assessed)
    if not eligible:
        findings.append(
            {
                "code": "no_submit_ready_candidate",
                "message": "no current candidate has complete official metrics, low similarity risk, and submission-ready status",
            }
        )
        findings.extend(_production_gap_findings(primary_audit, ledger_audits, family_candidates))

    latest_job_id = primary_audit.get("latest_job_id", "")
    latest_job_status = primary_audit.get("latest_job_status", "")
    max_similarity_values = [
        item["max_similarity"] for item in assessed if isinstance(item.get("max_similarity"), (int, float))
    ]
    max_similarity = max(max_similarity_values) if max_similarity_values else None
    family_max_similarity = max(family_max_similarity_values) if family_max_similarity_values else None
    latest_blocking_reason_counts = _blocking_reason_counts(assessed)
    ledger_blocking_reason_counts = _blocking_reason_counts(primary_audit.get("candidates") or [])
    candidate_ledger_blocking_reason_counts = dict(candidate_ledger_audit.get("blocking_reason_counts") or {})
    family_blocking_reason_counts = _blocking_reason_counts(family_candidates)
    primary_chain_summary = dict(primary_audit.get("chain_summary") or {})
    family_chain_summary = _merge_chain_summaries(ledger_audits)
    primary_candidate_evidence_incomplete = _candidate_evidence_incomplete([primary_audit])
    evidence_ok = not any(
        finding.get("code") in {"jobs_ledger_error", "readiness_config_error", "candidate_ledger_error"}
        for finding in findings
    )
    ready_to_submit = bool(eligible) and evidence_ok
    return {
        "ok": evidence_ok,
        "schema_version": SCHEMA_VERSION,
        "jobs": str(path),
        "candidate_ledger": str(candidate_path),
        "job_ledger_paths": [str(ledger_path) for ledger_path in ledger_paths],
        "job_ledgers_checked": len(ledger_audits),
        "jobs_checked": int(primary_audit.get("jobs_checked") or 0),
        "latest_job_id": latest_job_id,
        "latest_job_status": latest_job_status,
        "candidate_count": len(assessed),
        "eligible_count": len(eligible),
        "ledger_candidate_count": int(primary_audit.get("ledger_candidate_count") or 0),
        "ledger_eligible_count": len(ledger_eligible),
        "ledger_ready_to_submit": bool(ledger_eligible),
        "ready_to_submit": ready_to_submit,
        "human_confirmation_required": ready_to_submit,
        "candidate_ledger_candidate_count": int(candidate_ledger_audit.get("candidate_count") or 0),
        "candidate_ledger_eligible_count": int(candidate_ledger_audit.get("eligible_count") or 0),
        "candidate_ledger_ready_to_submit": bool(candidate_ledger_audit.get("ready_to_submit")),
        "similarity_threshold": similarity_threshold,
        "threshold_summary": _threshold_summary(thresholds),
        "max_similarity": max_similarity,
        "job_family_jobs_checked": sum(int(item.get("jobs_checked") or 0) for item in ledger_audits),
        "job_family_candidate_count": len(family_candidates),
        "job_family_eligible_count": len(family_eligible_candidates),
        "job_family_ready_to_submit": bool(family_eligible_candidates),
        "job_family_max_similarity": family_max_similarity,
        "summary_counts": dict(primary_audit.get("summary_counts") or {}),
        "latest_blocking_reason_counts": latest_blocking_reason_counts,
        "ledger_blocking_reason_counts": ledger_blocking_reason_counts,
        "candidate_ledger_blocking_reason_counts": candidate_ledger_blocking_reason_counts,
        "job_family_blocking_reason_counts": family_blocking_reason_counts,
        "primary_chain_summary": primary_chain_summary,
        "job_family_chain_summary": family_chain_summary,
        "production_gap_summary": _production_gap_summary(
            primary_audit=primary_audit,
            latest_blocking_reason_counts=latest_blocking_reason_counts,
            family_blocking_reason_counts=family_blocking_reason_counts,
            primary_chain_summary=primary_chain_summary,
            family_chain_summary=family_chain_summary,
            candidate_evidence_incomplete=primary_candidate_evidence_incomplete,
            current_ready_to_submit=ready_to_submit,
        ),
        "best_candidate": best,
        "job_family_best_candidate": _best_candidate(family_candidates),
        "job_audits": primary_audit.get("job_audits") or [],
        "job_ledger_audits": ledger_audits,
        "candidate_ledger_audit": candidate_ledger_audit,
        "eligible_candidates": eligible,
        "ledger_eligible_candidates": ledger_eligible,
        "candidate_ledger_eligible_candidates": candidate_ledger_audit.get("eligible_candidates") or [],
        "job_family_eligible_candidates": family_eligible_candidates,
        "findings": findings,
    }


def _error_result(path: Path, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "schema_version": SCHEMA_VERSION,
        "jobs": str(path),
        "candidate_ledger": str(path.parent / "candidates.jsonl"),
        "job_ledger_paths": [str(path)],
        "job_ledgers_checked": 0,
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
        "candidate_ledger_candidate_count": 0,
        "candidate_ledger_eligible_count": 0,
        "candidate_ledger_ready_to_submit": False,
        "similarity_threshold": DEFAULT_SIMILARITY_THRESHOLD,
        "threshold_summary": _threshold_summary(QualityThresholds()),
        "max_similarity": None,
        "job_family_jobs_checked": 0,
        "job_family_candidate_count": 0,
        "job_family_eligible_count": 0,
        "job_family_ready_to_submit": False,
        "job_family_max_similarity": None,
        "summary_counts": {},
        "latest_blocking_reason_counts": {},
        "ledger_blocking_reason_counts": {},
        "candidate_ledger_blocking_reason_counts": {},
        "job_family_blocking_reason_counts": {},
        "primary_chain_summary": {},
        "job_family_chain_summary": {},
        "production_gap_summary": {"gap_count": 0, "gaps": []},
        "best_candidate": {},
        "job_family_best_candidate": {},
        "job_audits": [],
        "job_ledger_audits": [],
        "candidate_ledger_audit": {},
        "eligible_candidates": [],
        "ledger_eligible_candidates": [],
        "candidate_ledger_eligible_candidates": [],
        "job_family_eligible_candidates": [],
        "findings": [{"code": "jobs_ledger_error", "message": message}],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether local evidence is ready for live BRAIN submit.")
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS), help="Production jobs ledger path.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path for official submit thresholds.")
    parser.add_argument("--candidate-ledger", default=None, help="Candidate JSONL ledger path.")
    parser.add_argument("--similarity-threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD)
    parser.add_argument("--require-ready", action="store_true", help="Exit non-zero when no eligible candidate exists.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_live_submit_readiness(
        args.jobs,
        config_path=args.config,
        similarity_threshold=args.similarity_threshold,
        candidate_ledger_path=args.candidate_ledger,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)
    return 0 if result["ok"] and (result["ready_to_submit"] or not args.require_ready) else 1


"""Threshold loading and summary helpers."""


from pathlib import Path
from typing import Any

from brain_alpha_ops.config import ConfigValidationError, QualityThresholds, load_run_config


def _load_thresholds(config_path: str | Path) -> tuple[QualityThresholds, dict[str, str] | None]:
    try:
        return load_run_config(config_path).ops.thresholds, None
    except ConfigValidationError as exc:
        return QualityThresholds(), {
            "code": "readiness_config_error",
            "message": f"could not load official threshold config: {exc}",
        }


def _threshold_summary(thresholds: QualityThresholds) -> dict[str, Any]:
    return {
        "min_sharpe": thresholds.min_sharpe,
        "min_fitness": thresholds.min_fitness,
        "platform_max_turnover": thresholds.platform_max_turnover,
        "max_self_correlation": thresholds.max_self_correlation,
        "max_prod_correlation": thresholds.max_prod_correlation,
        "max_weight_concentration": thresholds.max_weight_concentration,
        "require_official_pass": thresholds.require_official_pass,
        "require_official_metrics": thresholds.require_official_metrics,
    }


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())