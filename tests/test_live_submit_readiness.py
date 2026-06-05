from __future__ import annotations

import json

from scripts.check_live_submit_readiness import check_live_submit_readiness, main


def _official_metrics(**overrides):
    metrics = {
        "official_alpha_id": "official_ready",
        "pass_fail": "PASS",
        "sharpe": 1.6,
        "fitness": 1.2,
        "turnover": 0.25,
        "correlation": 0.2,
        "self_correlation": 0.2,
        "prod_correlation": 0.2,
        "weight_concentration": 0.05,
    }
    metrics.update(overrides)
    return metrics


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
    assert result["latest_blocking_reason_counts"] == {
        "decision_band_not_submit_candidate": 1,
        "high_cloud_similarity": 1,
        "missing_official_alpha_id": 1,
        "missing_official_metrics": 1,
        "not_submission_ready": 1,
    }
    assert result["primary_chain_summary"]["official_validation_passed"] == 1
    assert result["primary_chain_summary"]["officially_simulated"] == 0
    gap_codes = {gap["code"] for gap in result["production_gap_summary"]["gaps"]}
    assert "official_validation_without_simulation" in gap_codes
    assert "latest_candidate_high_cloud_similarity" in gap_codes
    assert "candidate_family_missing_official_metrics" in gap_codes
    assert result["best_candidate"]["alpha_id"] == "alpha_blocked"
    assert result["best_candidate"]["blocking_reasons"] == [
        "not_submission_ready",
        "decision_band_not_submit_candidate",
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
                "official_metrics": _official_metrics(),
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
    assert result["latest_blocking_reason_counts"] == {}
    assert result["production_gap_summary"]["gaps"] == []
    assert result["findings"] == []
    assert result["threshold_summary"]["min_sharpe"] == 1.25
    assert result["eligible_candidates"][0]["official_release_gate"]["status"] == "PASS"


def test_live_submit_readiness_requires_official_metrics_above_config_thresholds(tmp_path):
    jobs = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_low_sharpe",
                "official_alpha_id": "official_low_sharpe",
                "lifecycle_status": "submission_ready",
                "gate": {"submission_ready": True},
                "official_metrics": _official_metrics(
                    official_alpha_id="official_low_sharpe",
                    sharpe=0.8,
                ),
                "scorecard": {"total_score": 91.2, "decision_band": "submit_candidate"},
                "cloud_correlation_risk": {"level": "low", "max_similarity": 0.12},
            }
        ],
    )

    result = check_live_submit_readiness(jobs)

    assert result["ready_to_submit"] is False
    assert result["eligible_count"] == 0
    assert result["best_candidate"]["official_release_gate"]["status"] == "FAIL"
    assert result["best_candidate"]["blocking_reasons"] == ["official_sharpe_below_threshold"]


def test_live_submit_readiness_requires_complete_official_release_metrics(tmp_path):
    jobs = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_sparse_metrics",
                "official_alpha_id": "official_sparse_metrics",
                "lifecycle_status": "submission_ready",
                "gate": {"submission_ready": True},
                "official_metrics": {"official_alpha_id": "official_sparse_metrics", "pass_fail": "PASS"},
                "scorecard": {"total_score": 91.2, "decision_band": "submit_candidate"},
                "cloud_correlation_risk": {"level": "low", "max_similarity": 0.12},
            }
        ],
    )

    result = check_live_submit_readiness(jobs)

    assert result["ready_to_submit"] is False
    assert result["eligible_count"] == 0
    assert "missing_official_metric_fields" in result["best_candidate"]["blocking_reasons"]
    assert "official_sharpe_below_threshold" in result["best_candidate"]["blocking_reasons"]
    assert "sharpe" in result["best_candidate"]["missing_official_metric_fields"]


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
                                        "scorecard": {"total_score": 91.0, "decision_band": "submit_candidate"},
                                        "official_metrics": _official_metrics(official_alpha_id="official_ready_old"),
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
                                    "scorecard": {"total_score": 91.0, "decision_band": "submit_candidate"},
                                    "official_metrics": _official_metrics(official_alpha_id="official_ready_related"),
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


def test_live_submit_readiness_reports_production_gap_summary(tmp_path):
    production_jobs = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_latest_blocked",
                "lifecycle_status": "official_validation_passed",
                "scorecard": {"total_score": 66.9, "decision_band": "research_only"},
                "submission": {"local_backtest": {"pass_local": False}},
                "cloud_correlation_risk": {"level": "high", "max_similarity": 1.0},
                "official_metrics": {},
            }
        ],
        summary={"official_validation_passed": 1, "officially_simulated": 0, "submission_ready": 0},
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
                            "summary": {
                                "generated_count": 1,
                                "local_only": True,
                                "official_api_called": False,
                            },
                            "candidates": [
                                {
                                    "alpha_id": "alpha_local_only",
                                    "lifecycle_status": "generated",
                                    "scorecard": {
                                        "total_score": 73.0,
                                        "decision_band": "optimize_before_submit",
                                    },
                                    "official_metrics": {},
                                }
                            ],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = check_live_submit_readiness(production_jobs)

    assert result["ready_to_submit"] is False
    assert result["job_family_blocking_reason_counts"]["missing_official_metrics"] == 2
    assert result["job_family_blocking_reason_counts"]["missing_official_alpha_id"] == 2
    assert result["job_family_chain_summary"]["local_only_jobs"] == 1
    gap_codes = {gap["code"] for gap in result["production_gap_summary"]["gaps"]}
    assert "official_validation_without_simulation" in gap_codes
    assert "local_only_candidate_jobs" in gap_codes
    assert "latest_candidate_local_backtest_failed" in gap_codes
    assert "latest_candidate_high_cloud_similarity" in gap_codes
    assert "candidate_family_missing_official_metrics" in gap_codes
    assert any(finding["code"] == "local_only_candidate_jobs" for finding in result["findings"])


def test_live_submit_readiness_uses_submission_evidence_outside_compacted_preview(tmp_path):
    blocked_preview = [
        {
            "alpha_id": f"alpha_preview_{index}",
            "lifecycle_status": "generated",
            "scorecard": {"total_score": 55.0, "decision_band": "research_only"},
        }
        for index in range(5)
    ]
    jobs = tmp_path / "jobs_production.json"
    jobs.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    "job_0001": {
                        "status": "completed",
                        "result": {
                            "candidates_count": 6,
                            "candidates_preview": blocked_preview,
                            "candidates_submission_evidence": [
                                {
                                    "alpha_id": "alpha_ready_hidden",
                                    "official_alpha_id": "official_ready_hidden",
                                    "lifecycle_status": "submission_ready",
                                    "gate": {"submission_ready": True},
                                    "scorecard": {"total_score": 91.0, "decision_band": "submit_candidate"},
                                    "official_metrics": _official_metrics(official_alpha_id="official_ready_hidden"),
                                    "cloud_correlation_risk": {"level": "low", "max_similarity": 0.1},
                                }
                            ],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = check_live_submit_readiness(jobs)

    assert result["ready_to_submit"] is True
    assert result["eligible_count"] == 1
    assert result["ledger_candidate_count"] == 6
    assert result["eligible_candidates"][0]["alpha_id"] == "alpha_ready_hidden"
    assert not any(finding["code"] == "candidate_pool_truncated" for finding in result["findings"])


def test_live_submit_readiness_reports_truncated_candidate_preview_without_submission_evidence(tmp_path):
    jobs = tmp_path / "jobs_production.json"
    jobs.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    "job_0001": {
                        "status": "completed",
                        "result": {
                            "candidates_count": 6,
                            "candidates_preview": [
                                {
                                    "alpha_id": f"alpha_preview_{index}",
                                    "lifecycle_status": "generated",
                                }
                                for index in range(5)
                            ],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = check_live_submit_readiness(jobs)

    assert result["ready_to_submit"] is False
    assert result["candidate_count"] == 5
    assert any(
        finding["code"] == "candidate_pool_truncated"
        and finding["source"] == "result.candidates"
        and finding["job_id"] == "job_0001"
        for finding in result["findings"]
    )
    gap_codes = {gap["code"] for gap in result["production_gap_summary"]["gaps"]}
    assert "candidate_evidence_incomplete" in gap_codes


def test_live_submit_readiness_keeps_related_ledger_truncation_out_of_primary_gap(tmp_path):
    primary = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_current",
                "lifecycle_status": "generated",
                "scorecard": {"total_score": 71.0, "decision_band": "optimize_before_submit"},
                "cloud_correlation_risk": {"level": "low", "max_similarity": 0.2},
                "official_metrics": {},
            }
        ],
        summary={"submission_ready": 0, "official_validation_passed": 0, "officially_simulated": 0},
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
                            "candidates_count": 6,
                            "candidates_preview": [
                                {
                                    "alpha_id": f"alpha_async_preview_{index}",
                                    "lifecycle_status": "generated",
                                }
                                for index in range(5)
                            ],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = check_live_submit_readiness(primary, related_jobs_paths=[related])

    assert any(finding["code"] == "candidate_pool_truncated" for finding in result["findings"])
    gap_codes = {gap["code"] for gap in result["production_gap_summary"]["gaps"]}
    assert "candidate_evidence_incomplete" not in gap_codes


def test_live_submit_readiness_reports_truncated_candidate_preview_with_incomplete_evidence(tmp_path):
    jobs = tmp_path / "jobs_production.json"
    jobs.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    "job_0001": {
                        "status": "completed",
                        "result": {
                            "candidates_count": 7,
                            "candidates_preview": [
                                {
                                    "alpha_id": f"alpha_preview_{index}",
                                    "lifecycle_status": "generated",
                                }
                                for index in range(5)
                            ],
                            "candidates_submission_evidence": [
                                {
                                    "alpha_id": "alpha_hidden_1",
                                    "lifecycle_status": "generated",
                                    "scorecard": {"decision_band": "research_only"},
                                }
                            ],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = check_live_submit_readiness(jobs)

    assert result["ready_to_submit"] is False
    assert result["candidate_count"] == 6
    assert any(
        finding["code"] == "candidate_pool_truncated"
        and finding["source"] == "result.candidates"
        and finding["job_id"] == "job_0001"
        for finding in result["findings"]
    )
    gap_codes = {gap["code"] for gap in result["production_gap_summary"]["gaps"]}
    assert "candidate_evidence_incomplete" in gap_codes


def test_live_submit_readiness_requires_submit_candidate_decision_band(tmp_path):
    jobs = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_optimize",
                "official_alpha_id": "official_optimize",
                "lifecycle_status": "submission_ready",
                "gate": {"submission_ready": True},
                "official_metrics": _official_metrics(official_alpha_id="official_optimize"),
                "scorecard": {"total_score": 78.0, "decision_band": "optimize_before_submit"},
                "cloud_correlation_risk": {"level": "low", "max_similarity": 0.12},
            }
        ],
        summary={"submission_ready": 1, "official_validation_passed": 1, "submitted_this_run": 0},
    )

    result = check_live_submit_readiness(jobs)

    assert result["ready_to_submit"] is False
    assert result["eligible_count"] == 0
    assert result["best_candidate"]["blocking_reasons"] == ["decision_band_not_submit_candidate"]


def test_live_submit_readiness_blocks_stub_official_alpha_id(tmp_path):
    jobs = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_stub_ready",
                "official_alpha_id": "prod_stub_alpha_0001",
                "lifecycle_status": "submission_ready",
                "gate": {"submission_ready": True},
                "official_metrics": _official_metrics(official_alpha_id="prod_stub_alpha_0001"),
                "scorecard": {"total_score": 91.2, "decision_band": "submit_candidate"},
                "cloud_correlation_risk": {"level": "low", "max_similarity": 0.12},
            }
        ],
        summary={"submission_ready": 1, "official_validation_passed": 1, "submitted_this_run": 0},
    )

    result = check_live_submit_readiness(jobs)

    assert result["ready_to_submit"] is False
    assert result["eligible_count"] == 0
    assert result["best_candidate"]["blocking_reasons"] == ["non_production_official_alpha_id"]


def test_live_submit_readiness_blocks_failed_local_backtest(tmp_path):
    jobs = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_local_failed",
                "official_alpha_id": "official_local_failed",
                "lifecycle_status": "submission_ready",
                "gate": {"submission_ready": True},
                "official_metrics": _official_metrics(official_alpha_id="official_local_failed"),
                "scorecard": {"total_score": 91.2, "decision_band": "submit_candidate"},
                "cloud_correlation_risk": {"level": "low", "max_similarity": 0.12},
                "submission": {"local_backtest": {"pass_local": False}},
            }
        ],
        summary={"submission_ready": 1, "official_validation_passed": 1, "submitted_this_run": 0},
    )

    result = check_live_submit_readiness(jobs)

    assert result["ready_to_submit"] is False
    assert result["eligible_count"] == 0
    assert result["best_candidate"]["local_backtest_passed"] is False
    assert result["best_candidate"]["blocking_reasons"] == ["local_backtest_failed"]


def test_live_submit_readiness_blocks_high_turnover_generation_risk(tmp_path):
    jobs = _jobs_file(
        tmp_path,
        [
            {
                "alpha_id": "alpha_generation_risk",
                "official_alpha_id": "official_generation_risk",
                "expression": "rank(ts_delta(returns, 10))",
                "lifecycle_status": "submission_ready",
                "gate": {"submission_ready": True},
                "official_metrics": _official_metrics(official_alpha_id="official_generation_risk"),
                "scorecard": {"total_score": 91.2, "decision_band": "submit_candidate"},
                "cloud_correlation_risk": {"level": "low", "max_similarity": 0.12},
                "submission": {"local_backtest": {"pass_local": True}},
            }
        ],
        summary={"submission_ready": 1, "official_validation_passed": 1, "officially_simulated": 1},
    )

    result = check_live_submit_readiness(jobs)

    assert result["ready_to_submit"] is False
    assert result["eligible_count"] == 0
    assert result["best_candidate"]["generation_risk_reasons"] == ["direct_returns_delta_window=10"]
    assert result["best_candidate"]["blocking_reasons"] == ["high_turnover_generation_risk"]
    gap_codes = {gap["code"] for gap in result["production_gap_summary"]["gaps"]}
    assert "latest_candidate_generation_risk" in gap_codes


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


def test_live_submit_readiness_fails_closed_when_primary_ledger_missing(tmp_path):
    jobs = tmp_path / "jobs_production.json"

    result = check_live_submit_readiness(jobs, related_jobs_paths=[])

    assert result["ok"] is False
    assert result["ready_to_submit"] is False
    assert result["job_ledgers_checked"] == 0
    assert result["findings"] == [
        {"code": "jobs_ledger_error", "message": f"jobs ledger not found: {jobs}"}
    ]


def test_live_submit_readiness_fails_closed_when_primary_ledger_invalid_json(tmp_path):
    jobs = tmp_path / "jobs_production.json"
    jobs.write_text("{broken", encoding="utf-8")

    result = check_live_submit_readiness(jobs, related_jobs_paths=[])

    assert result["ok"] is False
    assert result["ready_to_submit"] is False
    assert result["job_ledgers_checked"] == 0
    assert result["findings"][0]["code"] == "jobs_ledger_error"
    assert "not valid JSON" in result["findings"][0]["message"]


def test_live_submit_readiness_fails_closed_when_primary_ledger_has_no_jobs(tmp_path):
    jobs = tmp_path / "jobs_production.json"
    jobs.write_text(json.dumps({"version": 1, "jobs": {}}), encoding="utf-8")

    result = check_live_submit_readiness(jobs, related_jobs_paths=[])

    assert result["ok"] is False
    assert result["ready_to_submit"] is False
    assert result["job_ledgers_checked"] == 0
    assert result["findings"] == [
        {"code": "jobs_ledger_error", "message": f"jobs ledger does not contain any jobs: {jobs}"}
    ]


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
    assert result["job_family_jobs_checked"] >= result["jobs_checked"]
    assert result["job_family_candidate_count"] >= result["candidate_count"]
    assert result["job_family_eligible_count"] == 0
    assert not any(finding["code"] == "jobs_ledger_error" for finding in result["findings"])
