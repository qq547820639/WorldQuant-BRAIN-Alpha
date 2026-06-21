"""Message catalog for BRAIN Alpha Ops i18n (Phase 4.1).

Keys use dot-delimited convention: ``<domain>.<category>.<specific>``.
Chinese is the primary language ("zh"); English translations are optional.
"""
from __future__ import annotations

_MESSAGES: dict[str, dict[str, str]] = {
    # ── Submission preflight ──────────────────────────────────────────
    "submission.blocked.missing_id": {
        "zh": "缺少官方 Alpha ID，请先完成官方回测。",
    },
    "submission.blocked.not_ready": {
        "zh": "该 Alpha 尚未达到可提交状态，请先在达标列表完成检查。",
    },
    "submission.blocked.failed": {
        "zh": "该 Alpha 已标记为失败或不达标，不能提交。",
    },
    "submission.blocked.duplicate_id": {
        "zh": "本地提交记录中已存在该官方 Alpha ID。",
    },
    "submission.blocked.duplicate_expr": {
        "zh": "本地提交记录中已存在相同表达式。",
    },
    "submission.blocked.sync_required": {
        "zh": "提交前请先同步云端数据。",
    },
    "submission.blocked.sync_stale": {
        "zh": "云端数据已超过 24 小时未刷新，请先同步云端数据。",
    },
    "submission.blocked.already_submitted": {
        "zh": "云端缓存显示该 Alpha 已提交。",
    },

    # ── Pipeline events ───────────────────────────────────────────────
    "pipeline.event.started": {
        "zh": "Research pipeline started.",
    },
    "pipeline.event.completed": {
        "zh": "Research pipeline completed.",
    },
    "pipeline.event.timeout": {
        "zh": "Pipeline max runtime exceeded.",
    },
    "pipeline.progress.startup": {
        "zh": "准备认证并加载官方字段/算子上下文。",
    },
    "pipeline.progress.stopped": {
        "zh": "用户已停止连续生产队列。",
    },
    "pipeline.progress.completed": {
        "zh": "生产、评价、排序和回测等待流程完成。",
    },
    "pipeline.progress.cycle": {
        "zh": "第 {cycle} 轮：生产 {generated} 个 Alpha，进入本地评分与排序。",
    },
    "pipeline.progress.cycle_done": {
        "zh": "第 {cycle} 轮完成，继续生产、评价和排序。",
    },
    "pipeline.progress.candidate_pool": {
        "zh": "候选池已按本地分排序，保留 {kept}/{total} 个 Alpha。",
    },

    # ── State contract messages ───────────────────────────────────────
    "state.job.running": {
        "zh": "任务进行中",
    },
    "state.job.completed": {
        "zh": "任务完成",
    },
    "state.job.failed": {
        "zh": "任务失败",
    },
    "state.job.stopped": {
        "zh": "任务已停止",
    },
    "state.job.cancelled": {
        "zh": "任务已取消",
    },
    "state.job.not_found": {
        "zh": "未找到任务",
    },
    "state.phase.pending": {
        "zh": "待解锁",
    },
    "state.phase.active": {
        "zh": "进行中",
    },
    "state.phase.complete": {
        "zh": "已完成",
    },
    "state.phase.blocked": {
        "zh": "已阻断",
    },
    "state.sync.in_progress": {
        "zh": "同步进行中",
    },
    "state.sync.done": {
        "zh": "同步完成",
    },
    "state.sync.stalled": {
        "zh": "同步停滞",
    },
    "state.error.unknown": {
        "zh": "未知错误",
    },
    "state.error.validation": {
        "zh": "数据验证失败",
    },
    "state.error.config": {
        "zh": "配置错误",
    },
    "state.error.auth": {
        "zh": "认证失败",
    },
}
