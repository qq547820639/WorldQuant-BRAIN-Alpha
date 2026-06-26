"""String-form submission preflight error message.

Extracted from the former ``web_submission_safety.py`` monolith
(deep-optimization-phase13).
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.safety import SubmissionLedger
from brain_alpha_ops.web_candidates.selection import official_alpha_id

from ._blocks import CloudAlphaSnapshot, CloudStatusFor, LedgerFactory


def submission_preflight_error_message(
    candidate: dict[str, Any],
    run_config: RunConfig,
    *,
    ledger_factory: LedgerFactory = SubmissionLedger,
    cloud_alpha_snapshot: CloudAlphaSnapshot,
    cloud_status_for: CloudStatusFor,
) -> str:
    official_id = official_alpha_id(candidate)
    if not official_id:
        return "缺少官方 Alpha ID，请先完成官方回测。"
    gate = candidate.get("gate") or {}
    if not (gate.get("submission_ready") or candidate.get("lifecycle_status") == "submission_ready"):
        return "该 Alpha 尚未达到可提交状态，请先在达标列表完成检查。"
    status_text = f"{candidate.get('lifecycle_status', '')} {gate.get('status', '')}".lower()
    if any(word in status_text for word in ("failed", "rejected", "不达标")):
        return "该 Alpha 已标记为失败或不达标，不能提交。"

    records = ledger_factory(run_config.ops.storage_dir).records()
    candidate_expr_key = expression_key(str(candidate.get("expression", "")))
    duplicate_id = any(str(row.get("official_alpha_id") or "") == official_id for row in records)
    duplicate_expr = bool(candidate_expr_key) and any(expression_key(str(row.get("expression", ""))) == candidate_expr_key for row in records)
    if duplicate_id:
        return "本地提交记录中已存在该官方 Alpha ID。"
    if duplicate_expr:
        return "本地提交记录中已存在相同表达式。"

    cloud_snapshot = cloud_alpha_snapshot()
    cloud_rows = cloud_snapshot.get("alphas") or []
    cloud_summary = cloud_snapshot.get("summary") or {}
    if not cloud_rows:
        return "提交前请先同步云端数据。"
    if cloud_summary.get("is_stale"):
        return "云端数据已超过 24 小时未刷新，请先同步云端数据。"

    cloud_status = cloud_status_for(candidate, cloud_rows)
    if str(cloud_status.get("status", "")).upper() in {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}:
        return "云端缓存显示该 Alpha 已提交。"
    return ""


# P3-1: removed the legacy alias ``submission_preflight_error`` (now only
# the canonical ``submission_preflight_error_message`` is exported).  All
# in-tree callers were updated to the canonical name.
