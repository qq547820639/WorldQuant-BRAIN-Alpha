"""Live submit readiness orchestrator and CLI entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.live_submit_readiness_assessment import (
    best_candidate as _best_candidate,
)

from ._candidates import (
    _blocking_reason_counts,
    _candidate_key,
    _dedupe_assessed_candidates,
    _merge_chain_summaries,
)
from ._checks import (
    _audit_candidate_ledger,
    _audit_ledger,
    _error_ledger_audit,
    _job_ledger_paths,
    _read_jobs_ledger,
)
from ._constants import (
    DEFAULT_CANDIDATE_LEDGER,
    DEFAULT_CONFIG,
    DEFAULT_JOBS,
    DEFAULT_SIMILARITY_THRESHOLD,
    SCHEMA_VERSION,
)
from ._gaps import (
    _candidate_evidence_incomplete,
    _production_gap_findings,
    _production_gap_summary,
)
from ._reporters import _print_human
from ._thresholds import _load_thresholds, _threshold_summary


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
