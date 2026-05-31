"""Audit whether current local evidence is ready for a live BRAIN submit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOBS = ROOT / "data" / "jobs_production.json"
DEFAULT_JOB_LEDGER_GLOB = "jobs_*.json"
SCHEMA_VERSION = "live_submit_readiness.v1"
DEFAULT_SIMILARITY_THRESHOLD = 0.90


def check_live_submit_readiness(
    jobs_path: str | Path = DEFAULT_JOBS,
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    related_jobs_paths: list[str | Path] | None = None,
) -> dict[str, Any]:
    path = Path(jobs_path)
    findings: list[dict[str, str]] = []
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
        ledger_audit = _audit_ledger(ledger_path, ledger_jobs, similarity_threshold=similarity_threshold)
        ledger_audits.append(ledger_audit)
        family_candidates.extend(ledger_audit["candidates"])
        family_eligible_candidates.extend(ledger_audit["ledger_eligible_candidates"])
        family_max_similarity_values.extend(
            item["max_similarity"]
            for item in ledger_audit["candidates"]
            if isinstance(item.get("max_similarity"), (int, float))
        )

    primary_audit = next((item for item in ledger_audits if item["jobs"] == str(path)), {})
    assessed = primary_audit.get("latest_candidates") or []
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

    latest_job_id = primary_audit.get("latest_job_id", "")
    latest_job_status = primary_audit.get("latest_job_status", "")
    max_similarity_values = [
        item["max_similarity"] for item in assessed if isinstance(item.get("max_similarity"), (int, float))
    ]
    max_similarity = max(max_similarity_values) if max_similarity_values else None
    family_max_similarity = max(family_max_similarity_values) if family_max_similarity_values else None
    evidence_ok = not any(finding.get("code") == "jobs_ledger_error" for finding in findings)
    return {
        "ok": evidence_ok,
        "schema_version": SCHEMA_VERSION,
        "jobs": str(path),
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
        "ready_to_submit": bool(eligible),
        "human_confirmation_required": bool(eligible),
        "similarity_threshold": similarity_threshold,
        "max_similarity": max_similarity,
        "job_family_jobs_checked": sum(int(item.get("jobs_checked") or 0) for item in ledger_audits),
        "job_family_candidate_count": sum(int(item.get("ledger_candidate_count") or 0) for item in ledger_audits),
        "job_family_eligible_count": len(family_eligible_candidates),
        "job_family_ready_to_submit": bool(family_eligible_candidates),
        "job_family_max_similarity": family_max_similarity,
        "summary_counts": dict(primary_audit.get("summary_counts") or {}),
        "best_candidate": best,
        "job_family_best_candidate": _best_candidate(family_candidates),
        "job_audits": primary_audit.get("job_audits") or [],
        "job_ledger_audits": ledger_audits,
        "eligible_candidates": eligible,
        "ledger_eligible_candidates": ledger_eligible,
        "job_family_eligible_candidates": family_eligible_candidates,
        "findings": findings,
    }


def _error_result(path: Path, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "schema_version": SCHEMA_VERSION,
        "jobs": str(path),
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
        "similarity_threshold": DEFAULT_SIMILARITY_THRESHOLD,
        "max_similarity": None,
        "job_family_jobs_checked": 0,
        "job_family_candidate_count": 0,
        "job_family_eligible_count": 0,
        "job_family_ready_to_submit": False,
        "job_family_max_similarity": None,
        "summary_counts": {},
        "best_candidate": {},
        "job_family_best_candidate": {},
        "job_audits": [],
        "job_ledger_audits": [],
        "eligible_candidates": [],
        "ledger_eligible_candidates": [],
        "job_family_eligible_candidates": [],
        "findings": [{"code": "jobs_ledger_error", "message": message}],
    }


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


def _audit_ledger(jobs_path: Path, jobs: dict[str, Any], *, similarity_threshold: float) -> dict[str, Any]:
    job_audits = _audit_jobs(jobs, similarity_threshold=similarity_threshold)
    latest_job_id = _latest_job_id(jobs)
    latest_job = jobs.get(latest_job_id) or {}
    latest_audit = next((item for item in job_audits if item["job_id"] == latest_job_id), {})
    assessed = latest_audit.get("candidates") or []
    eligible = [item for item in assessed if item["eligible"]]
    ledger_eligible = [
        dict(candidate, job_id=audit["job_id"], job_ledger=str(jobs_path))
        for audit in job_audits
        for candidate in audit["eligible_candidates"]
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
        "eligible_candidates": eligible,
        "ledger_eligible_candidates": ledger_eligible,
        "latest_candidates": assessed,
        "candidates": [candidate for audit in job_audits for candidate in audit["candidates"]],
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
        "max_similarity": None,
        "summary_counts": {},
        "best_candidate": {},
        "job_audits": [],
        "eligible_candidates": [],
        "ledger_eligible_candidates": [],
        "latest_candidates": [],
        "candidates": [],
        "error": message,
    }


def _latest_job_id(jobs: dict[str, Any]) -> str:
    def sort_key(job_id: str) -> tuple[int, str]:
        suffix = job_id.rsplit("_", 1)[-1]
        return (_int(suffix), job_id)

    return sorted((str(job_id) for job_id in jobs), key=sort_key)[-1]


def _audit_jobs(jobs: dict[str, Any], *, similarity_threshold: float) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for job_id in sorted((str(job_id) for job_id in jobs), key=lambda item: (_int(item.rsplit("_", 1)[-1]), item)):
        job = jobs.get(job_id) or {}
        if not isinstance(job, dict):
            job = {}
        candidates = [
            _assess_candidate(item, similarity_threshold=similarity_threshold)
            for item in _collect_candidates(job)
        ]
        eligible = [dict(item, job_id=job_id) for item in candidates if item["eligible"]]
        audits.append(
            {
                "job_id": job_id,
                "status": str(job.get("status") or ""),
                "candidate_count": len(candidates),
                "eligible_count": len(eligible),
                "candidates": candidates,
                "eligible_candidates": eligible,
            }
        )
    return audits


def _collect_candidates(job: dict[str, Any]) -> list[dict[str, Any]]:
    result = job.get("result") or {}
    progress_data = (job.get("progress") or {}).get("data") or {}
    pools = (
        progress_data.get("candidates") or [],
        progress_data.get("passed_candidates") or [],
        result.get("candidates") or [],
        (result.get("summary") or {}).get("passed_candidates") or [],
        result.get("candidates_preview") or [],
    )
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pool in pools:
        for candidate in pool:
            if not isinstance(candidate, dict):
                continue
            key = _candidate_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    return candidates


def _candidate_key(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("alpha_id")
        or candidate.get("official_alpha_id")
        or candidate.get("simulation_id")
        or candidate.get("expression")
        or id(candidate)
    )


def _assess_candidate(candidate: dict[str, Any], *, similarity_threshold: float) -> dict[str, Any]:
    metrics = candidate.get("official_metrics") if isinstance(candidate.get("official_metrics"), dict) else {}
    if not metrics and isinstance(candidate.get("metrics"), dict):
        metrics = candidate["metrics"]
    risk = candidate.get("cloud_correlation_risk") if isinstance(candidate.get("cloud_correlation_risk"), dict) else {}
    max_similarity = _float_or_none(risk.get("max_similarity"))
    official_id = str(candidate.get("official_alpha_id") or metrics.get("official_alpha_id") or "")
    pass_fail = str(metrics.get("pass_fail") or "").strip().upper()
    submission_ready = bool((candidate.get("gate") or {}).get("submission_ready")) or candidate.get(
        "lifecycle_status"
    ) == "submission_ready"
    reasons: list[str] = []
    if not submission_ready:
        reasons.append("not_submission_ready")
    if not official_id:
        reasons.append("missing_official_alpha_id")
    if not metrics or not pass_fail:
        reasons.append("missing_official_metrics")
    elif pass_fail != "PASS":
        reasons.append("official_pass_fail_not_pass")
    if max_similarity is None:
        reasons.append("missing_cloud_similarity")
    elif max_similarity >= similarity_threshold or str(risk.get("level") or "").lower() == "high":
        reasons.append("high_cloud_similarity")
    eligible = not reasons
    return {
        "alpha_id": str(candidate.get("alpha_id") or ""),
        "official_alpha_id": official_id,
        "lifecycle_status": str(candidate.get("lifecycle_status") or ""),
        "pass_fail": pass_fail,
        "score": _float_or_none((candidate.get("scorecard") or {}).get("total_score") or candidate.get("score")),
        "decision_band": str((candidate.get("scorecard") or {}).get("decision_band") or ""),
        "max_similarity": max_similarity,
        "risk_level": str(risk.get("level") or ""),
        "eligible": eligible,
        "blocking_reasons": reasons,
    }


def _best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        return {}
    return sorted(candidates, key=lambda item: item.get("score") or 0.0, reverse=True)[0]


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether local evidence is ready for live BRAIN submit.")
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS), help="Production jobs ledger path.")
    parser.add_argument("--similarity-threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD)
    parser.add_argument("--require-ready", action="store_true", help="Exit non-zero when no eligible candidate exists.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_live_submit_readiness(args.jobs, similarity_threshold=args.similarity_threshold)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)
    return 0 if result["ok"] and (result["ready_to_submit"] or not args.require_ready) else 1


if __name__ == "__main__":
    raise SystemExit(main())
