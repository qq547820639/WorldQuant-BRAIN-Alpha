"""Tests for UX error translation and status code localization."""

from __future__ import annotations

import pytest

from brain_alpha_ops.ux.errors import (
    PHASE_GUIDANCE,
    STATUS_CODE_ZH,
    format_gate_failure,
    get_phase_guidance,
    translate_check_result,
    translate_error,
    translate_status_code,
)


class TestTranslateStatusCode:
    """Test status code to Chinese translation."""

    def test_known_code_exact_match(self):
        assert translate_status_code("SUBMISSION_READY") == "提交就绪"
        assert translate_status_code("NEEDS_ITERATION") == "需要迭代优化"

    def test_known_code_lowercase(self):
        assert translate_status_code("completed") == "已完成"
        assert translate_status_code("failed") == "已失败"

    def test_unknown_code_fallback(self):
        assert translate_status_code("CUSTOM_STATUS") == "CUSTOM_STATUS"
        assert translate_status_code("never_seen_before") == "never_seen_before"

    def test_empty_code(self):
        assert translate_status_code("") == "未知"

    def test_none_code(self):
        assert translate_status_code(None) == "未知"  # type: ignore

    def test_all_status_codes_have_translations(self):
        """Verify common status codes are covered."""
        required = [
            "created", "generated", "scored", "submitted",
            "completed", "failed", "running", "pending",
            "PASS", "FAIL", "BLOCKED", "PENDING",
        ]
        for code in required:
            result = translate_status_code(code)
            assert result != code or code in STATUS_CODE_ZH, f"Missing translation for: {code}"


class TestTranslateError:
    """Test error message translation."""

    def test_translate_auth_error(self):
        result = translate_error("authentication failed: invalid credentials")
        assert result["friendly"] == "BRAIN 平台认证失败"
        assert "BRAIN_USERNAME" in result["suggested_action"]
        assert result["error_code"] == "AUTHENTICATION"

    def test_translate_rate_limit_error(self):
        result = translate_error("429 Too Many Requests - rate limit exceeded")
        assert result["friendly"] == "API 请求频率超限，请稍后重试"
        assert "official_retry_pause_seconds" in result["suggested_action"]

    def test_translate_correlation_error(self):
        result = translate_error("check failed: correlation too high with existing alpha")
        assert "关联度" in result["friendly"]
        assert "算子" in result["suggested_action"] or "字段" in result["suggested_action"]

    def test_translate_turnover_error(self):
        result = translate_error("turnover exceeds platform_max_turnover=0.70")
        assert "换手率" in result["friendly"]
        assert result["error_code"] == "TURNOVER"

    def test_translate_concentration_error(self):
        result = translate_error("weight_concentration check failed: 0.15 > 0.10")
        assert "集中度" in result["friendly"]
        assert result["error_code"] == "CONCENTRATION"

    def test_translate_unknown_error(self):
        result = translate_error("something_completely_unexpected_xyz")
        assert result["friendly"] == "操作未能完成"
        assert result["error_code"] == "GENERIC_ERROR"

    def test_translate_empty_error(self):
        result = translate_error("")
        assert result["friendly"] == "发生未知错误"
        assert result["error_code"] == "UNKNOWN"

    def test_translate_returns_dict_with_all_keys(self):
        result = translate_error("authentication failed")
        assert "original" in result
        assert "friendly" in result
        assert "suggested_action" in result
        assert "error_code" in result


class TestTranslateCheckResult:
    """Test check result descriptions."""

    def test_known_check_returns_info(self):
        result = translate_check_result("sharpe_positive")
        assert result["name"] == "夏普比率 ≥ 1.25"
        assert "风险" in result["meaning"]
        assert result["fix"]

    def test_unknown_check_returns_generic(self):
        result = translate_check_result("custom_check_xyz")
        assert result["name"] == "custom_check_xyz"
        assert result["meaning"] == "质量检查项"

    def test_all_hard_gate_checks_have_descriptions(self):
        """Verify all ERROR-severity checks have user-friendly descriptions."""
        hard_gates = [
            "sharpe_positive",
            "fitness_minimum",
            "turnover_platform",
            "self_correlation",
            "prod_correlation",
            "weight_concentration",
            "sub_universe_sharpe",
            "expression_valid",
        ]
        for check in hard_gates:
            result = translate_check_result(check)
            assert result["name"] != check, f"Missing description for hard gate: {check}"


class TestFormatGateFailure:
    """Test gate failure formatting."""

    def test_format_known_failure(self):
        result = format_gate_failure("sharpe_positive 1.20 < 1.25 (actual: 0.95)")
        assert result["friendly_name"] == "夏普比率 ≥ 1.25"
        assert "风险" in result["meaning"]

    def test_format_unknown_failure(self):
        result = format_gate_failure("custom_check: something failed")
        assert result["friendly_name"] == "custom_check"
        assert "评分详情" in result["fix"]

    def test_format_with_raw_preserved(self):
        raw = "turnover_platform 0.85 > 0.70 (actual: 0.85)"
        result = format_gate_failure(raw)
        assert result["raw"] == raw


class TestPhaseGuidance:
    """Test workflow phase guidance."""

    def test_known_phases(self):
        phases = ["connection", "sync", "generate", "score", "check", "submit"]
        for phase in phases:
            guidance = get_phase_guidance(phase)
            assert "title" in guidance
            assert "description" in guidance
            assert "action" in guidance
            assert guidance["title"] != phase  # Should be Chinese

    def test_unknown_phase(self):
        guidance = get_phase_guidance("unknown_phase")
        assert guidance["title"] == "unknown_phase"

    def test_phase_guidance_consistency(self):
        """All defined phases should have non-empty content."""
        for phase, guidance in PHASE_GUIDANCE.items():
            assert guidance["title"], f"Empty title for phase: {phase}"
            assert guidance["description"], f"Empty description for phase: {phase}"
            assert guidance["action"], f"Empty action for phase: {phase}"


class TestStatusCodeCoverage:
    """Test that all status codes have Chinese translations."""

    def test_job_statuses_covered(self):
        job_statuses = ["starting", "running", "completed", "failed", "pending", "idle"]
        for status in job_statuses:
            result = translate_status_code(status)
            assert result != status, f"Job status not translated: {status}"

    def test_gate_statuses_covered(self):
        gate_statuses = ["SUBMISSION_READY", "NEEDS_ITERATION", "BLOCKED"]
        for status in gate_statuses:
            result = translate_status_code(status)
            assert result != status, f"Gate status not translated: {status}"

    def test_decision_bands_covered(self):
        bands = ["submit_candidate", "optimize_before_submit", "research_only", "abandon_or_rebuild"]
        for band in bands:
            result = translate_status_code(band)
            assert result != band, f"Decision band not translated: {band}"
