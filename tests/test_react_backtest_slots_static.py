from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SLOTS = (
    ROOT
    / "brain_alpha_ops"
    / "web"
    / "react_app"
    / "src"
    / "components"
    / "OfficialBacktestSlots.tsx"
)
TYPES = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "types" / "index.ts"
UTILS = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "utils" / "backtestSlots.ts"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_official_backtest_slots_expose_readonly_queue_summary():
    source = _source(SLOTS)
    types = _source(TYPES)
    utils = _source(UTILS)

    assert "queue_summary?: BacktestQueueSummary;" in types
    assert "status_board?: BacktestStatusBoard;" in types
    assert "export interface BacktestStatusBoard" in types
    assert "export interface BacktestQueueSummary" in types
    assert "official_slot_record_count?: number;" in types
    assert "const queueSummary = api.data?.queue_summary;" in source
    assert "const slotLimit = backtestSlotLimit(api.data);" in source
    assert "<BacktestQueueSummaryStrip summary={queueSummary} activeCount={activeCount} slotLimit={slotLimit} />" in source
    assert "Array.from({ length: backtestSlotLimit(payload) }" in source
    assert '<QueueMetric label="可用槽位" value={`${openSlots}/${slotLimit}`} />' in source
    assert '<QueueMetric label="提交证据缺口" value={formatCount(summary?.submit_evidence_blocking_count)} />' in source
    assert '<QueueMetric label="官方接口" value={summary?.official_api_called ? "已调用" : "未调用"} />' in source
    assert '<QueueMetric label="槽位记录" value={formatCount(summary?.official_slot_record_count)} />' in source
    assert "const board = slot.status_board;" in source
    assert '<SlotMetric label="任务序号" value={formatCount(board?.task_index ?? slot.slot)} />' in source
    assert '<SlotMetric label="Alpha 标识" value={board?.alpha_id || slot.alpha_id || "-"} mono />' in source
    assert '<SlotMetric label="已提交任务" value={formatCount(board?.submitted_count)} />' in source
    assert '<SlotMetric label="成功回测" value={formatCount(board?.completed_count)} />' in source
    assert '<SlotMetric label="回测失败" value={formatCount(board?.failed_count)} />' in source
    assert '<SlotMetric label="达标数" value={formatCount(board?.passed_count)} />' in source
    assert '<SlotMetric label="不达标数" value={formatCount(board?.not_passed_count)} />' in source
    assert '<SlotMetric label="达标率" value={formatRate(board?.pass_rate)} />' in source
    assert '<SlotMetric label="操作进度" value={`${boundedPercent(slot.progress_percent)}%`} />' in source
    assert "backtestActiveCount(api.data)" in source
    assert '"CAPACITY_WAIT"' in utils
    assert "ACTIVE_BACKTEST_SLOT_STATUSES.has(text)" in utils
    assert 'if (text === "CAPACITY_WAIT") return "等待容量";' in source
    assert 'if (text === "POLL_TIMEOUT") return "轮询超时";' in source
    assert "官方工作阻断: {reviewBlockers || \"暂无\"}" in source
    assert "提交证据阻断: {submitBlockers || \"暂无\"}" in source
    assert 'if (text === "trusted_environment_official_simulation_required") return "官方复核";' in source
