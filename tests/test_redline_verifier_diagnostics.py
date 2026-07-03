import logging

from brain_alpha_ops import data as data_module
from brain_alpha_ops.research import generator as generator_module
from brain_alpha_ops.compliance import redline_checks as redline_check_alignment
from brain_alpha_ops.compliance import redline_checks as redline_check_coverage
from brain_alpha_ops.compliance import redline_checks as redline_check_datasets
from brain_alpha_ops.compliance import redline_checks as redline_check_no_custom_extension
from brain_alpha_ops.compliance import redline_checks as redline_check_thresholds
from brain_alpha_ops.compliance import redline_checks as redline_check_traceability
from brain_alpha_ops.compliance import redline_core as redline_models
from brain_alpha_ops.compliance import redline_verifier


def test_redline_verifier_reexports_report_models():
    assert redline_verifier.RedLineViolation is redline_models.RedLineViolation
    assert redline_verifier.ComplianceReport is redline_models.ComplianceReport
    assert redline_verifier.RedLineBlockedError is redline_models.RedLineBlockedError


def test_redline_verifier_reexports_check_functions():
    assert (
        redline_verifier._verify_redline_1_no_custom_extension
        is redline_check_no_custom_extension._verify_redline_1_no_custom_extension
    )
    assert (
        redline_verifier._verify_redline_2_threshold_zero_deviation
        is redline_check_thresholds._verify_redline_2_threshold_zero_deviation
    )
    assert redline_verifier._verify_redline_3_dataset_ids is redline_check_datasets._verify_redline_3_dataset_ids
    assert (
        redline_verifier._verify_redline_4_parameter_traceability
        is redline_check_traceability._verify_redline_4_parameter_traceability
    )
    assert redline_verifier._verify_redline_5_factor_coverage is redline_check_coverage._verify_redline_5_factor_coverage
    assert redline_verifier._verify_redline_6_code_alignment is redline_check_alignment._verify_redline_6_code_alignment


def test_candidate_generator_fallback_template_extraction_warns_on_failure(monkeypatch, caplog):
    def fail_load_fallback_templates():
        raise OSError("source unavailable")

    monkeypatch.setattr(generator_module, "_load_fallback_templates", fail_load_fallback_templates)

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.compliance.redline_verifier"):
        templates = redline_verifier._candidate_generator_fallback_templates()

    assert templates == []
    assert "redline verifier failed to extract generator fallback templates" in caplog.text


def test_verification_blocked_logs_warning(caplog):
    report = redline_verifier.ComplianceReport()
    error = RuntimeError("canonical evidence unavailable")

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.compliance.redline_verifier"):
        redline_verifier._verification_blocked(
            report,
            redline_id=6,
            redline_name="代码强对齐",
            file_path="brain_alpha_ops/config.py",
            check_name="无法验证官方 API base_url",
            error=error,
            expected="官方 API endpoint 可验证",
            fix_guidance="修复 canonical evidence 加载。",
        )

    assert report.failed == 1
    assert report.violations[0].actual_value == "canonical evidence unavailable"
    assert "redline verification blocked: redline_id=6" in caplog.text
    assert "canonical evidence unavailable" in caplog.text


def test_generator_template_official_context_failure_logs_warning(monkeypatch, tmp_path, caplog):
    class FailingOfficialDataLoader:
        def load_all(self, _data_dir):
            raise OSError("official context missing")

    monkeypatch.setattr(data_module, "OfficialDataLoader", FailingOfficialDataLoader)

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.compliance.redline_verifier"):
        result = redline_verifier._verify_generator_templates_against_official_context(tmp_path)

    assert result == {"ok": False, "reason": "official context unavailable: official context missing"}
    assert "redline verifier official context unavailable for generator template validation" in caplog.text
    assert "official context missing" in caplog.text
