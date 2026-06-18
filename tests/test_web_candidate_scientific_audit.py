from brain_alpha_ops.web_candidates.audit import (
    append_scientific_audit_event,
    attach_scientific_audit,
    scientific_audit_policy_reasons,
    scientific_audit_summary,
)


def test_attach_scientific_audit_records_non_submit_boundary_and_redacts_sensitive_values():
    row = {
        "alpha_id": "alpha_audit",
        "expression": "rank(close)",
        "dataset_id": "pv1",
        "source_tags": ["local_only"],
        "scorecard": {"total_score": 82, "decision_band": "optimize_before_submit"},
        "quality_diagnosis": {"blocking_reasons": ["decision_band_not_submit_candidate"]},
        "submission": {
            "retry_count": 2,
            "access_token": "secret-token-123",
            "password": "super-secret",
        },
    }

    audited = attach_scientific_audit(
        row,
        operation="candidate_generation",
        source="local_candidate_generator",
        feedback_sources=["local_backtest_prefilter", "scorecard"],
    )

    audit = audited["scientific_audit"]
    assert audit["schema_version"] == "candidate-scientific-audit-v1"
    assert audit["expression"]["expression_fingerprint"]
    assert audit["evidence"]["feedback_sources"] == ["local_backtest_prefilter", "scorecard"]
    assert audit["safety_boundary"]["local_only"] is True
    assert audit["safety_boundary"]["official_api_called"] is False
    assert audit["safety_boundary"]["submit_allowed"] is False
    assert audit["anti_overfit"]["test_script_outcomes_used"] is False
    assert audit["retry"]["retry_count"] == 2
    assert "secret-token-123" not in str(audit)
    assert "super-secret" not in str(audit)
    assert audited["extra_fields"]["scientific_audit"] == audit


def test_attach_scientific_audit_records_lineage_and_parent_similarity():
    parent = {
        "alpha_id": "alpha_parent",
        "expression": "rank(close)",
        "scorecard": {"total_score": 73},
    }
    child = {
        "alpha_id": "alpha_child",
        "parent_id": "alpha_parent",
        "mutation_type": "window_refine",
        "expression": "rank(ts_rank(close, 30))",
        "scorecard": {"total_score": 84},
    }

    audited = attach_scientific_audit(
        child,
        operation="candidate_optimization",
        source="local_parameter_search",
        parent=parent,
        search_row={
            "score": 91,
            "mutation_mode": "window_refine",
            "metadata": {"reason": "bounded parameter search"},
        },
        feedback_sources=["parameter_search_diagnosis", "local_backtest_prefilter"],
    )

    audit = audited["scientific_audit"]
    assert audit["lineage"]["parent_alpha_id"] == "alpha_parent"
    assert audit["lineage"]["mutation_type"] == "window_refine"
    assert audit["lineage"]["variant_reason"] == "bounded parameter search"
    assert audit["anti_overfit"]["parent_similarity"] < 1.0
    assert audit["events"][0]["operation"] == "candidate_optimization"


def test_attach_scientific_audit_records_expression_delta_and_official_proof():
    child = {
        "alpha_id": "alpha_child",
        "parent_id": "alpha_parent",
        "mutation_type": "window_refine",
        "expression": "rank(ts_rank(close, 30))",
        "extra_fields": {
            "expression_delta": {
                "schema_version": "expression-delta.v1",
                "operators_added": ["ts_rank"],
                "fields_unchanged": ["close"],
            },
            "official_context_proof": {
                "schema_version": "expression-official-context-proof.v1",
                "passed": True,
                "official_api_called": False,
            },
            "optimization_explanation": {
                "schema_version": "candidate-optimization-explanation-v1",
                "official_api_called": False,
                "submit_allowed": False,
                "mutation": {"mode": "window_refine"},
            },
        },
    }

    audited = attach_scientific_audit(
        child,
        operation="candidate_optimization",
        source="local_parameter_search",
    )

    explainability = audited["scientific_audit"]["explainability"]
    assert explainability["expression_delta"]["operators_added"] == ["ts_rank"]
    assert explainability["official_context_proof"]["passed"] is True
    assert explainability["official_context_proof"]["official_api_called"] is False
    assert explainability["optimization_explanation"]["mutation"]["mode"] == "window_refine"


def test_append_scientific_audit_event_preserves_non_submit_boundary():
    audited = attach_scientific_audit(
        {"alpha_id": "alpha_event", "expression": "rank(close)"},
        operation="candidate_generation",
        source="local_candidate_generator",
        feedback_sources=["local_quality"],
    )

    updated = append_scientific_audit_event(
        audited,
        operation="official_simulation_writeback",
        source="web_official_simulation_result",
        feedback_sources=["official_simulation_result"],
        official_api_called=True,
        details={"status": "COMPLETED", "simulation_id": "sim_1"},
    )

    audit = updated["scientific_audit"]
    assert [event["operation"] for event in audit["events"]] == [
        "candidate_generation",
        "official_simulation_writeback",
    ]
    assert audit["events"][-1]["official_api_called"] is True
    assert audit["events"][-1]["details"]["simulation_id"] == "sim_1"
    assert audit["safety_boundary"]["submit_allowed"] is False
    assert audit["safety_boundary"]["real_submit_performed"] is False
    assert "official_simulation_result" in audit["evidence"]["feedback_sources"]


def test_scientific_audit_summary_counts_official_events_without_submit_breach():
    audited = attach_scientific_audit(
        {"alpha_id": "alpha_event_summary", "expression": "rank(close)"},
        operation="candidate_generation",
        source="local_candidate_generator",
    )

    updated = append_scientific_audit_event(
        audited,
        operation="official_simulation_writeback",
        source="web_official_simulation_result",
        feedback_sources=["official_simulation_result"],
        official_api_called=True,
        details={"status": "COMPLETED"},
    )

    summary = scientific_audit_summary([updated])

    assert summary["official_api_called_count"] == 1
    assert summary["submit_allowed_count"] == 0
    assert summary["real_submit_performed_count"] == 0
    assert summary["non_submit_boundary_intact"] is False
    assert scientific_audit_policy_reasons(updated) == []


def test_scientific_audit_policy_reasons_fail_closed_on_event_submit_boundary():
    audited = attach_scientific_audit(
        {"alpha_id": "alpha_event_boundary", "expression": "rank(close)"},
        operation="candidate_generation",
        source="local_candidate_generator",
    )
    audit = dict(audited["scientific_audit"])
    audit["events"] = [
        *audit["events"],
        {
            "operation": "submit_boundary_probe",
            "source": "test_fixture",
            "submit_allowed": True,
            "details": {"real_submit_performed": True},
        },
    ]
    audited["scientific_audit"] = audit
    audited["extra_fields"] = {"scientific_audit": audit}

    summary = scientific_audit_summary([audited])

    assert summary["submit_allowed_count"] == 1
    assert summary["real_submit_performed_count"] == 1
    assert summary["non_submit_boundary_intact"] is False
    assert scientific_audit_policy_reasons(audited) == ["scientific_audit_submit_boundary_breached"]


def test_scientific_audit_summary_counts_missing_and_unsafe_rows():
    audited = attach_scientific_audit(
        {"alpha_id": "safe", "expression": "rank(close)"},
        operation="candidate_generation",
        source="local_candidate_generator",
    )
    unsafe = {
        "alpha_id": "unsafe",
        "expression": "rank(open)",
        "scientific_audit": {
            "schema_version": "candidate-scientific-audit-v1",
            "safety_boundary": {"local_only": False, "official_api_called": True, "submit_allowed": True},
            "anti_overfit": {"test_script_outcomes_used": True},
        },
    }

    summary = scientific_audit_summary([audited, unsafe, {"alpha_id": "missing"}])

    assert summary["schema_version"] == "candidate-scientific-audit-summary-v1"
    assert summary["audited_count"] == 2
    assert summary["missing_audit_count"] == 1
    assert summary["official_api_called_count"] == 1
    assert summary["submit_allowed_count"] == 1
    assert summary["test_feedback_used_count"] == 1


def test_scientific_audit_summary_fails_closed_on_nested_unsafe_audit_copy():
    safe_top_level = attach_scientific_audit(
        {"alpha_id": "shadowed", "expression": "rank(close)"},
        operation="candidate_generation",
        source="local_candidate_generator",
    )
    unsafe_nested = {
        **safe_top_level,
        "extra_fields": {
            "scientific_audit": {
                "schema_version": "candidate-scientific-audit-v1",
                "operation": "candidate_optimization",
                "source": "local_parameter_search",
                "anti_overfit": {"test_script_outcomes_used": False},
                "evidence": {"feedback_sources": ["pytest_result"]},
                "safety_boundary": {
                    "local_only": True,
                    "official_api_called": False,
                    "submit_allowed": False,
                    "real_submit_performed": True,
                },
            }
        },
    }

    summary = scientific_audit_summary([unsafe_nested])

    assert summary["candidate_count"] == 1
    assert summary["audited_count"] == 1
    assert summary["audit_payload_count"] == 2
    assert summary["test_feedback_used_count"] == 1
    assert summary["real_submit_performed_count"] == 1
    assert summary["non_submit_boundary_intact"] is False


def test_scientific_audit_summary_deduplicates_matching_top_level_and_extra_audit():
    audited = attach_scientific_audit(
        {"alpha_id": "dedupe", "expression": "rank(close)"},
        operation="candidate_generation",
        source="local_candidate_generator",
    )

    summary = scientific_audit_summary([audited])

    assert summary["candidate_count"] == 1
    assert summary["audited_count"] == 1
    assert summary["audit_payload_count"] == 1
    assert summary["operations"] == {"candidate_generation": 1}
    assert summary["sources"] == {"local_candidate_generator": 1}
