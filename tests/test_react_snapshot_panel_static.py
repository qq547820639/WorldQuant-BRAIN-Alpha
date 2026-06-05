from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PANEL = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "components" / "SnapshotPanel.tsx"


def test_snapshot_panel_declares_all_data_views_and_endpoints():
    source = SNAPSHOT_PANEL.read_text(encoding="utf-8")

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
        '/api/snapshot/cloud?limit=100',
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
    assert 'role="alert"' in source
    assert 'aria-live="assertive"' in source
    assert 'onNavigate?: (view: CardViewId) => void;' in source
    assert '检测到可续跑断点' in source
    assert '进入候选管理' in source
    assert '查看质量门禁' in source
    assert 'function SnapshotMobileCard' in source
    assert 'rows: checkpointStatusRows' in source
    assert 'metrics: checkpointStatusMetrics' in source
    assert 'function checkpointStatusRows(payload: SnapshotPayload)' in source
    assert 'function comparisonRows(comparison: SnapshotPayload)' in source
    assert 'function analyticsRows(analytics: SnapshotPayload)' in source
