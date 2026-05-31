from __future__ import annotations

import json

from scripts.check_live_submit_readiness import check_live_submit_readiness, main


def _jobs_file(tmp_path, candidates, *, summary=None):
    path = tmp_path / "jobs_production.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    "job_0001": {"status": "failed"},
                    "job_0002": {
                        "status": "stopped",
                        "result": {"summary": summary or {}},
                        "progress": {"data": {"candidates": candidates}},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_live_submit_readiness_reports_current_blockers(tmp_path):
    jobs = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_blocked",
                "lifecycle_status": "official_validation_passed",
                "scorecard": {"total_score": 66.9, "decision_band": "research_only"},
                "cloud_correlation_risk": {"level": "high", "max_similarity": 1.0},
                "official_metrics": {},
            }
        ],
        summary={"submission_ready": 0, "official_validation_passed": 1, "submitted_this_run": 0},
    )

    result = check_live_submit_readiness(jobs)

    assert result["ok"] is True
    assert result["latest_job_id"] == "job_0002"
    assert result["ready_to_submit"] is False
    assert result["eligible_count"] == 0
    assert result["candidate_count"] == 1
    assert result["job_ledgers_checked"] == 1
    assert result["jobs_checked"] == 2
    assert result["ledger_candidate_count"] == 1
    assert result["ledger_eligible_count"] == 0
    assert result["ledger_ready_to_submit"] is False
    assert result["job_family_jobs_checked"] == 2
    assert result["job_family_candidate_count"] == 1
    assert result["job_family_eligible_count"] == 0
    assert result["job_family_ready_to_submit"] is False
    assert result["job_audits"][-1]["job_id"] == "job_0002"
    assert result["job_audits"][-1]["eligible_count"] == 0
    assert result["max_similarity"] == 1.0
    assert result["summary_counts"]["submission_ready"] == 0
    assert result["summary_counts"]["official_validation_passed"] == 1
    assert result["best_candidate"]["alpha_id"] == "alpha_blocked"
    assert result["best_candidate"]["blocking_reasons"] == [
        "not_submission_ready",
        "missing_official_alpha_id",
        "missing_official_metrics",
        "high_cloud_similarity",
    ]
    assert result["findings"][0]["code"] == "no_submit_ready_candidate"


def test_live_submit_readiness_accepts_low_risk_official_pass(tmp_path):
    jobs = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_ready",
                "official_alpha_id": "official_ready",
                "lifecycle_status": "submission_ready",
                "gate": {"submission_ready": True},
                "official_metrics": {"pass_fail": "PASS", "official_alpha_id": "official_ready"},
                "scorecard": {"total_score": 91.2, "decision_band": "submit_candidate"},
                "cloud_correlation_risk": {"level": "low", "max_similarity": 0.12},
            }
        ],
        summary={"submission_ready": 1, "official_validation_passed": 1, "submitted_this_run": 0},
    )

    result = check_live_submit_readiness(jobs)

    assert result["ready_to_submit"] is True
    assert result["human_confirmation_required"] is True
    assert result["eligible_count"] == 1
    assert result["ledger_eligible_count"] == 1
    assert result["ledger_ready_to_submit"] is True
    assert result["job_family_eligible_count"] == 1
    assert result["job_family_ready_to_submit"] is True
    assert result["eligible_candidates"][0]["alpha_id"] == "alpha_ready"
    assert result["ledger_eligible_candidates"][0]["job_id"] == "job_0002"
    assert result["eligible_candidates"][0]["blocking_reasons"] == []
    assert result["findings"] == []


def test_live_submit_readiness_audits_all_jobs_for_hidden_eligible_candidates(tmp_path):
    path = tmp_path / "jobs_production.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    "job_0001": {
                        "status": "stopped",
                        "progress": {
                            "data": {
                                "candidates": [
                                    {
                                        "alpha_id": "alpha_ready_old",
                                        "official_alpha_id": "official_ready_old",
                                        "lifecycle_status": "submission_ready",
                                        "gate": {"submission_ready": True},
                                        "official_metrics": {
                                            "pass_fail": "PASS",
                                            "official_alpha_id": "official_ready_old",
                                        },
                                        "cloud_correlation_risk": {"level": "low", "max_similarity": 0.2},
                                    }
                                ]
                            }
                        },
                    },
                    "job_0002": {
                        "status": "stopped",
                        "progress": {
                            "data": {
                                "candidates": [
                                    {
                                        "alpha_id": "alpha_blocked_latest",
                                        "lifecycle_status": "official_validation_passed",
                                        "cloud_correlation_risk": {"level": "high", "max_similarity": 1.0},
                                        "official_metrics": {},
                                    }
                                ]
                            }
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = check_live_submit_readiness(path)

    assert result["latest_job_id"] == "job_0002"
    assert result["ready_to_submit"] is False
    assert result["eligible_count"] == 0
    assert result["ledger_candidate_count"] == 2
    assert result["ledger_eligible_count"] == 1
    assert result["ledger_ready_to_submit"] is True
    assert result["ledger_eligible_candidates"][0]["alpha_id"] == "alpha_ready_old"
    assert result["ledger_eligible_candidates"][0]["job_id"] == "job_0001"


def test_live_submit_readiness_audits_related_job_ledgers(tmp_path):
    production_jobs = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_blocked_latest",
                "lifecycle_status": "official_validation_passed",
                "cloud_correlation_risk": {"level": "high", "max_similarity": 1.0},
                "official_metrics": {},
            }
        ],
    )
    related = tmp_path / "jobs_async.json"
    related.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    "task_0001": {
                        "status": "completed",
                        "result": {
                            "candidates_preview": [
                                {
                                    "alpha_id": "alpha_ready_related",
                                    "official_alpha_id": "official_ready_related",
                                    "lifecycle_status": "submission_ready",
                                    "gate": {"submission_ready": True},
                                    "official_metrics": {
                                        "pass_fail": "PASS",
                                        "official_alpha_id": "official_ready_related",
                                    },
                                    "cloud_correlation_risk": {"level": "low", "max_similarity": 0.1},
                                }
                            ]
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = check_live_submit_readiness(production_jobs)

    assert result["ready_to_submit"] is False
    assert result["eligible_count"] == 0
    assert result["job_ledgers_checked"] == 2
    assert result["job_family_jobs_checked"] == 3
    assert result["job_family_candidate_count"] == 2
    assert result["job_family_eligible_count"] == 1
    assert result["job_family_ready_to_submit"] is True
    assert result["job_ledger_audits"][1]["job_ledger"] == "jobs_async.json"
    assert result["job_family_eligible_candidates"][0]["alpha_id"] == "alpha_ready_related"
    assert result["job_family_eligible_candidates"][0]["job_ledger"].endswith("jobs_async.json")


def test_live_submit_readiness_require_ready_exits_nonzero_without_candidate(tmp_path):
    jobs = _jobs_file(tmp_path, [])

    assert main(["--jobs", str(jobs), "--require-ready", "--json"]) == 1
    assert main(["--jobs", str(jobs), "--json"]) == 0


def test_live_submit_readiness_fails_closed_on_broken_related_ledger(tmp_path):
    jobs = _jobs_file(tmp_path, [])
    (tmp_path / "jobs_async.json").write_text("{broken", encoding="utf-8")

    result = check_live_submit_readiness(jobs)

    assert result["ok"] is False
    assert result["job_ledgers_checked"] == 2
    assert any(finding["code"] == "jobs_ledger_error" for finding in result["findings"])
    assert main(["--jobs", str(jobs), "--json"]) == 1


def test_live_submit_readiness_discovers_repo_job_ledgers():
    result = check_live_submit_readiness()

    assert result["ok"] is True
    assert result["job_ledger_paths"] == [
        str((result["jobs"])),
        str((result["jobs"]).replace("jobs_production.json", "jobs_async.json")),
        str((result["jobs"]).replace("jobs_production.json", "jobs_check.json")),
        str((result["jobs"]).replace("jobs_production.json", "jobs_sync.json")),
    ]
    assert result["job_ledgers_checked"] == 4
    assert result["job_family_jobs_checked"] == 28
    assert result["job_family_candidate_count"] == 17
    assert result["job_family_eligible_count"] == 0
