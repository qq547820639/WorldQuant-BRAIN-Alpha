"""Red Line 5: complete factor coverage."""

from __future__ import annotations

from brain_alpha_ops.compliance.redline_helpers import _verification_blocked
from brain_alpha_ops.compliance.redline_models import ComplianceReport, RedLineViolation


def _verify_redline_5_factor_coverage(report: ComplianceReport) -> None:
    """Red Line 5: 要素全覆盖."""
    redline_id = 5
    report.redline_summary[redline_id] = "要素全覆盖"

    # BRAIN Alpha Check complete set
    required_checks = [
        ("LOW_SHARPE", "sharpe", "is_hard_gate"),
        ("LOW_FITNESS", "fitness", "is_hard_gate"),
        ("LOW_TURNOVER", "turnover_min", "is_hard_gate"),
        ("HIGH_TURNOVER", "turnover_platform", "is_hard_gate"),
        ("SELF_CORRELATION", "self_correlation", "is_hard_gate"),
        ("CONCENTRATED_WEIGHT", "weight_concentration", "is_hard_gate"),
        ("LOW_SUB_UNIVERSE_SHARPE", "sub_universe_sharpe", "is_hard_gate"),
    ]

    try:
        import inspect

        from brain_alpha_ops.research.scoring import empirical_score
        source = inspect.getsource(empirical_score)
        for check_id, check_name, tag in required_checks:
            if check_name in source and tag in source:
                report.add_pass()
            else:
                report.add(RedLineViolation(
                    redline_id=redline_id, redline_name="要素全覆盖",
                    severity="BLOCKING", file_path="brain_alpha_ops/research/scoring.py",
                    check_name=f"缺少 BRAIN Alpha Check: {check_id}",
                    actual_value=f"未找到 {check_name}", expected_value=f"包含 {check_id} ({check_name})",
                    deviation=f"empirical_score 未覆盖 {check_id}",
                    fix_guidance=f"在 empirical_score 的 items 中添加 {check_name} 检查项",
                ))
    except Exception as exc:
        for check_id, check_name, _tag in required_checks:
            _verification_blocked(
                report,
                redline_id=redline_id,
                redline_name="要素全覆盖",
                file_path="brain_alpha_ops/research/scoring.py",
                check_name=f"无法验证覆盖: {check_id}",
                error=exc,
                expected=f"包含 {check_id} ({check_name})",
                fix_guidance="修复 empirical_score 导入或代码检查。",
            )

    # 5b. Verify fitness_crosscheck exists
    try:
        from brain_alpha_ops.research.scoring import calculate_fitness
        report.add_pass()
    except ImportError as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="要素全覆盖",
            file_path="brain_alpha_ops/research/scoring.py",
            check_name="缺少 Fitness 交叉验证",
            error=exc, expected="函数可导入",
            fix_guidance="确保 calculate_fitness 函数在 scoring.py 中定义。",
        )

    # 5c. Verify self_correlation exception rule
    try:
        import inspect

        from brain_alpha_ops.research.scoring import _build_self_correlation_item
        source = inspect.getsource(_build_self_correlation_item)
        if "exception_applied" in source and "1.10" in source:
            report.add_pass()
        else:
            report.add(RedLineViolation(
                redline_id=redline_id, redline_name="要素全覆盖",
                severity="WARNING", file_path="brain_alpha_ops/research/scoring.py",
                check_name="SELF_CORRELATION 豁免规则可能缺失",
                actual_value="未确认", expected_value="包含 Sharpe×1.10 豁免规则",
                deviation="BRAIN 官方 SELF_CORRELATION 豁免规则可能未被实现",
                fix_guidance="确认 _build_self_correlation_item 实现了 exception_applied 逻辑",
            ))
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="要素全覆盖",
            file_path="brain_alpha_ops/research/scoring.py",
            check_name="无法验证 SELF_CORRELATION 豁免规则",
            error=exc, expected="包含 Sharpe×1.10 豁免规则",
            fix_guidance="修复 _build_self_correlation_item 导入或实现。",
        )
