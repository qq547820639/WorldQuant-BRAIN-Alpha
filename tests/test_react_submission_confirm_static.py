from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "components"
TYPES = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "types" / "index.ts"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _submission_source() -> str:
    return "\n".join(
        _source(COMPONENTS / name)
        for name in (
            "SubmissionConfirmPanel.tsx",
            "SubmissionGates.tsx",
            "SubmissionChecklist.tsx",
            "SubmissionGuidance.tsx",
        )
    )


def test_submit_readiness_contract_is_typed_for_react():
    types = _source(TYPES)

    assert "export interface SubmitReadinessResponse" in types
    assert "authoritative_stop_rule?: string;" in types
    assert "validation_command?: string;" in types
    assert "official_api_called?: boolean;" in types
    assert "non_submit_flow?: boolean;" in types
    assert "real_submit_performed?: boolean;" in types
    assert "ready_to_submit?: boolean;" in types
    assert "submit_ready_claim_allowed?: boolean;" in types
    assert "job_family_candidate_count?: number;" in types
    assert "top_blocking_reasons?: ReadinessReasonCount[];" in types
    assert "production_gaps?: SubmitReadinessFinding[];" in types
    assert "required_next_steps?: string[];" in types


def test_state_cards_defer_heavy_submit_readiness_to_confirm_panel():
    source = _source(COMPONENTS / "StateCards.tsx")

    assert 'const readinessApi = useApi<SubmitReadinessResponse>();' not in source
    assert 'void readinessApi.call("/api/submit_readiness");' not in source
    assert "const submitCount = readinessApi.data?.eligible_count ?? 0;" not in source
    assert "const slotLimit = backtestSlotLimit(slotsApi.data);" in source
    assert 'official_backtests: `${activeSlots}/${slotLimit}`,' in source
    assert "backtestActiveCount(slotsApi.data)" in source
    assert 'caption: "提交审计",' in source
    assert 'eligible: "打开",' in source


def test_submission_confirm_panel_exposes_readiness_summary():
    source = _submission_source()

    assert 'const readinessApi = useApi<SubmitReadinessResponse>();' in source
    assert 'callReadiness<SubmitReadinessResponse>("/api/submit_readiness")' in source
    assert "<ReadinessSummary readiness={readiness}" in source
    assert '<ReadinessMetric label="阻断复核" value={ready ? "通过" : "未通过"}' in source
    assert '<ReadinessMetric label="复核候选" value={formatCount(readiness?.eligible_count)} />' in source
    assert '<ReadinessMetric label="官方仿真" value={formatCount(summary.officially_simulated)} />' in source
    assert '<ReadinessMetric label="官方接口" value={readiness?.official_api_called ? "已调用" : "未调用"} />' in source
    assert '<ReadinessMetric label="真实提交" value={readiness?.real_submit_performed ? "真实提交已发生" : "未执行真实提交"}' in source
    assert "readiness?.authoritative_stop_rule || readiness?.validation_command || readiness?.source" in source
    assert 'readiness?.submit_ready_claim_allowed ? "可按验证结果继续人工复核" : "不可声明提交就绪"' in source
    assert "判定来源: {readiness?.authoritative_stop_rule || readiness?.validation_command || readiness?.source" in source
    assert "提交就绪声明: {readiness?.submit_ready_claim_allowed" in source
    assert "allBlockers = readiness?.top_blocking_reasons || [];" in source
    assert "allFamilyBlockers = readiness?.top_family_blocking_reasons || [];" in source
    assert "allProductionGaps = readiness?.production_gaps || [];" in source
    assert "allNextSteps = readiness?.required_next_steps || [];" in source
    assert "previewLabel" not in source
    assert ".slice(0, 4)" not in source


def test_submission_confirm_mobile_cards_show_full_blockers_without_truncation():
    source = _submission_source()

    assert 'aria-label={`${title} 移动端卡片`}' in source
    assert 'className="space-y-3 md:hidden"' in source
    assert 'hidden min-w-0 overflow-hidden md:block rounded-md' in source
    assert "readinessStatusLabel(row.status)" in source
    assert "break-words font-mono-value text-xs text-text-secondary" in source
    assert 'max-w-sm break-words p-3 text-xs text-text-secondary' in source
