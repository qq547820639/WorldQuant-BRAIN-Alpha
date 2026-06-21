"""Red Line 5: complete factor coverage."""

from __future__ import annotations

import ast
from pathlib import Path

from brain_alpha_ops.compliance.redline_helpers import _verification_blocked
from brain_alpha_ops.compliance.redline_models import ComplianceReport, RedLineViolation


def _verify_redline_5_factor_coverage(report: ComplianceReport) -> None:
    """Red Line 5: complete factor coverage — uses explicit constants and AST
    instead of inspect.getsource, which fails in PyInstaller builds."""
    redline_id = 5
    report.redline_summary[redline_id] = "要素全覆盖"

    required_checks = [
        ("LOW_SHARPE", "sharpe"),
        ("LOW_FITNESS", "fitness"),
        ("LOW_TURNOVER", "turnover_min"),
        ("HIGH_TURNOVER", "turnover_platform"),
        ("SELF_CORRELATION", "self_correlation"),
        ("CONCENTRATED_WEIGHT", "weight_concentration"),
        ("LOW_SUB_UNIVERSE_SHARPE", "sub_universe_sharpe"),
    ]

    # 5a. Check against the canonical constant in scoring.py
    try:
        from brain_alpha_ops.research.scoring import EMPRIRICAL_CHECK_ITEM_NAMES
        actual_names = set(EMPRIRICAL_CHECK_ITEM_NAMES)
        for check_id, check_name in required_checks:
            if check_name in actual_names:
                report.add_pass()
            else:
                report.add(RedLineViolation(
                    redline_id=redline_id, redline_name="要素全覆盖",
                    severity="BLOCKING", file_path="brain_alpha_ops/research/scoring.py",
                    check_name=f"缺少 BRAIN Alpha Check: {check_id}",
                    actual_value=f"EMPRIRICAL_CHECK_ITEM_NAMES 缺 {check_name}",
                    expected_value=f"包含 {check_id} ({check_name})",
                    deviation=f"empirical_score 未覆盖 {check_id}",
                    fix_guidance=f"在 empirical_score 的 items 中添加 {check_name} 检查项并更新 EMPRIRICAL_CHECK_ITEM_NAMES。",
                ))
    except ImportError as exc:
        for check_id, check_name in required_checks:
            _verification_blocked(
                report, redline_id=redline_id, redline_name="要素全覆盖",
                file_path="brain_alpha_ops/research/scoring.py",
                check_name=f"无法导入 EMPRIRICAL_CHECK_ITEM_NAMES: {check_id}",
                error=exc, expected=f"包含 {check_id} ({check_name})",
                fix_guidance="确保 scoring.py 定义了 EMPRIRICAL_CHECK_ITEM_NAMES 常量。",
            )

    # 5b. Verify calculate_fitness exists
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

    # 5c. Verify self_correlation exception rule via AST (survives PyInstaller)
    try:
        scoring_path = Path(__file__).resolve().parents[2] / "research" / "scoring.py"
        tree = ast.parse(scoring_path.read_text(encoding="utf-8"))
        has_exception_applied = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_build_self_correlation_item":
                for child in ast.walk(node):
                    if isinstance(child, ast.Constant) and isinstance(child.value, str):
                        if "exception_applied" in child.value:
                            has_exception_applied = True
                            break
                    elif isinstance(child, ast.Name) and child.id == "exception_applied":
                        has_exception_applied = True
                        break
        if has_exception_applied:
            report.add_pass()
        else:
            report.add(RedLineViolation(
                redline_id=redline_id, redline_name="要素全覆盖",
                severity="WARNING", file_path="brain_alpha_ops/research/scoring.py",
                check_name="SELF_CORRELATION 豁免规则可能缺失",
                actual_value="未确认", expected_value="包含 exception_applied 逻辑",
                deviation="BRAIN 官方 SELF_CORRELATION 豁免规则可能未被实现",
                fix_guidance="确认 _build_self_correlation_item 实现了 exception_applied 逻辑。",
            ))
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="要素全覆盖",
            file_path="brain_alpha_ops/research/scoring.py",
            check_name="无法验证 SELF_CORRELATION 豁免规则",
            error=exc, expected="包含 exception_applied 逻辑",
            fix_guidance="修复 _build_self_correlation_item 导入或实现。",
        )
