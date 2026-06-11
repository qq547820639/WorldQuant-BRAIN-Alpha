"""Red Line 6: strong alignment with BRAIN canonical API contracts."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.brain_api.canonical import (
    CANONICAL_API_PATHS,
    CANONICAL_METRIC_NAMES,
    CANONICAL_SETTINGS,
)
from brain_alpha_ops.compliance.redline_helpers import _verification_blocked
from brain_alpha_ops.compliance.redline_models import ComplianceReport, RedLineViolation


def _verify_redline_6_code_alignment(
    report: ComplianceReport,
    run_config: Any | None = None,
) -> None:
    """Red Line 6: 代码强对齐."""
    redline_id = 6
    report.redline_summary[redline_id] = "代码强对齐"

    # 6a. Verify base_url
    try:
        from brain_alpha_ops.config import OfficialAPIConfig
        api_config = getattr(getattr(run_config, "ops", None), "official_api", None) or OfficialAPIConfig()
        if api_config.base_url == "https://api.worldquantbrain.com":
            report.add_pass()
        else:
            report.add(RedLineViolation(
                redline_id=redline_id, redline_name="代码强对齐",
                severity="BLOCKING", file_path="brain_alpha_ops/config.py",
                check_name="base_url 非官方地址",
                actual_value=api_config.base_url,
                expected_value="https://api.worldquantbrain.com",
                deviation="API 基础地址与 BRAIN 官方不一致",
                fix_guidance="OfficialAPIConfig.base_url 必须为 https://api.worldquantbrain.com",
            ))
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="代码强对齐",
            file_path="brain_alpha_ops/config.py",
            check_name="无法验证官方 API base_url",
            error=exc, expected="https://api.worldquantbrain.com",
            fix_guidance="修复 OfficialAPIConfig 或运行配置。",
        )

    # 6b. Verify API paths
    try:
        from brain_alpha_ops.config import OfficialAPIConfig
        api_config = getattr(getattr(run_config, "ops", None), "official_api", None) or OfficialAPIConfig()
        path_map = {
            "authentication": api_config.authentication_path,
            "simulations": api_config.simulations_path,
            "data_categories": api_config.data_categories_path,
            "data_sets": api_config.data_sets_path,
            "data_set_detail": api_config.data_set_path_template,
            "data_fields": api_config.data_fields_path,
            "data_field_detail": api_config.data_field_path_template,
            "operators": api_config.operators_path,
            "user_alphas": api_config.user_alphas_path,
            "user_profile": api_config.user_profile_path,
            "alpha_check": api_config.alpha_check_path_template,
            "alpha_submit": api_config.alpha_submit_path_template,
            "alpha_detail": api_config.alpha_path_template,
            "alpha_correlations": api_config.alpha_correlations_path,
        }
        for key, canonical_path in CANONICAL_API_PATHS.items():
            actual = path_map.get(key)
            if actual is None:
                continue
            if actual != canonical_path:
                report.add(RedLineViolation(
                    redline_id=redline_id, redline_name="代码强对齐",
                    severity="BLOCKING", file_path="brain_alpha_ops/config.py",
                    check_name=f"API 路径偏差: {key}",
                    actual_value=actual, expected_value=canonical_path,
                    deviation=f"路径 '{actual}' 与官方 '{canonical_path}' 不一致",
                    fix_guidance=f"修改 OfficialAPIConfig 中 {key} 路径为 {canonical_path}",
                ))
            else:
                report.add_pass()
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="代码强对齐",
            file_path="brain_alpha_ops/config.py",
            check_name="无法验证官方 API 路径",
            error=exc, expected="API paths match canonical.py",
            fix_guidance="修复 OfficialAPIConfig 或 canonical 映射。",
        )

    # 6c. Verify settings canonical values
    try:
        from brain_alpha_ops.config import BrainSettings
        bs = getattr(getattr(run_config, "ops", None), "settings", None) or BrainSettings()
        for key, allowed in CANONICAL_SETTINGS.items():
            actual = getattr(bs, key, None)
            if actual is not None and actual not in allowed:
                report.add(RedLineViolation(
                    redline_id=redline_id, redline_name="代码强对齐",
                    severity="WARNING", file_path="brain_alpha_ops/config.py",
                    check_name=f"设置值超 BRAIN 允许范围: {key}",
                    actual_value=actual,
                    expected_value=f"{{{', '.join(str(v) for v in list(allowed)[:5])}...}}",
                    deviation=f"{key}={actual} 非 BRAIN 官方允许值",
                    fix_guidance=f"修改 BrainSettings.{key} 为 BRAIN 允许值之一",
                ))
            else:
                report.add_pass()
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="代码强对齐",
            file_path="brain_alpha_ops/config.py",
            check_name="无法验证 BRAIN settings 枚举",
            error=exc, expected="settings values in canonical.py sets",
            fix_guidance="修复 BrainSettings 或运行配置。",
        )

    # 6d. Verify config/web enum validators share the canonical settings.
    try:
        from brain_alpha_ops import config as config_mod
        from brain_alpha_ops import web_config as web_config_mod

        validator_sets = {
            "config.region": (getattr(config_mod, "_VALID_REGIONS", set()), CANONICAL_SETTINGS["region"]),
            "config.universe": (getattr(config_mod, "_VALID_UNIVERSES", set()), CANONICAL_SETTINGS["universe"]),
            "config.delay": (getattr(config_mod, "_VALID_DELAYS", set()), CANONICAL_SETTINGS["delay"]),
            "config.neutralization": (
                getattr(config_mod, "_VALID_NEUTRALIZATIONS", set()),
                CANONICAL_SETTINGS["neutralization"],
            ),
            "config.type": (getattr(config_mod, "_VALID_ALPHA_TYPES", set()), CANONICAL_SETTINGS["type"]),
            "config.unitHandling": (
                getattr(config_mod, "_VALID_UNIT_HANDLING", set()),
                CANONICAL_SETTINGS["unitHandling"],
            ),
            "web.region": (getattr(web_config_mod, "_VALID_REGIONS", set()), CANONICAL_SETTINGS["region"]),
            "web.universe": (getattr(web_config_mod, "_VALID_UNIVERSES", set()), CANONICAL_SETTINGS["universe"]),
            "web.delay": (getattr(web_config_mod, "_VALID_DELAYS", set()), CANONICAL_SETTINGS["delay"]),
            "web.neutralization": (
                getattr(web_config_mod, "_VALID_NEUTRALIZATIONS", set()),
                CANONICAL_SETTINGS["neutralization"],
            ),
            "web.type": (getattr(web_config_mod, "_VALID_TYPES", set()), CANONICAL_SETTINGS["type"]),
        }
        for name, (actual, expected) in validator_sets.items():
            if set(actual) != set(expected):
                report.add(RedLineViolation(
                    redline_id=redline_id, redline_name="代码强对齐",
                    severity="BLOCKING", file_path="brain_alpha_ops/brain_api/canonical.py",
                    check_name=f"canonical enum drift: {name}",
                    actual_value=sorted(actual), expected_value=sorted(expected),
                    deviation="Config/Web enum validators are not aligned with canonical settings.",
                    fix_guidance="Import supported enum sets from brain_alpha_ops.brain_api.canonical.",
                ))
            else:
                report.add_pass()
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="代码强对齐",
            file_path="brain_alpha_ops/brain_api/canonical.py",
            check_name="canonical enum alignment check failed",
            error=exc, expected="alignment check can run",
            fix_guidance="Ensure config.py and web_config.py import canonical enum sets without cycles.",
        )

    # 6e. Verify metric field names in empirical_score
    try:
        from brain_alpha_ops.research.scoring import empirical_score
        import inspect
        source = inspect.getsource(empirical_score)
        for metric_name in CANONICAL_METRIC_NAMES:
            if metric_name in source:
                report.add_pass()
            else:
                report.add(RedLineViolation(
                    redline_id=redline_id, redline_name="代码强对齐",
                    severity="WARNING", file_path="brain_alpha_ops/research/scoring.py",
                    check_name=f"未引用 BRAIN API 指标: {metric_name}",
                    actual_value="未找到", expected_value=f'源码中使用 "{metric_name}"',
                    deviation="可能使用了非标准字段名",
                    fix_guidance=f"确认 empirical_score 使用 BRAIN API 原生字段名 \"{metric_name}\"",
                ))
    except Exception as exc:
        _verification_blocked(
            report, redline_id=redline_id, redline_name="代码强对齐",
            file_path="brain_alpha_ops/research/scoring.py",
            check_name="无法验证 BRAIN API 指标字段名",
            error=exc, expected="empirical_score 可检查 canonical metric names",
            fix_guidance="修复评分模块导入或指标命名。",
        )
