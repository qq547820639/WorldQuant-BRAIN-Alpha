"""Progress presentation helpers for the local web console."""

from __future__ import annotations


PHASE_LABELS: dict[str, str] = {
    "queued": "排队",
    "auth": "认证",
    "scan": "扫描",
    "merge": "合并",
    "startup": "启动",
    "cloud_sync": "云端数据同步",
    "context": "加载上下文",
    "production_loop": "循环生产",
    "local_scoring": "本地评分排序",
    "candidate_pool": "候选池维护",
    "official_validation": "回测前预检",
    "official_simulation": "官方模拟回测",
    "official_deferred": "官方延迟",
    "checking": "批量检查",
    "submitting": "提交",
    "completed": "已完成",
    "stopped": "已停止",
    "failed": "失败",
    "stopping": "正在停止",
    "context_fields": "更新字段缓存",
    "context_operators": "更新算子缓存",
}


def enrich_progress(progress: dict) -> dict:
    if "phase" in progress and "phase_label" not in progress:
        progress["phase_label"] = PHASE_LABELS.get(str(progress["phase"]), str(progress["phase"]))
    return progress
