from brain_alpha_ops.web_candidates.decisions import candidate_production_decision
from brain_alpha_ops.web_candidates.payloads import candidate_main_pool, candidate_payload, candidate_summary
from brain_alpha_ops.web_candidates.workflow import candidate_workflow_plan


def _candidate(alpha_id: str, expression: str, score: float, *, blocked: bool = False) -> dict:
    row = {
        "alpha_id": alpha_id,
        "expression": expression,
        "family": "demo",
        "hypothesis": "candidate payload test",
        "lifecycle_status": "candidate_pool_retained",
        "scorecard": {
            "total_score": score,
            "decision_band": "optimize_before_submit",
        },
        "quality_diagnosis": {
            "local_candidate_valid": True,
            "blocking_reasons": ["decision_band_not_submit_candidate"],
            "reasons": [
                {
                    "code": "decision_band_not_submit_candidate",
                    "category": "quality_gate_failed",
                    "severity": "blocking",
                }
            ],
        },
        "local_quality": {"passed": True},
    }
    if blocked:
        row["lifecycle_status"] = "local_prefilter_rejected"
        row["local_quality"] = {"passed": False, "reasons": ["local_quality_failed"]}
        row["quality_diagnosis"] = {
            "local_candidate_valid": False,
            "blocking_reasons": ["local_quality_failed"],
        }
    return row


def test_candidate_main_pool_excludes_blocked_rows_and_keeps_best_expression():
    low_duplicate = _candidate("low", "rank(close)", 71)
    high_duplicate = _candidate("high", "rank(close)", 88)
    blocked = _candidate("blocked", "rank(volume)", 99, blocked=True)
    second = _candidate("second", "rank(open)", 82)

    pool = candidate_main_pool([low_duplicate, blocked, second, high_duplicate], target_size=2)

    assert [row["alpha_id"] for row in pool] == ["high", "second"]


def test_candidate_payload_reports_main_pool_separately_from_full_ledger():
    rows = [
        _candidate("kept", "rank(close)", 88),
        _candidate("blocked", "rank(volume)", 99, blocked=True),
    ]

    payload = candidate_payload(rows, source="test", total=len(rows))

    assert [row["alpha_id"] for row in payload["candidates"]] == ["kept", "blocked"]
    assert [row["alpha_id"] for row in payload["main_pool_candidates"]] == ["kept"]
    assert payload["pool_summary"]["main_pool_count"] == 1
    assert payload["pool_summary"]["blocked_or_archived_count"] == 1


def test_candidate_summary_does_not_count_submit_only_blockers_as_hard_blocked():
    submit_only = _candidate("confirm", "rank(open)", 86)
    submit_only["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "blocking_reasons": ["needs_human_confirmation"],
    }
    hard_blocked = _candidate("bad", "rank(volume)", 70, blocked=True)

    summary = candidate_summary([submit_only, hard_blocked])
    pool = candidate_main_pool([submit_only, hard_blocked], target_size=2)

    assert summary["blocked_count"] == 1
    assert [row["alpha_id"] for row in pool] == ["confirm"]


def test_candidate_decision_routes_submit_only_confirmation_to_human_review():
    row = _candidate("confirm", "rank(open)", 91)
    row["scorecard"]["decision_band"] = "submit_candidate"
    row["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "submission_ready": False,
        "blocking_reasons": ["needs_human_confirmation"],
    }

    decision = candidate_production_decision(row)

    assert decision["action"] == "needs_human_confirmation"
    assert decision["next_state"] == "ready_for_review"
    assert decision["blocking"] is False
    assert decision["submit_allowed"] is False


def test_candidate_decision_routes_hard_local_blockers_to_archive():
    row = _candidate("bad", "rank(volume)", 99, blocked=True)

    decision = candidate_production_decision(row)

    assert decision["action"] == "archive"
    assert decision["next_state"] == "archived"
    assert decision["blocking"] is True
    assert "local_quality_failed" in decision["reason_codes"]
    assert candidate_main_pool([row], target_size=1) == []


def test_candidate_decision_routes_high_score_local_candidate_to_official_queue():
    row = _candidate("queue", "rank(close)", 92)
    row["scorecard"]["decision_band"] = "submit_candidate"
    row["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "submission_ready": False,
        "blocking_reasons": ["missing_official_alpha_id", "missing_official_metrics"],
        "reasons": [
            {
                "code": "missing_official_metrics",
                "category": "official_evidence_missing",
                "severity": "blocking",
            }
        ],
    }

    decision = candidate_production_decision(row, min_official_score=70)

    assert decision["action"] == "official_validation_queue"
    assert decision["next_state"] == "queued_for_simulation"
    assert decision["official_api_called"] is False


def test_candidate_payload_uses_lifecycle_failure_before_official_queue():
    row = _candidate("queue", "rank(close)", 92)
    row["scorecard"]["decision_band"] = "submit_candidate"
    row["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "submission_ready": False,
        "blocking_reasons": ["missing_official_metrics"],
        "reasons": [
            {
                "code": "missing_official_metrics",
                "category": "official_evidence_missing",
                "severity": "blocking",
            }
        ],
    }
    payload = candidate_payload(
        [row],
        source="test",
        total=1,
        lifecycle_rows=[
            {
                "alpha_id": "queue",
                "stage": "official_validation",
                "status": "FAILED",
                "timestamp": "2026-06-12T01:00:00Z",
            }
        ],
    )

    candidate = payload["candidates"][0]
    decision = candidate["production_decision"]
    risk = decision["decision_evidence"]["lifecycle_risk"]
    assert decision["action"] == "optimize"
    assert decision["next_state"] == "needs_optimization"
    assert "lifecycle_history_failed" in decision["reason_codes"]
    assert risk["official_api_called"] is False
    assert risk["submit_allowed"] is False
    assert payload["main_pool_candidates"] == []
    assert payload["pool_summary"]["lifecycle_rework_count"] == 1
    assert payload["workflow_plan"]["validator"]["candidate_ids"] == []
    assert payload["workflow_plan"]["rework"]["candidate_ids"] == ["queue"]


def test_candidate_payload_preserves_recovered_lifecycle_replay_evidence_in_decision_audit():
    row = _candidate("recovered_queue", "rank(close)", 93)
    row["scorecard"]["decision_band"] = "submit_candidate"
    row["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "submission_ready": False,
        "blocking_reasons": ["missing_official_metrics"],
        "reasons": [
            {
                "code": "missing_official_metrics",
                "category": "official_evidence_missing",
                "severity": "blocking",
            }
        ],
    }

    payload = candidate_payload(
        [row],
        source="test",
        total=1,
        lifecycle_rows=[
            {
                "alpha_id": "recovered_queue",
                "stage": "generated",
                "status": "READY",
                "timestamp": "2026-06-12T01:00:00Z",
            },
            {
                "alpha_id": "recovered_queue",
                "stage": "official_validation",
                "status": "FAILED",
                "timestamp": "2026-06-12T01:10:00Z",
            },
        ],
    )

    candidate = payload["candidates"][0]
    decision = candidate["production_decision"]
    evidence = decision["decision_evidence"]
    replay = evidence["lifecycle_replay"]
    audit_evidence = candidate["scientific_audit"]["evidence"]

    assert decision["action"] == "optimize"
    assert replay["source"] == "lifecycle_jsonl"
    assert replay["recovered_from_local_history"] is True
    assert replay["matched_event_count"] == 2
    assert replay["matched_by"] == "identity"
    assert replay["latest_status_category"] == "failed"
    assert replay["official_api_called"] is False
    assert replay["submit_allowed"] is False
    assert audit_evidence["lifecycle_replay"] == replay
    assert "lifecycle_history" in audit_evidence["feedback_sources"]


def test_candidate_payload_merges_lifecycle_replay_into_existing_scientific_audit():
    row = _candidate("existing_audit_replay", "rank(close)", 93)
    row["scorecard"]["decision_band"] = "submit_candidate"
    row["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "submission_ready": False,
        "blocking_reasons": ["missing_official_metrics"],
        "reasons": [
            {
                "code": "missing_official_metrics",
                "category": "official_evidence_missing",
                "severity": "blocking",
            }
        ],
    }
    safety_boundary = {
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "real_submit_performed": False,
    }
    anti_overfit = {
        "test_script_outcomes_used": False,
        "test_feedback_allowed": False,
        "feedback_policy": "system-tests-verify-behavior-only",
    }
    row["scientific_audit"] = {
        "schema_version": "candidate-scientific-audit-v1",
        "anti_overfit": dict(anti_overfit),
        "evidence": {"feedback_sources": ["scorecard"], "production_action": "retain"},
        "safety_boundary": dict(safety_boundary),
    }

    payload = candidate_payload(
        [row],
        source="test",
        total=1,
        lifecycle_rows=[
            {
                "alpha_id": "existing_audit_replay",
                "stage": "official_validation",
                "status": "FAILED",
                "timestamp": "2026-06-12T01:10:00Z",
            }
        ],
    )

    candidate = payload["candidates"][0]
    replay = candidate["production_decision"]["decision_evidence"]["lifecycle_replay"]
    audit = candidate["scientific_audit"]
    audit_evidence = audit["evidence"]

    assert candidate["production_decision"]["action"] == "optimize"
    assert audit_evidence["lifecycle_replay"] == replay
    assert audit_evidence["feedback_sources"] == ["lifecycle_history", "scorecard"]
    assert audit["safety_boundary"] == safety_boundary
    assert audit["anti_overfit"] == anti_overfit
    assert candidate["extra_fields"]["scientific_audit"] == audit


def test_candidate_payload_archives_historical_hard_blockers_from_lifecycle():
    row = _candidate("blocked_history", "rank(volume)", 93)
    row["scorecard"]["decision_band"] = "submit_candidate"
    row["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "submission_ready": False,
        "blocking_reasons": ["missing_official_metrics"],
    }

    payload = candidate_payload(
        [row],
        source="test",
        total=1,
        lifecycle_rows=[
            {
                "expression": "rank(volume)",
                "stage": "local_prefilter_rejected",
                "status": "REJECTED",
                "timestamp": "2026-06-12T01:01:00Z",
            }
        ],
    )

    candidate = payload["candidates"][0]
    decision = candidate["production_decision"]
    risk = decision["decision_evidence"]["lifecycle_risk"]
    assert decision["action"] == "archive"
    assert decision["blocking"] is True
    assert risk["matched_by"] == "expression"
    assert risk["action_hint"] == "archive"
    assert "lifecycle_history_failed" in decision["reason_codes"]
    assert payload["main_pool_candidates"] == []
    assert payload["workflow_plan"]["archive"]["candidate_ids"] == ["blocked_history"]


def test_candidate_decision_lifecycle_risk_suppresses_raw_sensitive_fields():
    row = _candidate("raw_lifecycle_risk", "rank(close)", 93)
    row["scorecard"]["decision_band"] = "submit_candidate"
    row["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "submission_ready": False,
        "blocking_reasons": ["missing_official_metrics"],
    }
    row["lifecycle_risk"] = {
        "schema_version": "candidate-lifecycle-risk-v1",
        "source": "lifecycle_jsonl",
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "matched_event_count": 1,
        "matched_by": "identity",
        "latest_stage": "official_validation",
        "latest_status": "FAILED token=RAW_SECRET_TOKEN_123",
        "latest_status_category": "failed",
        "latest_event_at": "2026-06-12T01:10:00Z",
        "action_hint": "optimize",
        "blocking": False,
        "reason_code": "lifecycle_history_failed",
        "raw_notes": "operator note with password=RAW_PASSWORD_123",
        "credentials": {"authorization": "Bearer RAW_AUTH_123"},
        "events": [{"cookie": "brain=RAW_COOKIE_123"}],
    }

    decision = candidate_production_decision(row)

    risk = decision["decision_evidence"]["lifecycle_risk"]
    assert decision["action"] == "optimize"
    assert risk == {
        "schema_version": "candidate-lifecycle-risk-v1",
        "source": "lifecycle_jsonl",
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "matched_event_count": 1,
        "matched_by": "identity",
        "latest_stage": "official_validation",
        "latest_status": "FAILED token=<redacted>",
        "latest_status_category": "failed",
        "latest_event_at": "2026-06-12T01:10:00Z",
        "action_hint": "optimize",
        "blocking": False,
        "reason_code": "lifecycle_history_failed",
    }
    assert "raw_notes" not in risk
    assert "credentials" not in risk
    assert "events" not in risk
    assert "RAW_SECRET" not in str(decision["decision_evidence"])
    assert "RAW_PASSWORD" not in str(decision["decision_evidence"])
    assert "RAW_AUTH" not in str(decision["decision_evidence"])


def test_candidate_decision_blocks_unsafe_scientific_audit_feedback():
    row = _candidate("unsafe_audit", "rank(open)", 96)
    row["scorecard"]["decision_band"] = "submit_candidate"
    row["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "submission_ready": False,
        "blocking_reasons": ["missing_official_metrics"],
    }
    row["scientific_audit"] = {
        "schema_version": "candidate-scientific-audit-v1",
        "anti_overfit": {"test_script_outcomes_used": True},
        "evidence": {"feedback_sources": ["scorecard", "pytest"]},
        "safety_boundary": {
            "local_only": True,
            "official_api_called": False,
            "submit_allowed": False,
            "real_submit_performed": False,
        },
    }

    decision = candidate_production_decision(row)

    assert decision["action"] == "archive"
    assert decision["blocking"] is True
    assert "scientific_audit_test_feedback_used" in decision["reason_codes"]
    assert decision["official_api_called"] is False
    assert decision["submit_allowed"] is False


def test_candidate_decision_blocks_nested_scientific_audit_feedback_substrings():
    row = _candidate("unsafe_nested_audit", "rank(open)", 96)
    row["scorecard"]["decision_band"] = "submit_candidate"
    row["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "submission_ready": False,
        "blocking_reasons": ["missing_official_metrics"],
    }
    row["scientific_audit"] = {
        "schema_version": "candidate-scientific-audit-v1",
        "anti_overfit": {"test_script_outcomes_used": False},
        "evidence": {"feedback_sources": ["scorecard"]},
        "safety_boundary": {"submit_allowed": False, "real_submit_performed": False},
    }
    row["extra_fields"] = {
        "scientific_audit": {
            "schema_version": "candidate-scientific-audit-v1",
            "anti_overfit": {"test_script_outcomes_used": False},
            "evidence": {"feedback_sources": ["browser_smoke_result"]},
            "safety_boundary": {"submit_allowed": False, "real_submit_performed": False},
        }
    }

    decision = candidate_production_decision(row)

    assert decision["action"] == "archive"
    assert decision["blocking"] is True
    assert "scientific_audit_test_feedback_used" in decision["reason_codes"]


def test_candidate_decision_routes_optimize_band_to_optimization_service():
    row = _candidate("opt", "rank(close)", 78)
    row["scorecard"]["decision_band"] = "optimize_before_submit"

    decision = candidate_production_decision(row)

    assert decision["action"] == "optimize"
    assert decision["next_state"] == "needs_optimization"
    assert decision["blocking"] is False


def test_candidate_decision_blocks_submit_ready_at_manual_review_boundary():
    row = _candidate("ready", "rank(close)", 94)
    row["scorecard"]["decision_band"] = "submit_candidate"
    row["quality_diagnosis"] = {"local_candidate_valid": True, "submission_ready": True, "blocking_reasons": []}
    row["gate"] = {"submission_ready": True}
    row["official_alpha_id"] = "off_ready"
    row["official_metrics"] = {"sharpe": 1.7, "fitness": 1.1, "turnover": 0.2}

    decision = candidate_production_decision(row)

    assert decision["action"] == "submit_review_blocked"
    assert decision["next_state"] == "ready_for_review"
    assert decision["submit_allowed"] is False


def test_candidate_payload_attaches_traceable_decisions_and_action_counts():
    rows = [
        _candidate("opt", "rank(close)", 78),
        _candidate("bad", "rank(volume)", 99, blocked=True),
    ]

    payload = candidate_payload(rows, source="test", total=len(rows))

    assert payload["candidates"][0]["production_decision"]["action"] == "optimize"
    assert payload["candidates"][0]["quality_diagnosis"]["production_decision"]["action"] == "optimize"
    assert payload["pool_summary"]["decision_action_counts"]["optimize"] == 1
    assert payload["pool_summary"]["decision_action_counts"]["archive"] == 1


def test_candidate_workflow_plan_decouples_producer_validator_and_rework_queues():
    queue_1 = _candidate("queue_1", "rank(close)", 94)
    queue_1["scorecard"]["decision_band"] = "submit_candidate"
    queue_1["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "blocking_reasons": ["missing_official_metrics"],
        "reasons": [
            {
                "code": "missing_official_metrics",
                "category": "official_evidence_missing",
                "severity": "blocking",
            }
        ],
    }
    queue_2 = _candidate("queue_2", "rank(open)", 91)
    queue_2["scorecard"]["decision_band"] = "submit_candidate"
    queue_2["quality_diagnosis"] = queue_1["quality_diagnosis"]
    optimize = _candidate("optimize", "rank(volume)", 77)
    blocked = _candidate("blocked", "rank(vwap)", 98, blocked=True)
    rows = candidate_payload(
        [queue_2, optimize, blocked, queue_1],
        source="test",
        total=4,
        target_pool_size=5,
    )["candidates"]
    main_pool = candidate_main_pool(rows, target_size=5)

    plan = candidate_workflow_plan(rows, target_size=5, main_pool=main_pool, validator_batch_size=3)

    assert plan["official_api_called"] is False
    assert plan["submit_allowed"] is False
    assert plan["producer"]["active_pool_count"] == 3
    assert plan["producer"]["deficit"] == 2
    assert plan["producer"]["can_continue_while_validator_runs"] is True
    assert plan["validator"]["candidate_ids"] == ["queue_1", "queue_2"]
    assert plan["validator"]["next_candidate_ids"] == ["queue_1", "queue_2"]
    assert plan["rework"]["candidate_ids"] == ["optimize"]
    assert plan["archive"]["candidate_ids"] == ["blocked"]
    assert plan["next_action"] == "run_official_validator"


def test_candidate_workflow_plan_exposes_non_submit_readiness_evidence():
    queue_1 = _candidate("queue_1", "rank(close)", 94)
    queue_1["scorecard"]["decision_band"] = "submit_candidate"
    queue_1["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "blocking_reasons": ["missing_official_alpha_id", "missing_official_metrics"],
        "reasons": [
            {
                "code": "missing_official_alpha_id",
                "category": "official_evidence_missing",
                "severity": "blocking",
            },
            {
                "code": "missing_official_metrics",
                "category": "official_evidence_missing",
                "severity": "blocking",
            },
        ],
    }
    queue_2 = _candidate("queue_2", "rank(open)", 91)
    queue_2["scorecard"]["decision_band"] = "submit_candidate"
    queue_2["quality_diagnosis"] = queue_1["quality_diagnosis"]
    optimize = _candidate("optimize", "rank(volume)", 77)
    blocked = _candidate("blocked", "rank(vwap)", 98, blocked=True)
    rows = candidate_payload(
        [queue_2, optimize, blocked, queue_1],
        source="test",
        total=4,
        target_pool_size=5,
    )["candidates"]
    main_pool = candidate_main_pool(rows, target_size=5)

    plan = candidate_workflow_plan(rows, target_size=5, main_pool=main_pool, validator_batch_size=3)
    evidence = plan["readiness_evidence"]

    assert plan["execution_readiness"] == evidence
    assert evidence["schema_version"] == "candidate-workflow-readiness-evidence-v1"
    assert evidence["local_only"] is True
    assert evidence["official_api_called"] is False
    assert evidence["submit_allowed"] is False
    assert evidence["ready_to_submit"] is False
    assert evidence["stop_rule_required"] is True
    assert evidence["authoritative_stop_rule"] == "scripts/check_live_submit_readiness.py"
    assert evidence["candidate_count"] == 4
    assert evidence["active_pool_deficit"] == 2
    assert evidence["next_safe_action"] == "run_official_validator"
    assert evidence["blocker_counts"]["missing_official_alpha_id"] == 2
    assert evidence["blocker_counts"]["missing_official_metrics"] == 2
    assert evidence["blocker_counts"]["decision_band_not_submit_candidate"] == 1
    assert evidence["blocker_counts"]["local_quality_failed"] == 1
    assert evidence["execution_gap_counts"]["pool_deficit"] == 2
    assert evidence["queue_to_blocker_mapping"]["producer"] == [
        "pool_deficit",
        "no_submit_band_candidate",
    ]
    validator = evidence["queue_evidence"]["validator"]
    assert validator["candidate_ids"] == ["queue_1", "queue_2"]
    assert validator["next_candidate_ids"] == ["queue_1", "queue_2"]
    assert validator["blocker_counts"] == {
        "missing_official_alpha_id": 2,
        "missing_official_metrics": 2,
    }
    assert "missing_official_metrics" in validator["closes_blockers"]
    assert evidence["queue_evidence"]["rework"]["blocker_counts"] == {
        "decision_band_not_submit_candidate": 1,
    }
    assert evidence["queue_evidence"]["archive"]["blocker_counts"] == {
        "local_quality_failed": 1,
    }


def test_candidate_workflow_plan_does_not_dispatch_empty_validator_batch():
    queue = _candidate("queue", "rank(close)", 94)
    queue["scorecard"]["decision_band"] = "submit_candidate"
    queue["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "blocking_reasons": [],
    }
    rows = candidate_payload([queue], source="test", total=1, target_pool_size=1)["candidates"]
    main_pool = candidate_main_pool(rows, target_size=1)

    plan = candidate_workflow_plan(rows, target_size=1, main_pool=main_pool, validator_batch_size=0)

    assert plan["validator"]["candidate_ids"] == ["queue"]
    assert plan["validator"]["next_candidate_ids"] == []
    assert plan["validator"]["next_batch_size"] == 0
    assert plan["next_action"] == "monitor_pool"
    evidence = plan["readiness_evidence"]
    assert evidence["next_safe_action"] == "monitor_pool"
    assert evidence["queue_evidence"]["validator"]["blocker_counts"] == {
        "missing_official_evidence": 1,
    }
    assert "missing_official_evidence" in evidence["queue_to_blocker_mapping"]["validator"]
    assert evidence["submit_allowed"] is False


def test_candidate_workflow_plan_handles_empty_invalid_and_review_only_rows():
    empty_plan = candidate_workflow_plan([None, "bad", {}], target_size=2, main_pool=[], validator_batch_size=3)

    assert empty_plan["producer"]["deficit"] == 2
    assert empty_plan["validator"]["candidate_ids"] == []
    assert empty_plan["next_action"] == "replenish_candidate_pool"
    assert empty_plan["readiness_evidence"]["candidate_count"] == 1
    assert empty_plan["readiness_evidence"]["execution_gap_counts"] == {
        "pool_deficit": 2,
        "no_submit_band_candidate": 1,
    }

    review = _candidate("review", "rank(open)", 94)
    review["scorecard"]["decision_band"] = "submit_candidate"
    review["quality_diagnosis"] = {
        "local_candidate_valid": True,
        "submission_ready": False,
        "blocking_reasons": ["needs_human_confirmation"],
    }
    rows = candidate_payload([review], source="test", total=1, target_pool_size=1)["candidates"]
    main_pool = candidate_main_pool(rows, target_size=1)

    plan = candidate_workflow_plan(rows, target_size=1, main_pool=main_pool, validator_batch_size=3)

    assert plan["review"]["candidate_ids"] == ["review"]
    assert plan["next_action"] == "human_review_required"
    assert plan["readiness_evidence"]["queue_evidence"]["review"]["blocker_counts"] == {
        "needs_human_confirmation": 1,
    }


def test_candidate_payload_exposes_workflow_plan_for_legacy_ledger_rows():
    rows = [
        _candidate("optimize", "rank(volume)", 77),
        _candidate("blocked", "rank(vwap)", 98, blocked=True),
    ]

    payload = candidate_payload(rows, source="test", total=2, target_pool_size=4)

    workflow = payload["workflow_plan"]
    assert payload["candidate_workflow"] == workflow
    assert workflow["schema_version"] == "candidate-pool-workflow-v1"
    assert workflow["readiness_evidence"]["schema_version"] == "candidate-workflow-readiness-evidence-v1"
    assert workflow["readiness_evidence"]["official_api_called"] is False
    assert workflow["readiness_evidence"]["submit_allowed"] is False
    assert workflow["readiness_evidence"]["execution_gap_counts"]["pool_deficit"] == 3
    assert workflow["readiness_evidence"]["execution_gap_counts"]["no_submit_band_candidate"] == 1
    assert workflow["producer"]["deficit"] == 3
    assert workflow["rework"]["candidate_ids"] == ["optimize"]
    assert workflow["archive"]["candidate_ids"] == ["blocked"]


def test_candidate_payload_preserves_optimization_explanation_summary_after_reload():
    row = _candidate("explained", "rank(close)", 88)
    row["extra_fields"] = {
        "optimization_explanation": {
            "schema_version": "candidate-optimization-explanation-v1",
            "official_api_called": False,
            "submit_allowed": False,
            "next_action": "retain_for_candidate_pool",
            "mutation": {
                "mode": "window_refine",
                "parent_failure": "sharpe",
                "optimizer_trace": {
                    "schema_version": "optimizer-trace-v1",
                    "failed_dimension": "sharpe",
                    "selected_strategy": "window_perturb",
                    "official_api_called": False,
                    "submit_allowed": False,
                },
            },
            "official_context": {
                "passed": True,
                "official_api_called": False,
            },
        }
    }

    payload = candidate_payload([row], source="test", total=1)

    summary = payload["optimization_explanations"]
    assert summary["schema_version"] == "candidate-optimization-explanation-summary-v1"
    assert summary["candidate_count"] == 1
    assert summary["explained_count"] == 1
    assert summary["official_context_passed_count"] == 1
    assert summary["non_submit_boundary_intact"] is True
    assert summary["mutation_modes"] == {"window_refine": 1}
    assert summary["parent_failures"] == {"sharpe": 1}


def test_candidate_payload_flags_concentrated_optimization_explanations():
    rows = []
    for alpha_id, mode, failure in (
        ("opt_1", "window_refine", "sharpe"),
        ("opt_2", "window_refine", "sharpe"),
        ("opt_3", "structure_refine", "fitness"),
    ):
        row = _candidate(alpha_id, f"rank({alpha_id})", 80)
        row["extra_fields"] = {
            "optimization_explanation": {
                "schema_version": "candidate-optimization-explanation-v1",
                "official_api_called": False,
                "submit_allowed": False,
                "next_action": "retain_for_candidate_pool",
                "mutation": {
                    "mode": mode,
                    "parent_failure": failure,
                    "optimizer_trace": {
                        "schema_version": "optimizer-trace-v1",
                        "failed_dimension": failure,
                        "selected_strategy": mode,
                        "official_api_called": False,
                        "submit_allowed": False,
                    },
                },
                "official_context": {
                    "passed": True,
                    "official_api_called": False,
                },
            }
        }
        rows.append(row)

    payload = candidate_payload(rows, source="test", total=3)

    audit = payload["optimization_explanations"]["concentration_audit"]
    assert audit["schema_version"] == "optimization-concentration-audit-v1"
    assert audit["local_only"] is True
    assert audit["official_api_called"] is False
    assert audit["submit_allowed"] is False
    assert audit["unique_mutation_mode_count"] == 2
    assert audit["unique_parent_failure_count"] == 2
    assert audit["top_mutation_mode"] == "window_refine"
    assert audit["top_mutation_mode_count"] == 2
    assert audit["top_parent_failure"] == "sharpe"
    assert audit["top_parent_failure_count"] == 2
    assert audit["concentration_risk"] == "moderate"
    assert "mutation_mode_concentration" in audit["risk_reasons"]
    assert "parent_failure_concentration" in audit["risk_reasons"]


def test_candidate_payload_does_not_warn_on_balanced_optimization_explanations():
    rows = []
    for alpha_id, mode, failure in (
        ("opt_1", "window_refine", "sharpe"),
        ("opt_2", "structure_refine", "fitness"),
        ("opt_3", "neutralize_refine", "correlation"),
    ):
        row = _candidate(alpha_id, f"rank({alpha_id})", 80)
        row["extra_fields"] = {
            "optimization_explanation": {
                "schema_version": "candidate-optimization-explanation-v1",
                "official_api_called": False,
                "submit_allowed": False,
                "next_action": "retain_for_candidate_pool",
                "mutation": {
                    "mode": mode,
                    "parent_failure": failure,
                    "optimizer_trace": {
                        "schema_version": "optimizer-trace-v1",
                        "failed_dimension": failure,
                        "selected_strategy": mode,
                        "official_api_called": False,
                        "submit_allowed": False,
                    },
                },
                "official_context": {
                    "passed": True,
                    "official_api_called": False,
                },
            }
        }
        rows.append(row)

    payload = candidate_payload(rows, source="test", total=3)

    audit = payload["optimization_explanations"]["concentration_audit"]
    assert audit["unique_mutation_mode_count"] == 3
    assert audit["unique_parent_failure_count"] == 3
    assert audit["top_mutation_mode_share"] == 0.3333
    assert audit["top_parent_failure_share"] == 0.3333
    assert audit["concentration_risk"] == "none"
    assert audit["risk_reasons"] == []
