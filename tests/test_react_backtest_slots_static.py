from __future__ import annotations

from pathlib import Path

from _react_source_utils import resolve_react_source


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
TYPES = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "types"
UTILS = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "utils"


def _source(path: Path) -> str:
    return resolve_react_source(path)


def test_official_backtest_slots_expose_readonly_queue_summary():
    source = _source(SLOTS)
    types = _source(TYPES)
    utils = _source(UTILS)

    assert "queue_summary?: BacktestQueueSummary;" in types
    assert "status_board?: BacktestStatusBoard;" in types
    assert "export interface BacktestStatusBoard" in types
    assert "export interface BacktestQueueSummary" in types
    assert "official_slot_record_count?: number;" in types
    # Phase 15 refactor: api.data → slotsGlobal.data (useGlobalData hook)
    assert "const queueSummary = slotsGlobal.data?.queue_summary;" in source
    assert "const slotLimit = backtestSlotLimit(slotsGlobal.data);" in source
    # BacktestQueueSummaryStrip is multi-line after Prettier; check parts.
    assert "BacktestQueueSummaryStrip" in source
    assert "summary={queueSummary}" in source
    assert "activeCount={activeCount}" in source
    assert "slotLimit={slotLimit}" in source
    assert "Array.from({ length: backtestSlotLimit(payload) }" in source
    assert '<QueueMetric label="可用槽位" value={`${openSlots}/${slotLimit}`} />' in source
    # QueueMetric for 提交证据缺口 is multi-line; check parts.
    assert 'label="提交证据缺口"' in source
    assert "formatCount(summary?.submit_evidence_blocking_count)" in source
    assert "<QueueMetric label=\"官方接口\" value={summary?.official_api_called ? '已调用' : '未调用'} />" in source
    assert '<QueueMetric label="槽位记录" value={formatCount(summary?.official_slot_record_count)} />' in source
    assert "const board = slot.status_board;" in source
    assert '<SlotMetric label="任务序号" value={formatCount(board?.task_index ?? slot.slot)} />' in source
    # SlotMetric for Alpha 标识 is multi-line; check parts.
    assert 'label="Alpha 标识"' in source
    assert "board?.alpha_id || slot.alpha_id || '-'" in source
    assert '<SlotMetric label="已提交任务" value={formatCount(board?.submitted_count)} />' in source
    assert '<SlotMetric label="成功回测" value={formatCount(board?.completed_count)} />' in source
    assert '<SlotMetric label="回测失败" value={formatCount(board?.failed_count)} />' in source
    assert '<SlotMetric label="达标数" value={formatCount(board?.passed_count)} />' in source
    assert '<SlotMetric label="不达标数" value={formatCount(board?.not_passed_count)} />' in source
    assert '<SlotMetric label="达标率" value={formatRate(board?.pass_rate)} />' in source
    assert '<SlotMetric label="操作进度" value={`${boundedPercent(slot.progress_percent)}%`} />' in source
    assert "backtestActiveCount(slotsGlobal.data)" in source
    assert "'CAPACITY_WAIT'" in utils
    assert "ACTIVE_BACKTEST_SLOT_STATUSES.has(text)" in utils
    assert "if (text === 'CAPACITY_WAIT') return '等待容量';" in source
    assert "if (text === 'POLL_TIMEOUT') return '轮询超时';" in source
    assert "官方工作阻断: {reviewBlockers || '暂无'}" in source
    assert "提交证据阻断: {submitBlockers || '暂无'}" in source
    assert "if (text === 'trusted_environment_official_simulation_required') return '官方复核';" in source
