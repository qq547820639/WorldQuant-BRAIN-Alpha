"""Red Line 4: full parameter traceability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.compliance.redline_helpers import (
    _project_root,
    _verification_blocked,
)
from brain_alpha_ops.compliance.redline_models import ComplianceReport, RedLineViolation

_MAX_CONFIG_READ_BYTES = 1 * 1024 * 1024  # 1 MiB limit for config file reads


def _verify_redline_4_parameter_traceability(
    report: ComplianceReport,
    run_config: Any | None = None,
) -> None:
    """Red Line 4: 参数全链路可溯."""
    redline_id = 4
    report.redline_summary[redline_id] = "参数全链路可溯"

    # 4a. Verify build_scorecard accepts ScoringParams and BRAIN settings trace.
    try:
        import inspect

        from brain_alpha_ops.research.scoring import build_scorecard
        sig = inspect.signature(build_scorecard)
        if "params" in sig.parameters and "settings" in sig.parameters:
            report.add_pass()
        else:
            report.add(RedLineViolation(
                redline_id=redline_id, redline_name="参数全链路可溯",
                severity="WARNING", file_path="brain_alpha_ops/research/scoring.py",
                check_name="build_scorecard 缺少参数溯源入口",
                actual_value=f"parameters={list(sig.parameters)}",
                expected_value="params + settings",
                deviation="评分函数不能完整追溯校准参数与 BRAIN settings",
                fix_guidance="确保 build_scorecard 接受 params 与 settings 参数",
            ))
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="参数全链路可溯",
            file_path="brain_alpha_ops/research/scoring.py",
            check_name="无法验证评分溯源入口",
            error=exc, expected="build_scorecard 接受 params 与 settings",
            fix_guidance="修复评分模块导入或函数签名。",
        )

    # 4b. Verify ScoringConfig tracks market_regime
    try:
        from brain_alpha_ops.config import ScoringConfig
        sc = ScoringConfig()
        if hasattr(sc, 'market_regime') and hasattr(sc, 'prior_weights_override'):
            report.add_pass()
        else:
            report.add(RedLineViolation(
                redline_id=redline_id, redline_name="参数全链路可溯",
                severity="WARNING", file_path="brain_alpha_ops/config.py",
                check_name="ScoringConfig 缺少溯源字段",
                actual_value=f"market_regime={'✓' if hasattr(sc, 'market_regime') else '✗'}",
                expected_value="market_regime + prior_weights_override",
                deviation="评分配置缺少溯源维度",
                fix_guidance="确保 ScoringConfig 包含市场环境和权重覆盖字段",
            ))
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="参数全链路可溯",
            file_path="brain_alpha_ops/config.py", check_name="无法验证 ScoringConfig 溯源字段",
            error=exc, expected="ScoringConfig 包含溯源字段",
            fix_guidance="修复配置模块导入错误。",
        )

    # 4c. Verify PipelineResult has traceability fields
    try:
        from brain_alpha_ops.models import PipelineResult
        fields_set = {f.name for f in PipelineResult.__dataclass_fields__.values()}
        has_events = "events" in fields_set
        has_summary = "summary" in fields_set
        has_id = "run_id" in fields_set
        if has_events and has_summary and has_id:
            report.add_pass()
        else:
            report.add(RedLineViolation(
                redline_id=redline_id, redline_name="参数全链路可溯",
                severity="WARNING", file_path="brain_alpha_ops/models.py",
                check_name="PipelineResult 审计字段不完整",
                actual_value=f"events={'✓' if has_events else '✗'} summary={'✓' if has_summary else '✗'}",
                expected_value="events + summary + run_id",
                deviation="无法完整追溯运行参数",
                fix_guidance="确保 PipelineResult 包含完整审计字段",
            ))
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="参数全链路可溯",
            file_path="brain_alpha_ops/models.py", check_name="无法验证 PipelineResult 审计字段",
            error=exc, expected="PipelineResult 包含 events、summary 与 run_id",
            fix_guidance="修复模型模块导入错误。",
        )

    # 4d. Verify config file has version tag
    config_path = _project_root() / "config" / "run_config.json"
    if config_path.exists():
        try:
            file_size = config_path.stat().st_size
            if file_size > _MAX_CONFIG_READ_BYTES:
                report.add(RedLineViolation(
                    redline_id=redline_id, redline_name="参数全链路可溯",
                    severity="WARNING", file_path=str(config_path),
                    check_name="配置文件超过读取大小限制",
                    actual_value=f"{file_size} bytes",
                    expected_value=f"<= {_MAX_CONFIG_READ_BYTES} bytes",
                    deviation="配置文件过大，可能存在异常",
                    fix_guidance="检查 run_config.json 是否包含异常数据",
                ))
            else:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                if "schema_version" in data or "config_version" in data:
                    report.add_pass()
                else:
                    report.add(RedLineViolation(
                        redline_id=redline_id, redline_name="参数全链路可溯",
                        severity="WARNING", file_path=str(config_path),
                        check_name="配置文件缺少版本号",
                        actual_value="无版本字段", expected_value="schema_version",
                        deviation="配置版本不可追溯",
                        fix_guidance="在 run_config.json 添加 \"schema_version\": \"v2.0\"",
                    ))
        except Exception as exc:
            _verification_blocked(
                report, redline_id=redline_id, redline_name="参数全链路可溯",
                file_path=str(config_path), check_name="配置版本证据无法读取",
                error=exc, expected="可解析的 schema_version",
                fix_guidance="修复 config/run_config.json 格式。",
            )

    # 4e. Validate the parameter snapshot for the exact configuration being executed.
    if run_config is not None:
        try:
            from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot

            audit = build_parameter_audit_snapshot(run_config, source="redline_verifier")
            if audit.get("ok") and audit.get("thresholds_zero_deviation"):
                report.add_pass()
            else:
                report.add(RedLineViolation(
                    redline_id=redline_id,
                    redline_name="参数全链路可溯",
                    severity="BLOCKING",
                    file_path="runtime.ops",
                    check_name="运行参数审计未通过",
                    actual_value=audit.get("findings", []),
                    expected_value="complete parameter snapshot with canonical thresholds",
                    deviation="实际运行参数与溯源记录不完整或存在偏差",
                    fix_guidance="使用 canonical 参数重新加载配置并复核审计快照。",
                ))
        except Exception as exc:
            _verification_blocked(
                report, redline_id=redline_id, redline_name="参数全链路可溯",
                file_path="brain_alpha_ops/parameter_audit.py",
                check_name="运行参数审计不可执行",
                error=exc, expected="可生成 runtime parameter audit snapshot",
                fix_guidance="修复参数审计模块后再运行生产流程。",
            )
    # NOTE: individual sub-checks (4a-4d) each add their own pass when
    # successful.  This is intentional — we report granular results.  No
    # blanket pass is added here to avoid inflating the pass count.
