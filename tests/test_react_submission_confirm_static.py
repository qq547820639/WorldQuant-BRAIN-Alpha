from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "components"
TYPES = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "types" / "index.ts"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_submit_readiness_contract_is_typed_for_react():
    types = _source(TYPES)

    assert "export interface SubmitReadinessResponse" in types
    assert "official_api_called?: boolean;" in types
    assert "ready_to_submit?: boolean;" in types
    assert "job_family_candidate_count?: number;" in types
    assert "top_blocking_reasons?: ReadinessReasonCount[];" in types
    assert "production_gaps?: SubmitReadinessFinding[];" in types
    assert "required_next_steps?: string[];" in types


def test_state_cards_use_submit_readiness_for_submit_count():
    source = _source(COMPONENTS / "StateCards.tsx")

    assert 'const readinessApi = useApi<SubmitReadinessResponse>();' in source
    assert 'void readinessApi.call("/api/submit_readiness");' in source
    assert "const submitCount = readinessApi.data?.eligible_count ?? 0;" in source
    assert "const slotLimit = backtestSlotLimit(slotsApi.data);" in source
    assert 'official_backtests: `${activeSlots}/${slotLimit}`,' in source
    assert "Array.from({ length: backtestSlotLimit(payload) }" in source
    assert 'caption: "可提交 Alpha",' in source


def test_submission_confirm_panel_exposes_readiness_summary():
    source = _source(COMPONENTS / "SubmissionConfirmPanel.tsx")

    assert 'const readinessApi = useApi<SubmitReadinessResponse>();' in source
    assert 'callReadiness<SubmitReadinessResponse>("/api/submit_readiness")' in source
    assert "<ReadinessSummary readiness={readiness} />" in source
    assert '<ReadinessMetric label="Ready" value={readiness?.ready_to_submit ? "yes" : "no"}' in source
    assert '<ReadinessMetric label="Eligible" value={formatCount(readiness?.eligible_count)} />' in source
    assert '<ReadinessMetric label="Official sim" value={formatCount(summary.officially_simulated)} />' in source
    assert '<ReadinessMetric label="Live API" value={readiness?.official_api_called ? "called" : "not called"} />' in source
    assert "Blocking: {blockers || \"none\"}" in source
    assert "Family blockers: {familyBlockers || \"none\"}" in source
    assert "Production gaps: {productionGaps || \"none\"}" in source
    assert "Next: {nextSteps || \"none\"}" in source
