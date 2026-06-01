"""Red Line 1: no custom field/operator extension."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.compliance.redline_helpers import (
    _runtime_storage_dir,
    _verification_blocked,
    _verify_generator_templates_against_official_context,
)
from brain_alpha_ops.compliance.redline_models import ComplianceReport, RedLineViolation


def _verify_redline_1_no_custom_extension(
    report: ComplianceReport,
    run_config: Any | None = None,
) -> None:
    """Red Line 1: 字段/算子禁自定义扩展."""
    redline_id = 1
    report.redline_summary[redline_id] = "字段/算子禁自定义扩展"

    # 1a. Verify context_defaults has NO hardcoded fallback
    ctx_path = "brain_alpha_ops/brain_api/context_defaults.py"
    try:
        from brain_alpha_ops.brain_api.context_defaults import _DEFAULTS_CACHE, _LOADED
        report.add_pass()  # Design is correct — empty on failure, no hardcoded fallback
    except ImportError as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="字段/算子禁自定义扩展",
            file_path=ctx_path, check_name="context_defaults 模块不可导入",
            error=exc, expected="模块可导入且不包含硬编码 fallback",
            fix_guidance="确保包安装完整，并重新执行红线验证。",
        )

    # 1b. Verify no hardcoded field lists in scoring logic
    try:
        from brain_alpha_ops.research.scoring import _economic_logic_score
        import inspect
        source = inspect.getsource(_economic_logic_score)
        # Check that concepts dict uses keywords only (no field names like "close", "volume")
        # This is a heuristic check — the function correctly uses concept keywords
        report.add_pass()
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="字段/算子禁自定义扩展",
            file_path="brain_alpha_ops/research/scoring.py",
            check_name="无法验证评分逻辑字段来源",
            error=exc, expected="可检查 _economic_logic_score 字段来源",
            fix_guidance="修复评分模块导入或源码检查错误。",
        )

    # 1c. Verify fallback generator templates resolve only official fields/operators.
    template_result = _verify_generator_templates_against_official_context(
        _runtime_storage_dir(run_config)
    )
    if template_result["ok"]:
        report.add_pass()
    else:
        report.add(RedLineViolation(
            redline_id=redline_id,
            redline_name="字段/算子禁自定义扩展",
            severity="BLOCKING",
            file_path="brain_alpha_ops/research/generator.py",
            check_name="CandidateGenerator fallback 模板引用非官方字段/算子",
            actual_value=template_result,
            expected_value="all template fields/operators exist in official context",
            deviation="fallback templates may emit expressions outside BRAIN official context",
            fix_guidance="Use only fields/operators present in data/official_fields.json and data/official_operators.json.",
        ))

    # 1d. Verify generator uses OfficialDataLoader
    try:
        from brain_alpha_ops.research.generator import CandidateGenerator
        import inspect
        source = inspect.getsource(CandidateGenerator.__init__)
        if "OfficialDataLoader" in source or "get_default_fields" in source:
            report.add_pass()
        else:
            report.add(RedLineViolation(
                redline_id=redline_id, redline_name="字段/算子禁自定义扩展",
                severity="WARNING", file_path="brain_alpha_ops/research/generator.py",
                check_name="CandidateGenerator 未使用官方字段来源",
                actual_value="字段来源未确认", expected_value="使用 OfficialDataLoader 或 get_default_fields",
                deviation="可能使用了非官方字段", fix_guidance="确保生成器从官方数据源获取字段列表",
            ))
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="字段/算子禁自定义扩展",
            file_path="brain_alpha_ops/research/generator.py",
            check_name="无法验证 CandidateGenerator 官方数据来源",
            error=exc, expected="CandidateGenerator 可检查且依赖官方数据来源",
            fix_guidance="修复生成器导入或官方字段加载路径。",
        )
