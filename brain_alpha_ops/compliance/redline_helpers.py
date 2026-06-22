"""Shared helpers for technical red-line verification."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from brain_alpha_ops.compliance.redline_models import ComplianceReport, RedLineViolation
from brain_alpha_ops.redaction import redact_error_message, redact_text

logger = logging.getLogger("brain_alpha_ops.compliance.redline_verifier")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _runtime_storage_dir(run_config: Any | None) -> Path:
    storage_dir = getattr(getattr(run_config, "ops", None), "storage_dir", "data")
    target = Path(str(storage_dir or "data"))
    if not target.is_absolute():
        target = _project_root() / target
    return target.resolve()


def _verification_blocked(
    report: ComplianceReport,
    *,
    redline_id: int,
    redline_name: str,
    file_path: str,
    check_name: str,
    error: Any,
    expected: str,
    fix_guidance: str,
) -> None:
    message = redact_error_message(error)
    logger.warning(
        "redline verification blocked: redline_id=%s check=%s file=%s error=%s",
        redline_id,
        check_name,
        redact_text(file_path, max_length=180),
        message,
    )
    report.add(RedLineViolation(
        redline_id=redline_id,
        redline_name=redline_name,
        severity="BLOCKING",
        file_path=file_path,
        check_name=check_name,
        actual_value=message[:300],
        expected_value=expected,
        deviation="关键红线证据无法验证，按失败关闭处理",
        fix_guidance=fix_guidance,
    ))


def _verify_generator_templates_against_official_context(data_dir: Path) -> dict[str, Any]:
    """Render generator fallback templates and compare tokens to official context."""
    try:
        from brain_alpha_ops.data import OfficialDataLoader

        loader = OfficialDataLoader()
        loader.load_all(data_dir)
        official_fields = {
            str(getattr(field, "id", "") or "").lower()
            for field in loader.get_fields()
            if str(getattr(field, "id", "") or "")
        }
        official_operators = {
            str(getattr(operator, "name", "") or "").lower()
            for operator in loader.get_operators()
            if str(getattr(operator, "name", "") or "")
        }
    except Exception as exc:
        message = redact_error_message(exc)
        logger.warning(
            "redline verifier official context unavailable for generator template validation: %s",
            message,
        )
        return {"ok": False, "reason": f"official context unavailable: {message}"}

    templates = _candidate_generator_fallback_templates()
    if not official_fields or not official_operators:
        return {
            "ok": False,
            "reason": "official field/operator context is empty",
            "template_count": len(templates),
            "field_count": len(official_fields),
            "operator_count": len(official_operators),
        }
    if not templates:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no fallback templates are emitted by CandidateGenerator",
            "template_count": 0,
        }

    sample_fields = _sample_official_fields_for_templates(official_fields)
    missing_fields: dict[str, list[str]] = {}
    missing_operators: dict[str, list[str]] = {}
    rendered = []
    allowed_literals = {"nan", "inf", "std"}
    for template in templates:
        expr = (
            template
            .replace("{f1}", sample_fields["f1"])
            .replace("{f2}", sample_fields["f2"])
            .replace("{w}", "20")
        )
        rendered.append(expr)
        operators = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", expr.lower()))
        tokens = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", expr.lower()))
        field_like = tokens - operators - allowed_literals
        unknown_ops = sorted(op for op in operators if op not in official_operators)
        unknown_fields = sorted(token for token in field_like if token not in official_fields)
        if unknown_ops:
            missing_operators[template] = unknown_ops
        if unknown_fields:
            missing_fields[template] = unknown_fields

    return {
        "ok": not missing_fields and not missing_operators,
        "template_count": len(templates),
        "rendered_sample_count": len(rendered),
        "sample_fields": sample_fields,
        "missing_fields": missing_fields,
        "missing_operators": missing_operators,
    }


def _candidate_generator_fallback_templates() -> list[str]:
    """Return fallback expression templates used by CandidateGenerator.

    Delegates to generator._load_fallback_templates() -- the same source
    used at runtime -- instead of AST-parsing the source code (which
    broke when templates moved from inline constants to templates.yaml).
    """
    try:
        from brain_alpha_ops.research.generator import _load_fallback_templates

        templates, _families = _load_fallback_templates()
        return list(templates)
    except Exception as exc:
        logger.warning(
            "redline verifier failed to extract generator fallback templates: %s",
            redact_error_message(exc),
        )
        return []


def _sample_official_fields_for_templates(official_fields: set[str]) -> dict[str, str]:
    preferred_1 = ["close", "returns", "vwap", "volume"]
    preferred_2 = ["volume", "adv20", "returns", "open"]

    def choose(preferred: list[str], fallback_exclude: set[str] | None = None) -> str:
        fallback_exclude = fallback_exclude or set()
        for field in preferred:
            if field in official_fields and field not in fallback_exclude:
                return field
        for field in sorted(official_fields):
            if field not in fallback_exclude:
                return field
        return sorted(official_fields)[0] if official_fields else ""

    f1 = choose(preferred_1)
    f2 = choose(preferred_2, {f1}) or f1
    return {"f1": f1, "f2": f2}
