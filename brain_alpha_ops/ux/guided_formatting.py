"""Formatting helpers for the guided pipeline UX."""

from __future__ import annotations

import logging
from typing import Dict

from brain_alpha_ops.error_knowledge import classify_ux_error as _unified_classify
from brain_alpha_ops.models import Candidate, PipelineEvent
from brain_alpha_ops.redaction import redact_error_message


logger = logging.getLogger(__name__)


def classify_error(error: Exception) -> Dict[str, str]:
    """Classify an error and return actionable guidance."""
    try:
        info = _unified_classify(error)
        return {
            "type": info.error_code or type(error).__name__,
            "message": redact_error_message(error, max_length=200),
            "fix": info.fix_hint or "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
            "retry": "yes" if info.retryable else ("maybe" if info.retryable is None else "no"),
        }
    except Exception:
        logger.warning("guided pipeline error classification fallback failed", exc_info=True)
        return {
            "type": type(error).__name__,
            "message": redact_error_message(error, max_length=200),
            "fix": "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
            "retry": "maybe",
        }


def format_error_for_user(error: Exception) -> str:
    """Format an exception into a user-friendly, actionable message."""
    info = classify_error(error)
    lines = [
        f"\n  [W] 错误类型: {info['type']}",
        f"  错误信息: {info['message']}",
        f"  修复建议: {info['fix']}",
    ]
    if info["retry"] == "yes":
        lines.append("  可重试: 是 - 系统将自动重试")
    elif info["retry"] == "maybe":
        lines.append("  可重试: 不确定 - 请根据上述建议排查后重试")
    else:
        lines.append("  可重试: 否 - 请先修复问题后重新运行")
    return "\n".join(lines)


def format_candidate_summary(candidate: Candidate) -> str:
    """Format a single candidate as a readable summary."""
    sc = candidate.scorecard or {}
    gate = candidate.gate or {}
    lines = [
        f"  Alpha: {candidate.alpha_id}",
        f"  表达式: {candidate.expression[:80]}{'...' if len(candidate.expression) > 80 else ''}",
        f"  因子族: {candidate.family or 'N/A'}",
        f"  总分: {sc.get('total_score', 'N/A')} ({sc.get('decision_band', 'N/A')})",
        f"  Gate: {'PASS' if gate.get('submission_ready') else 'FAIL'}",
    ]
    if gate.get("failed_reasons"):
        lines.append("  失败原因:")
        for reason in gate["failed_reasons"][:3]:
            lines.append(f"    - {reason}")
    return "\n".join(lines)


def format_pipeline_progress(event: PipelineEvent) -> str:
    """Format a pipeline event for live display."""
    timestamp = event.timestamp[:19] if event.timestamp else ""
    level_icon = {"INFO": "[i]", "WARNING": "[W]", "ERROR": "[E]", "SUCCESS": "[+]"}.get(event.level, "[.]")
    return f"  [{timestamp}] {level_icon} {event.event}: {event.message}"
