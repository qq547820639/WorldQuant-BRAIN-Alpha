from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PANEL = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "components" / "SnapshotPanel.tsx"
SNAPSHOT_MODULES = [
    SNAPSHOT_PANEL,
    SNAPSHOT_PANEL.parent / "SnapshotPanel" / "utils.ts",
    SNAPSHOT_PANEL.parent / "SnapshotPanel" / "SnapshotPanelCloud.tsx",
    SNAPSHOT_PANEL.parent / "SnapshotPanel" / "SnapshotPanelLocal.tsx",
    SNAPSHOT_PANEL.parent / "SnapshotPanel" / "SnapshotPanelCompare.tsx",
]


def test_snapshot_panel_declares_all_data_views_and_endpoints():
    source = "\n".join(path.read_text(encoding="utf-8") for path in SNAPSHOT_MODULES)

    assert 'export type SnapshotView =' in source
    assert '| "cloud"' in source
    assert '| "checkpoint_status"' in source
    assert '| "lifecycle"' in source
    assert '| "research_memory"' in source
    assert '| "research_knowledge"' in source
    assert '| "research_observability"' in source
    assert '| "prompt_runs"' in source
    assert '| "sqlite_indexes"' in source
    assert '| "robustness"' in source
    for endpoint in (
        '/api/snapshot/cloud',
        '/api/checkpoint_status',
        '/api/lifecycle',
        '/api/research_memory?limit=5000&top_n=10',
        '/api/research_knowledge?limit=100&min_confidence=0',
        '/api/research_observability?limit=5000&top_n=10&include_cloud=true',
        '/api/prompt_runs?limit=100',
        '/api/sqlite_indexes?top_n=10',
        '/api/latest_result',
    ):
        assert endpoint in source
    assert 'aria-label={`筛选 ${config.title}`}' in source
    assert 'aria-label={`${config.title}表格`}' in source
    assert 'aria-label={`${config.title}移动列表`}' in source
    assert 'subtitle: "完整缓存的 Alpha 状态"' in source
    assert 'role="alert"' in source
    assert 'aria-live="assertive"' in source
    assert 'onNavigate?: (view: CardViewId) => void;' in source
    assert '检测到可继续的上次进度' in source
    assert '进入候选管理' in source
    assert '查看质量门禁' in source
    assert 'function SnapshotMobileCard' in source
    assert '"返回数量"' not in source
    assert 'rows: checkpointStatusRows' in source
    assert 'metrics: checkpointStatusMetrics' in source
    assert 'function checkpointStatusRows(payload: SnapshotPayload)' in source
    assert 'function comparisonRows(comparison: SnapshotPayload)' in source
    assert 'function analyticsRows(analytics: SnapshotPayload)' in source
    assert '{ label: "缓存总数", value: text((summary.total ?? summary.count ?? summary.total_count ?? "-") as string) }' in source
    assert '{ label: "载入状态", value: cloudLoadStatus(summary) }' in source
    assert 'return "完整载入";' in source
