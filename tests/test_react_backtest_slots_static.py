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


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_official_backtest_slots_expose_readonly_queue_summary():
    source = _source(SLOTS)
    types = _source(TYPES)

    assert "queue_summary?: BacktestQueueSummary;" in types
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
    assert "官方工作阻断: {reviewBlockers || \"暂无\"}" in source
    assert "提交证据阻断: {submitBlockers || \"暂无\"}" in source
    assert 'if (text === "trusted_environment_official_simulation_required") return "官方复核";' in source
