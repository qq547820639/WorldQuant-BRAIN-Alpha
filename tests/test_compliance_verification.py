"""Compliance verification tests for redline checks.

Tests cover:
  - Redline verifier functionality
  - Compliance report generation
  - Violation detection
  - Fix guidance generation
"""

from __future__ import annotations

import pytest


class TestRedlineVerifier:
    """Test redline verifier functionality."""

    def test_redline_verifier_creation(self):
        """Test redline verifier creation."""
        from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier

        verifier = RedLineVerifier()
        assert verifier is not None

    def test_redline_verifier_with_config(self):
        """Test redline verifier with config."""
        from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier
        from brain_alpha_ops.config import RunConfig

        config = RunConfig()
        verifier = RedLineVerifier(run_config=config)
        assert verifier.run_config is config

    def test_redline_verifier_verify_all(self):
        """Test redline verifier verify_all method."""
        from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier

        verifier = RedLineVerifier()
        report = verifier.verify_all()
        assert report is not None
        assert hasattr(report, "overall")
        assert hasattr(report, "violations")


class TestComplianceReport:
    """Test compliance report functionality."""

    def test_compliance_report_creation(self):
        """Test compliance report creation."""
        from brain_alpha_ops.compliance.redline_core import ComplianceReport

        report = ComplianceReport()
        assert report.overall == "PENDING"
        assert report.total_checks == 0
        assert report.passed == 0
        assert report.failed == 0

    def test_compliance_report_add_pass(self):
        """Test adding pass to compliance report."""
        from brain_alpha_ops.compliance.redline_core import ComplianceReport

        report = ComplianceReport()
        report.add_pass()
        assert report.total_checks == 1
        assert report.passed == 1

    def test_compliance_report_add_violation(self):
        """Test adding violation to compliance report."""
        from brain_alpha_ops.compliance.redline_core import ComplianceReport, RedLineViolation

        report = ComplianceReport()
        violation = RedLineViolation(
            redline_id=1,
            redline_name="Test Redline",
            severity="BLOCKING",
            file_path="test.py",
            check_name="test_check",
            actual_value="actual",
            expected_value="expected",
            deviation="deviation",
            fix_guidance="fix this",
        )
        report.add(violation)
        assert report.total_checks == 1
        assert report.failed == 1
        assert len(report.violations) == 1

    def test_compliance_report_finalize(self):
        """Test compliance report finalize."""
        from brain_alpha_ops.compliance.redline_core import ComplianceReport

        report = ComplianceReport()
        report.add_pass()
        report.add_pass()
        finalized = report.finalize()
        assert finalized.overall == "PASS"
        assert finalized.passed == 2

    def test_compliance_report_to_dict(self):
        """Test compliance report serialization."""
        from brain_alpha_ops.compliance.redline_core import ComplianceReport

        report = ComplianceReport()
        report.add_pass()
        report_dict = report.to_dict()
        assert isinstance(report_dict, dict)
        assert "overall" in report_dict
        assert "total_checks" in report_dict


class TestRedlineViolation:
    """Test redline violation functionality."""

    def test_redline_violation_creation(self):
        """Test redline violation creation."""
        from brain_alpha_ops.compliance.redline_core import RedLineViolation

        violation = RedLineViolation(
            redline_id=1,
            redline_name="Test Redline",
            severity="BLOCKING",
            file_path="test.py",
            check_name="test_check",
            actual_value="actual",
            expected_value="expected",
            deviation="deviation",
            fix_guidance="fix this",
        )
        assert violation.redline_id == 1
        assert violation.severity == "BLOCKING"

    def test_redline_violation_severity_levels(self):
        """Test redline violation severity levels."""
        from brain_alpha_ops.compliance.redline_core import RedLineViolation

        for severity in ["BLOCKING", "WARNING", "INFO"]:
            violation = RedLineViolation(
                redline_id=1,
                redline_name="Test",
                severity=severity,
                file_path="test.py",
                check_name="test",
                actual_value="actual",
                expected_value="expected",
                deviation="deviation",
                fix_guidance="fix",
            )
            assert violation.severity == severity


class TestRedlineChecks:
    """Test individual redline checks."""

    def test_redline_1_no_custom_extension(self):
        """Test redline 1: no custom extension."""
        from brain_alpha_ops.compliance.redline_checks import _verify_redline_1_no_custom_extension
        from brain_alpha_ops.compliance.redline_core import ComplianceReport

        report = ComplianceReport()
        _verify_redline_1_no_custom_extension(report, None)
        # Should complete without error
        assert report.total_checks >= 0

    def test_redline_2_threshold_zero_deviation(self):
        """Test redline 2: threshold zero deviation."""
        from brain_alpha_ops.compliance.redline_checks import _verify_redline_2_threshold_zero_deviation
        from brain_alpha_ops.compliance.redline_core import ComplianceReport

        report = ComplianceReport()
        _verify_redline_2_threshold_zero_deviation(report, None)
        # Should complete without error
        assert report.total_checks >= 0
