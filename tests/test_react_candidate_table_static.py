from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_TABLE = (
    ROOT
    / "brain_alpha_ops"
    / "web"
    / "react_app"
    / "src"
    / "components"
    / "CandidateTable.tsx"
)


def _source() -> str:
    return CANDIDATE_TABLE.read_text(encoding="utf-8")


def test_candidate_table_fetches_all_candidates_and_uses_local_pagination_window():
    source = _source()

    assert 'callApi("/api/candidates")' in source
    assert "CANDIDATE_FETCH_LIMIT" not in source
    assert "?limit=1000" not in source
    assert "const PAGE_SIZE = 20;" in source
    assert "const totalPages = Math.max(1, Math.ceil(sortedCandidates.length / PAGE_SIZE));" in source
    assert "return sortedCandidates.slice(startIndex, startIndex + PAGE_SIZE);" in source
    assert "上一页" in source
    assert "下一页" in source
    assert "sorted.slice(0, 50)" not in source
    assert "showMoreCandidates" not in source
    assert "Show more" not in source
    assert "显示 {visibleStart}-{visibleEnd}，共 {sortedCandidates.length} 条" in source
    assert "当前接口返回 {candidateMeta.returned} 条候选" in source


def test_candidate_table_exposes_paginated_table_accessibility_metadata():
    source = _source()

    assert 'aria-label="候选结果"' in source
    assert "function CandidateMobileCard" in source
    assert 'className="hidden md:block"' in source
    assert 'maxWidth: "100%"' in source
    assert 'role="alert"' in source
    assert 'role="status"' in source
    assert 'aria-live="polite"' in source
    assert 'aria-live="assertive"' in source
    assert "colSpan={hasActions ? 9 : 8}" in source


def test_candidate_table_bounds_generation_count_and_sanitizes_filter_input():
    source = _source()

    assert "const MIN_GENERATE_COUNT = 1;" in source
    assert "const MAX_GENERATE_COUNT = 100;" in source
    assert "const MAX_FILTER_LENGTH = 200;" in source
    assert "clampGenerateCount(generateCount)" in source
    assert "setGenerateCount(clampGenerateCount(value));" in source
    assert "min={MIN_GENERATE_COUNT}" in source
    assert "max={MAX_GENERATE_COUNT}" in source
    assert "maxLength={MAX_FILTER_LENGTH}" in source
    assert "setFilter(sanitizeTextInput(value, MAX_FILTER_LENGTH));" in source
    assert 'value.replace(/[\\x00-\\x1F\\x7F]/g, "").slice(0, maxLength)' in source


def test_candidate_table_sort_headers_expose_column_sort_state():
    source = _source()

    assert "function SortHeader" in source
    assert 'aria-sort={active ? (sortAsc ? "ascending" : "descending") : "none"}' in source
    assert 'type="button"' in source
    assert "onClick={() => onSort(column)}" in source
    assert 'scope="col"' in source
    assert 'aria-hidden="true">{active ? (sortAsc ?' in source


def test_candidate_table_tolerates_sparse_lifecycle_rows_and_uses_all_candidate_ids():
    source = _source()

    assert "candidateText(c.expression).toLowerCase().includes(normalizedFilter)" in source
    assert "candidateText(c.family).toLowerCase().includes(normalizedFilter)" in source
    assert "candidateIdentity(c).toLowerCase().includes(normalizedFilter)" in source
    assert "candidateQualitySearchText(c).toLowerCase().includes(normalizedFilter)" in source
    assert "function candidateIdentity(candidate: Candidate)" in source
    assert 'function candidateIds(candidate: Pick<Candidate, "alpha_id" | "official_alpha_id" | "simulation_id"> | CandidateCheckResult)' in source
    assert "return [candidate.alpha_id, candidate.official_alpha_id, candidate.simulation_id]" in source
    assert "function candidateStatus(candidate: Candidate)" in source
    assert "const normalized = candidateText(candidate.lifecycle_status" in source
    assert "function candidateText(value: unknown)" in source


def test_candidate_table_exposes_alpha_quality_diagnostics_and_output_config():
    source = _source()

    assert '<th style={{ width: "7rem" }}>质量</th>' in source
    assert '<th style={{ width: "14rem" }}>阻断原因</th>' in source
    assert '<th style={{ width: "18rem" }}>输出</th>' in source
    assert "function candidateQualityBadge(candidate: Candidate)" in source
    assert 'label: "本地通过"' in source
    assert 'label: "阻断"' in source
    assert 'label: "未验证"' in source
    assert "function candidateBlockerText(candidate: Candidate)" in source
    assert "function candidateLocalValid(candidate: Candidate)" in source
    assert 'if (typeof diagnosis.local_candidate_valid === "boolean")' in source
    assert "return candidate.local_quality?.passed === true;" in source
    assert "function candidateHasBlockingQuality(candidate: Candidate)" in source
    assert 'return "missing_quality_diagnosis";' in source
    assert "function candidateOutputSummary(candidate: Candidate)" in source
    assert "function candidateOutputDetail(candidate: Candidate)" in source
    assert "function summarizeCandidateQuality(candidates: Candidate[])" in source
    assert '<QualitySummaryItem label="达标" value={String(qualitySummary.ready)} />' in source
    assert '<QualitySummaryItem label="本地通过" value={String(qualitySummary.localValid)} />' in source
    assert '<QualitySummaryItem label="阻断" value={String(qualitySummary.blocked)} />' in source
    assert '<QualitySummaryItem label="输出模式" value={qualitySummary.outputMode} />' in source
    assert '<QualitySummaryItem label="Dataset" value={qualitySummary.dataset} />' in source
    assert "colSpan={hasActions ? 9 : 8}" in source


def test_candidate_table_exposes_queue_view_filters_for_inline_parity():
    source = _source()

    assert '| "pending_backtest"' in source
    assert '| "running_backtest"' in source
    assert '| "backtest_rework"' in source
    assert '| "passed"' in source
    assert '| "submittable"' in source
    assert '| "submitted"' in source
    assert '| "failed";' in source
    assert 'viewMode?: CandidateQueueView;' in source
    assert 'viewMode = "candidates"' in source
    assert "candidates.filter((candidate) => candidateMatchesQueueView(candidate, viewMode, checkResults))" in source
    assert 'if (viewMode === "pending_backtest") return status === "pending_backtest";' in source
    assert 'if (viewMode === "running_backtest") return status === "running_backtest" || status === "running";' in source
    assert 'if (viewMode === "backtest_rework") return status === "backtest_rework" || status === "failed_backtest" || status === "rejected";' in source
    assert 'if (viewMode === "passed") return candidateSubmissionReady(candidate);' in source
    assert "candidate.gate?.passed === true" not in source
    assert "candidates.filter(candidateSubmissionReady).length" in source
    assert 'if (viewMode === "submittable") return status !== "submitted"' in source
    assert 'if (viewMode === "submitted") return status === "submitted" || stage === "submitted";' in source
    assert 'return status === "failed" || status === "rejected" || status === "blocked";' in source


def test_candidate_table_loads_fresh_check_results_for_submittable_queue():
    source = _source()

    assert 'if (viewMode !== "submittable") return;' in source
    assert 'callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results")' in source
    assert "setCheckResults(indexCheckResults(result.items || []));" in source
    assert "result?.is_stale !== true && Boolean(result?.submittable ?? result?.passed ?? candidate.quality_diagnosis?.submission_ready)" in source


def test_candidate_table_forwards_token_credentials_without_stale_callbacks():
    source = _source()

    assert 'const token = credentials?.token.trim() || "";' in source
    assert "if (token) overrides.token = token;" in source
    assert "body: JSON.stringify({ ...buildCredentialOverrides(), count: clampGenerateCount(generateCount) })" in source
    assert "const payload: Record<string, unknown> = { ...buildCredentialOverrides() };" in source
    assert "payload.candidate_ids = [alphaId];" in source
    assert "payload.max_simulations = 1;" in source
    assert "body: JSON.stringify(payload)" in source
    assert "运行官方模拟" in source
    assert "真实 Alpha submit" in source
    assert "单个模拟" in source
    assert 'callSingleCheckApi<CandidateCheckResult>("/api/check"' in source
    assert "candidate," in source
    assert "单个检查" in source
    assert '"/api/submit"' not in source
    assert "}, [callApi, buildCredentialOverrides, generateCount, notify]);" in source
    assert "}, [callApi, buildCredentialOverrides, notify]);" in source
