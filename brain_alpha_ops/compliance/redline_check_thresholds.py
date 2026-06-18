"""Red Line 2: zero deviation from canonical thresholds."""

from __future__ import annotations

import json
from typing import Any

from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS
from brain_alpha_ops.compliance.redline_helpers import (
    _project_root,
    _verification_blocked,
)
from brain_alpha_ops.compliance.redline_models import ComplianceReport, RedLineViolation


def _verify_redline_2_threshold_zero_deviation(
    report: ComplianceReport,
    run_config: Any | None = None,
) -> None:
    """Red Line 2: 阈值零偏差."""
    redline_id = 2
    report.redline_summary[redline_id] = "阈值零偏差"

    config_path = _project_root() / "config" / "run_config.json"
    actual_thresholds: dict[str, Any] | None = None
    source_path = str(config_path)

    # 2a. Verify the thresholds used by this run, falling back to the release config for CLI use.
    if run_config is not None:
        try:
            thresholds = run_config.ops.thresholds
            actual_thresholds = {
                key: getattr(thresholds, key, None)
                for key in CANONICAL_THRESHOLDS
            }
            source_path = "runtime.ops.thresholds"
        except Exception as exc:
            _verification_blocked(
                report, redline_id=redline_id, redline_name="阈值零偏差",
                file_path="runtime.ops.thresholds", check_name="运行阈值不可读取",
                error=exc, expected="运行配置包含完整 canonical thresholds",
                fix_guidance="修复运行配置加载后重新执行红线验证。",
            )
    elif config_path.exists():
        try:
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
            actual_thresholds = config_data.get("ops", {}).get("thresholds", {})
        except Exception as exc:
            _verification_blocked(
                report, redline_id=redline_id, redline_name="阈值零偏差",
                file_path=str(config_path), check_name="阈值配置无法读取",
                error=exc, expected="有效 JSON 且包含 canonical thresholds",
                fix_guidance="修复 config/run_config.json 格式。",
            )
    else:
        try:
            from brain_alpha_ops.config import QualityThresholds
            thresholds = QualityThresholds()
            actual_thresholds = {
                key: getattr(thresholds, key, None)
                for key in CANONICAL_THRESHOLDS
            }
            source_path = "brain_alpha_ops/config.py"
        except Exception as exc:
            _verification_blocked(
                report, redline_id=redline_id, redline_name="阈值零偏差",
                file_path="brain_alpha_ops/config.py", check_name="默认阈值不可读取",
                error=exc, expected="QualityThresholds 可导入且完整",
                fix_guidance="确保配置模块可导入。",
            )

    if actual_thresholds is not None:
        for key, canonical_value in CANONICAL_THRESHOLDS.items():
            actual = actual_thresholds.get(key)
            if actual is None:
                report.add(RedLineViolation(
                    redline_id=redline_id, redline_name="阈值零偏差",
                    severity="BLOCKING", file_path=source_path,
                    check_name=f"阈值缺失: {key}",
                    actual_value="缺失", expected_value=canonical_value,
                    deviation="运行阈值中未找到 canonical 参数",
                    fix_guidance=f"设置 {key}={canonical_value} 后重新验证。",
                ))
            elif actual != canonical_value:
                report.add(RedLineViolation(
                    redline_id=redline_id, redline_name="阈值零偏差",
                    severity="BLOCKING", file_path=source_path,
                    check_name=f"阈值偏差: {key}",
                    actual_value=actual, expected_value=canonical_value,
                    deviation=f"偏差 {abs(float(actual) - float(canonical_value)):.4f}",  # S-05: type safety
                    fix_guidance=f"将 {key} 调整为 {canonical_value} (BRAIN canonical)。",
                ))
            else:
                report.add_pass()

    # 2d. Verify official hard gates are not adjusted by local market-regime factors.
    try:
        import inspect

        from brain_alpha_ops.research.scoring import empirical_score

        source = inspect.getsource(empirical_score)
        forbidden = [
            "effective_min_sharpe = effective_min_sharpe *",
            "effective_min_fitness = effective_min_fitness *",
            "regime_sharpe_factor",
            "regime_fitness_factor",
        ]
        offenders = [token for token in forbidden if token in source]
        if offenders:
            report.add(RedLineViolation(
                redline_id=redline_id,
                redline_name="阈值零偏差",
                severity="BLOCKING",
                file_path="brain_alpha_ops/research/scoring.py",
                check_name="官方硬门槛被本地 market regime 调整",
                actual_value=", ".join(offenders),
                expected_value="BRAIN hard gates use canonical thresholds without local factors",
                deviation="本地环境因子会改变 LOW_SHARPE/LOW_FITNESS 阈值",
                fix_guidance="保留 regime 元数据用于归因，但不要乘到 BRAIN 官方硬门槛上",
            ))
        else:
            report.add_pass()
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="阈值零偏差",
            file_path="brain_alpha_ops/research/scoring.py",
            check_name="无法验证硬门槛未被本地因子调整",
            error=exc, expected="可检查 empirical_score 硬门槛实现",
            fix_guidance="修复评分模块导入或源码检查错误。",
        )
