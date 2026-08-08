from __future__ import annotations

from pathlib import Path

from _react_source_utils import resolve_react_source


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
COMPONENT = SRC / "components" / "QualityCheckPanel.tsx"


def _source(path: Path) -> str:
    return resolve_react_source(path)


def test_app_routes_quality_check_to_dedicated_panel():
    app = "\n".join([
        _source(SRC / "App.tsx"),
        _source(SRC / "components" / "views" / "renderView.tsx"),
    ])

    assert "lazy(() => import('@/components/QualityCheckPanel'))" in app
    assert "case 'quality_check':" in app
    assert "<SafeQualityCheckPanel notify={notify} />" in app


def test_quality_check_panel_reads_all_gate_snapshots():
    source = _source(COMPONENT)
    candidates = _source(SRC / "components" / "CandidateTable.tsx")
    global_data = _source(SRC / "hooks" / "useGlobalData.ts")

    assert '"/api/candidates?limit=1000"' not in source
    assert "candidatesApi.call('/api/candidates')" in global_data
    assert "CANDIDATE_FETCH_LIMIT" not in candidates
    assert "slotsApi.call('/api/backtest_slots')" in global_data
    assert "callReadiness<SubmitReadinessResponse>('/api/submit_readiness')" in source
    assert '<CandidateTable' in source
    assert 'viewMode="passed"' in source


def test_quality_check_panel_exposes_gate_summary_fields():
    source = _source(COMPONENT)

    assert '<QualityMetric label="候选" value={String(summary.total)} />' in source
    assert '<QualityMetric label="本地通过" value={String(summary.localValid)} />' in source
    assert '<QualityMetric label="待官方复核" value={String(summary.reviewReady)} />' in source
    assert '<QualityMetric label="官方仿真" value={String(summary.officiallySimulated)} />' in source
    assert '<QualityMetric label="阻断复核候选" value={String(summary.eligible)} />' in source
    assert '<QualityMetric label="官方接口"' in source
    assert "summary.officialApiCalled ? '已调用' : '未调用'" in source
    assert "官方门槛: {summary.thresholdText}" in source
    assert "官方工作阻断: {summary.reviewBlockers || '暂无'}" in source
    assert "候选族阻断: {summary.familyBlockers || '暂无'}" in source
