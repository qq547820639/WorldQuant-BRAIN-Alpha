from __future__ import annotations

from pathlib import Path

from scripts.check_candidate_scientific_audit import check_candidate_scientific_audit


def test_candidate_scientific_audit_check_accepts_current_tree():
    result = check_candidate_scientific_audit()

    assert result["ok"] is True
    assert result["schema_version"] == "candidate_scientific_audit_check.v1"
    assert result["checked_files"] == 11
    assert result["findings"] == []


def test_candidate_scientific_audit_check_rejects_test_feedback_sources(tmp_path):
    root = tmp_path
    _write_required_tree(root)
    generation = root / "brain_alpha_ops" / "web_candidates/generation.py"
    generation.write_text(
        generation.read_text(encoding="utf-8")
        + "\nattach_scientific_audit(row, operation=\"candidate_generation\", feedback_sources=[\"pytest\"])\n",
        encoding="utf-8",
    )

    result = check_candidate_scientific_audit(root)

    assert result["ok"] is False
    assert any(finding["code"] == "test_feedback_source_in_production" for finding in result["findings"])


def test_candidate_scientific_audit_check_rejects_variable_test_feedback_sources(tmp_path):
    root = tmp_path
    _write_required_tree(root)
    generation = root / "brain_alpha_ops" / "web_candidates/generation.py"
    generation.write_text(
        generation.read_text(encoding="utf-8")
        + "\n".join(
            [
                "",
                "def build(row):",
                "    feedback_sources = [\"local_quality\"]",
                "    feedback_sources.append(\"browser_smoke\")",
                "    return attach_scientific_audit(",
                "        row,",
                "        operation=\"candidate_generation\",",
                "        feedback_sources=feedback_sources,",
                "    )",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = check_candidate_scientific_audit(root)

    assert result["ok"] is False
    assert any(finding["code"] == "test_feedback_source_in_production" for finding in result["findings"])


def test_candidate_scientific_audit_check_rejects_module_constant_test_feedback_sources(tmp_path):
    root = tmp_path
    _write_required_tree(root)
    generation = root / "brain_alpha_ops" / "web_candidates/generation.py"
    generation.write_text(
        generation.read_text(encoding="utf-8")
        + "\n".join(
            [
                "",
                'FEEDBACK_SOURCES = ["pytest"]',
                "",
                "def build(row):",
                "    return attach_scientific_audit(",
                "        row,",
                "        operation=\"candidate_generation\",",
                "        feedback_sources=FEEDBACK_SOURCES,",
                "    )",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = check_candidate_scientific_audit(root)

    assert result["ok"] is False
    assert any(finding["code"] == "test_feedback_source_in_production" for finding in result["findings"])


def test_candidate_scientific_audit_check_rejects_append_event_test_feedback_sources(tmp_path):
    root = tmp_path
    _write_required_tree(root)
    simulation = root / "brain_alpha_ops" / "web_candidates/simulation.py"
    simulation.write_text(
        simulation.read_text(encoding="utf-8")
        + "\nappend_scientific_audit_event(row, operation=\"official_simulation_writeback\", feedback_sources=[\"vitest\"])\n",
        encoding="utf-8",
    )

    result = check_candidate_scientific_audit(root)

    assert result["ok"] is False
    assert any(finding["code"] == "test_feedback_source_in_production" for finding in result["findings"])


def test_candidate_scientific_audit_check_scans_simulation_failure_helper(tmp_path):
    root = tmp_path
    _write_required_tree(root)
    simulation_failures = root / "brain_alpha_ops" / "web_candidates/simulation_failures.py"
    simulation_failures.write_text(
        simulation_failures.read_text(encoding="utf-8")
        + "\nappend_scientific_audit_event(row, operation=\"official_simulation_writeback\", feedback_sources=[\"vitest\"])\n",
        encoding="utf-8",
    )

    result = check_candidate_scientific_audit(root)

    assert result["ok"] is False
    assert any(
        finding["code"] == "test_feedback_source_in_production"
        and finding["file"].endswith("web_candidates/simulation_failures.py")
        for finding in result["findings"]
    )


def _write_required_tree(root: Path) -> None:
    (root / "brain_alpha_ops").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / "brain_alpha_ops" / "web_candidates").mkdir(parents=True)
    (root / "brain_alpha_ops" / "web_candidates" / "audit.py").write_text(
        "\n".join(
            [
                "candidate-scientific-audit-v1",
                "candidate-scientific-audit-summary-v1",
                "attach_scientific_audit",
                "append_scientific_audit_event",
                "scientific_audit_summary",
                "test_script_outcomes_used",
                "submit_allowed",
                "official_api_called",
                "redact_data",
                "expression_profile_summary",
                "expression_similarity",
                "official_context_proof",
                "expression_delta",
                "optimization_explanation",
            ]
        ),
        encoding="utf-8",
    )
    (root / "brain_alpha_ops" / "web_candidates" / "generation.py").write_text(
        'attach_scientific_audit(row, operation="candidate_generation")\nscientific_audit_summary(processed_candidates)\n',
        encoding="utf-8",
    )
    (root / "brain_alpha_ops" / "web_candidates" / "optimization.py").write_text(
        'expression_official_context_proof(row)\nexpression_delta(row)\noptimization_explanation(row)\noptimizer_trace(row)\nselected_strategy(row)\nfailed_dimension(row)\nattach_scientific_audit(row, operation="candidate_optimization", parent=parent.to_dict())\nscientific_audit_summary(processed_candidates)\n',
        encoding="utf-8",
    )
    (root / "brain_alpha_ops" / "web_candidates" / "optimization_explainability.py").write_text(
        "\n".join(
            [
                "optimization_concentration_audit",
                "optimization-concentration-audit-v1",
                "concentration_risk",
                "risk_reasons",
                "single_mutation_mode",
                "single_parent_failure",
            ]
        ),
        encoding="utf-8",
    )
    (root / "brain_alpha_ops" / "web_candidates" / "decisions.py").write_text(
        'attach_scientific_audit(row, operation="production_decision")\n',
        encoding="utf-8",
    )
    (root / "brain_alpha_ops" / "web_candidates" / "payloads.py").write_text(
        "scientific_audit_summary(annotated_rows)\n",
        encoding="utf-8",
    )
    (root / "brain_alpha_ops" / "web_candidates" / "simulation.py").write_text(
        'append_scientific_audit_event(row, operation="official_simulation_writeback")\n',
        encoding="utf-8",
    )
    (root / "brain_alpha_ops" / "web_candidates" / "simulation_failures.py").write_text(
        'append_scientific_audit_event(row, operation="official_simulation_writeback")\n',
        encoding="utf-8",
    )
    (root / "brain_alpha_ops" / "web_candidates" / "check_evidence.py").write_text(
        'append_scientific_audit_event(row, operation="pre_submit_availability_check")\n',
        encoding="utf-8",
    )
    (root / "brain_alpha_ops" / "research" / "pipeline_runtime").mkdir(parents=True)
    (root / "brain_alpha_ops" / "research" / "pipeline_runtime" / "_records_mixin.py").write_text(
        'append_scientific_audit_event(row, operation="robustness_feedback")\n',
        encoding="utf-8",
    )
    (root / "scripts" / "quality_gate").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "quality_gate" / "__init__.py").write_text(
        "candidate_scientific_audit\n",
        encoding="utf-8",
    )
