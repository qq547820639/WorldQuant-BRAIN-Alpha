"""Human-readable reporting for live submit readiness."""

from __future__ import annotations

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
