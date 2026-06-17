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
APP = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "App.tsx"


def _source() -> str:
    return CANDIDATE_TABLE.read_text(encoding="utf-8")


def _app_source() -> str:
    return APP.read_text(encoding="utf-8")


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


def test_candidate_table_bounds_target_pool_size_and_sanitizes_filter_input():
    source = _source()

    assert "const MIN_TARGET_POOL_SIZE = 1;" in source
    assert "const MAX_TARGET_POOL_SIZE = 100;" in source
    assert "const MAX_FILTER_LENGTH = 200;" in source
    assert "setTargetPoolSize(clampTargetPoolSize(value));" in source
    assert "min={MIN_TARGET_POOL_SIZE}" in source
    assert "max={MAX_TARGET_POOL_SIZE}" in source
    assert "target_pool_size: targetPoolSize" in source
    assert "const existingPoolSize = poolSnapshot?.eligibleCount ?? poolEligibleCandidates.length;" in source
    assert "const nextDeficit = Math.max(0, targetPoolSize - existingPoolSize);" in source
    assert "existing_pool_size: existingPoolSize" in source
    assert "pool_deficit: nextDeficit" in source
    assert 'automation_mode: "maintain_candidate_pool"' in source
    assert "auto_simulate_after_generation: false" in source
    assert "auto_check_after_simulation: false" in source
    assert "maxLength={MAX_FILTER_LENGTH}" in source
    assert "setFilter(sanitizeTextInput(value, MAX_FILTER_LENGTH));" in source
    assert 'value.replace(/[\\x00-\\x1F\\x7F]/g, "").slice(0, maxLength)' in source


def test_candidate_pool_updates_refresh_phase_state_in_app_shell():
    source = _source()
    app = _app_source()

    assert "onCandidatePoolUpdated?: () => void;" in source
    assert "onCandidatePoolUpdated?.()" in source
    assert "const handleCandidatePoolUpdated = useCallback(() => {" in app
    assert 'void candidatesApi.call("/api/candidates?summary=true");' in app
    assert 'void phaseApi.call("/api/phase_state");' in app
    assert "onCandidatePoolUpdated={handleCandidatePoolUpdated}" in app


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
    assert 'label: "可推进"' in source
    assert 'label: "需优化"' in source
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
    assert "function summarizeCandidateQuality(candidates: Candidate[], retained: number, targetPoolSize: number)" in source
    assert '<QualitySummaryItem label="主池保留" value={String(qualitySummary.retained)} />' in source
    assert '<QualitySummaryItem label="可推进" value={String(qualitySummary.promotable)} />' in source
    assert '<QualitySummaryItem label="需优化" value={String(qualitySummary.rework)} />' in source
    assert '<QualitySummaryItem label="阻断" value={String(qualitySummary.blocked)} />' in source
    assert '<QualitySummaryItem label="输出模式" value={qualitySummary.outputMode} />' in source
    assert '"expression_too_nested"' in source
    assert "const displayQueueCandidates = useMemo(" in source
    assert 'viewMode === "candidates"\n        ? candidateManagementDisplayCandidates(candidates, retainedPoolCandidates, serverWorkflowPlan)\n        : rawQueueCandidates' in source
    assert "const summaryCandidates = displayQueueCandidates;" in source
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
    assert 'status.includes("high_cloud_similarity")' in source
    assert '(status.includes("blocked") && !candidateHasSubmitOnlyBlockers(candidate))' in source
    assert "function candidateHasSubmitOnlyBlockers(candidate: Candidate)" in source


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
    assert "...buildCredentialOverrides()," in source
    assert "target_pool_size: targetPoolSize" in source
    assert '"/api/check_batch"' in source
    assert "const payload: Record<string, unknown> = { ...buildCredentialOverrides() };" in source
    assert "payload.candidate_ids = [alphaId];" in source
    assert "payload.max_simulations = 1;" in source
    assert "body: JSON.stringify(payload)" in source
    assert "运行官方验证队列" in source
    assert "真实 Alpha submit" in source
    assert "单行补模拟" in source
    assert 'callSingleCheckApi<CandidateCheckResult>("/api/check"' in source
    assert "candidate," in source
    assert "单行补查" in source
    assert '"/api/submit"' not in source
    assert "poolEligibleCandidates.length" in source
    assert "targetPoolSize" in source
    generate_body = source.split('"/api/generate_candidates"', 1)[1].split("});", 1)[0]
    assert "...buildCredentialOverrides()" not in generate_body
    assert "username" not in generate_body
    assert "password" not in generate_body
    assert "token" not in generate_body


def test_candidate_table_auto_pool_simulates_top_three_main_pool_ids():
    source = _source()

    assert "const AUTO_SIMULATION_BATCH_SIZE = 3;" in source
    assert "serverMainPoolCandidates\n        ? rankPoolCandidates(serverMainPoolCandidates)" in source
    assert "const hasExplicitOverride = Boolean(candidateOverride && candidateOverride.length);" in source
    assert "workflowCandidatesForQueue(candidates, retainedPoolCandidates, serverWorkflowPlan?.validator?.next_candidate_ids)" in source
    assert "const candidateIds = simulationCandidateIds(candidatesForSimulation, AUTO_SIMULATION_BATCH_SIZE);" in source
    assert "payload.candidate_ids = candidateIds;" in source
    assert "payload.max_simulations = Math.min(AUTO_SIMULATION_BATCH_SIZE, candidateIds.length);" in source
    assert "const fallbackScore = (candidate as { score?: unknown }).score;" in source
    assert "const score = Number(candidate.scorecard?.total_score ?? fallbackScore ?? 0);" in source


def test_candidate_table_only_runs_batch_check_after_successful_simulation():
    source = _source()

    assert "const result = simulationResultSummary(event);" in source
    assert "const simulationSucceeded = result.completed > 0;" in source
    assert 'if (autoPipelineStageRef.current === "await_quality_check" && simulationSucceeded)' in source
    assert "const candidatesForCheck = nextBatchCheckCandidatesRef.current || undefined;" in source
    assert "void startBatchCheck(candidatesForCheck);" in source
    assert "resetAutoPipelineStageIfCurrent(\"await_quality_check\");" in source
    assert "nextBatchCheckCandidatesRef.current = null;" in source


def test_candidate_table_refills_after_quality_check_deficit():
    source = _source()

    assert "snapshot: candidatePoolSnapshot(nextRows, nextMainPool, targetPoolSize, nextWorkflowPlan)" in source
    assert "const producerDeficit = Number(workflowPlan?.producer?.deficit);" in source
    assert 'const shouldContinueMaintenance = autoPipelineStageRef.current === "await_quality_check";' in source
    assert '"await_simulation"' not in source
    assert "auto_simulate_after_generation !== false" not in source
    assert "loaded?.snapshot.deficit" in source
    assert "if (shouldContinueMaintenance && loaded?.snapshot.deficit && loaded.snapshot.deficit > 0)" in source
    assert "void generateCandidates(loaded.snapshot)" in source
    assert "主池仍缺 ${loaded.snapshot.deficit} 个候选，继续自动补位。" in source
    assert 'resetAutoPipelineStageIfCurrent("await_quality_check");' in source
    assert 'onClick={() => void generateCandidates()}' in source
    assert 'onRetry={() => void generateCandidates()}' in source


def test_candidate_table_optimizes_rework_before_refill_without_submit_or_credentials():
    source = _source()

    assert "const MAX_AUTO_OPTIMIZATION_CYCLES = 1;" in source
    assert '"await_optimization"' in source
    assert '"/api/candidates/optimize"' in source
    assert "function optimizationCandidatesForPool" in source
    assert "serverWorkflowPlan?.rework?.candidate_ids" in source
    assert "loaded.workflowPlan?.rework?.candidate_ids" in source
    assert 'candidate.production_decision?.action === "optimize"' in source
    assert "autoOptimizationCycles < MAX_AUTO_OPTIMIZATION_CYCLES" in source
    assert "void startOptimization(loaded.snapshot, reworkCandidates);" in source
    assert "先优化 ${Math.min(reworkCandidates.length, AUTO_SIMULATION_BATCH_SIZE)} 个需优化候选" in source
    assert "auto_simulate_after_optimization: false" in source
    assert "本地优化已回池；主池仍缺 ${loaded.snapshot.deficit} 个候选，继续自动补位。" in source
    assert "void startSimulation(undefined, optimizedPool);" not in source
    assert "function optimizationChildrenForSimulation" not in source
    assert "const nextBatchCheckCandidatesRef = useRef<Candidate[] | null>(null);" in source
    assert "const hasExplicitOverride = Boolean(candidateOverride && candidateOverride.length);" in source
    assert "nextBatchCheckCandidatesRef.current = candidateIds" in source
    assert ".map((id) => candidatesForSimulation.find((row) => candidateIdentity(row) === id))" in source
    assert "const startBatchCheck = useCallback(async (candidateOverride?: Candidate[])" in source
    assert "const candidatesForCheck = candidateOverride && candidateOverride.length" in source
    assert "void startBatchCheck(candidatesForCheck);" in source
    assert 'failed: "候选本地优化失败"' in source
    assert "setOptimizationError(message);" in source
    assert 'updateAutoPipelineStage("idle");' in source
    optimize_body = source.split('"/api/candidates/optimize"', 1)[1].split("});", 1)[0]
    assert "...buildCredentialOverrides()" not in optimize_body
    assert "username" not in optimize_body
    assert "password" not in optimize_body
    assert "token" not in optimize_body
    assert '"/api/submit"' not in source
    assert '"/api/submit_batch"' not in source
