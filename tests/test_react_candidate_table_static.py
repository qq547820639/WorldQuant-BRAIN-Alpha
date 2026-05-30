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


def test_candidate_table_uses_virtualized_render_window():
    source = _source()

    assert "const CANDIDATE_FETCH_LIMIT = 1000;" in source
    assert "const VIRTUAL_ROW_HEIGHT = 48;" in source
    assert "const VIRTUAL_OVERSCAN = 8;" in source
    assert "const VIRTUAL_VIEWPORT_HEIGHT = 520;" in source
    assert "const [scrollTop, setScrollTop] = useState(0);" in source
    assert "const virtualStartIndex = Math.max(0, Math.floor(scrollTop / VIRTUAL_ROW_HEIGHT) - VIRTUAL_OVERSCAN);" in source
    assert "const virtualRows = sorted.slice(virtualStartIndex, virtualEndIndex);" in source
    assert "topSpacerHeight" in source
    assert "bottomSpacerHeight" in source
    assert "sorted.slice(0, 50)" not in source
    assert "showMoreCandidates" not in source
    assert "Show more" not in source
    assert "Showing {visibleStartRow}-{visibleEndRow} of {sorted.length} candidates" in source


def test_candidate_table_exposes_large_list_accessibility_metadata():
    source = _source()

    assert 'data-virtualized-candidate-table="true"' in source
    assert 'aria-label="Scrollable candidate results"' in source
    assert "aria-rowcount={sorted.length > 0 ? sorted.length + 1 : undefined}" in source
    assert "aria-rowindex={virtualStartIndex + index + 2}" in source
    assert 'role="status"' in source
    assert 'aria-live="polite"' in source
    assert 'tr aria-hidden="true"' in source


def test_candidate_table_bounds_generation_count_and_sanitizes_filter_input():
    source = _source()

    assert "const MIN_GENERATE_COUNT = 1;" in source
    assert "const MAX_GENERATE_COUNT = 100;" in source
    assert "const MAX_FILTER_LENGTH = 200;" in source
    assert "JSON.stringify({ count: clampGenerateCount(generateCount) })" in source
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
    assert 'aria-hidden="true">{active ? (sortAsc ? "↑" : "↓") : ""}</span>' in source


def test_candidate_table_tolerates_sparse_lifecycle_rows_and_uses_all_candidate_ids():
    source = _source()

    assert "candidateText(c.expression).toLowerCase().includes(normalizedFilter)" in source
    assert "candidateText(c.family).toLowerCase().includes(normalizedFilter)" in source
    assert "candidateIdentity(c).toLowerCase().includes(normalizedFilter)" in source
    assert "function candidateIdentity(candidate: Candidate)" in source
    assert 'function candidateIds(candidate: Pick<Candidate, "alpha_id" | "official_alpha_id" | "simulation_id">)' in source
    assert "return [candidate.alpha_id, candidate.official_alpha_id, candidate.simulation_id]" in source
    assert "function candidateStatus(candidate: Candidate)" in source
    assert "const normalized = candidateText(s);" in source
    assert "function candidateText(value: unknown)" in source


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
    assert 'if (viewMode === "passed") return status === "submission_ready"' in source
    assert 'if (viewMode === "submittable") return status !== "submitted"' in source
    assert 'if (viewMode === "submitted") return status === "submitted" || candidateStage(candidate) === "submitted";' in source
    assert 'return status === "failed" || status === "rejected" || status === "blocked";' in source


def test_candidate_table_loads_fresh_check_results_for_submittable_queue():
    source = _source()

    assert 'if (viewMode !== "submittable") return;' in source
    assert 'callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results")' in source
    assert "setCheckResults(indexCheckResults(data.items || []));" in source
    assert "result.is_stale !== true && (result.submittable ?? result.passed)" in source
