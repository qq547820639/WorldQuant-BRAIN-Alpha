from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"
COMPONENT = SRC / "components" / "QualityCheckPanel.tsx"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_app_routes_quality_check_to_dedicated_panel():
    app = _source(SRC / "App.tsx")

    assert 'import QualityCheckPanel from "@/components/QualityCheckPanel";' in app
    assert 'detailContent = <QualityCheckPanel notify={notify} />;' in app
    assert 'key="quality_check"' not in app


def test_quality_check_panel_reads_all_gate_snapshots():
    source = _source(COMPONENT)

    assert 'callCandidates<{ candidates?: Candidate[]; items?: Candidate[]; total?: number }>("/api/candidates?limit=1000")' in source
    assert 'callSlots<BacktestSlotsResponse>("/api/backtest_slots")' in source
    assert 'callReadiness<SubmitReadinessResponse>("/api/submit_readiness")' in source
    assert '<CandidateTable' in source
    assert 'viewMode="passed"' in source


def test_quality_check_panel_exposes_gate_summary_fields():
    source = _source(COMPONENT)

    assert '<QualityMetric label="Candidates" value={String(summary.total)} />' in source
    assert '<QualityMetric label="Local valid" value={String(summary.localValid)} />' in source
    assert '<QualityMetric label="Review ready" value={String(summary.reviewReady)} />' in source
    assert '<QualityMetric label="Official sim" value={String(summary.officiallySimulated)} />' in source
    assert '<QualityMetric label="Eligible" value={String(summary.eligible)} />' in source
    assert '<QualityMetric label="Live API" value={summary.officialApiCalled ? "called" : "not called"} />' in source
    assert "Thresholds: {summary.thresholdText}" in source
    assert "Blocking: {summary.blockers || \"none\"}" in source
    assert "Family blockers: {summary.familyBlockers || \"none\"}" in source
