/**
 * Candidate management table for the state-card UI.
 *
 * The table keeps the compact card-first workflow, but preserves the production
 * semantics users need before official validation or pre-submit blocker review checks.
 *
 * Refactored: extracted CandidateRow, CandidateTableToolbar, useCandidateColumns,
 * CandidateDetailPanel, useCandidatePipeline, and useCandidateActions into separate files.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { useApi } from "@/hooks/useApi";
import { useGlobalData } from "@/hooks/useGlobalData";
import { useCandidatePipeline } from "@/hooks/useCandidatePipeline";
import { useSseManager } from "@/hooks/useSseManager";
import { useCandidateActions } from "@/hooks/useCandidateActions";
import type { AlphaLifecycleHistoryResponse, Candidate } from "@/types";
import { getStarred } from "@/utils/starredCandidates";
import ProgressFeedback from "@/components/ProgressFeedback";
import {
  candidateIdentity,
  candidateStatus,
  candidateCreatedAt,
  candidateText,
  candidateQualitySearchText,
  candidateNeedsOptimization,
  candidateRetainedPoolEligible,
  clampTargetPoolSize,
  sanitizeTextInput,
  indexCheckResults,
  lifecycleTracesForCandidates,
  queueViewLabel,
  CandidateCheckResult,
  CandidateQueueView,
  CandidatePoolSnapshot,
  CandidateWorkflowPlan,
  CandidateListMeta,
  summarizeCandidateQuality,
  rankPoolCandidates,
  candidatePoolSnapshot,
  workflowCandidatesForQueue,
  candidateMatchesQueueView,
  DEFAULT_TARGET_POOL_SIZE,
  MAX_FILTER_LENGTH,
} from "./CandidateTableUtils";
import {
  CandidateMobileCard,
  EmptyState,
} from "./CandidateTableSubComponents";
import { CandidateRow } from "./CandidateRow";
import CandidateTablePagination from "./CandidateTablePagination";
import { CandidateTableToolbar } from "./CandidateTableToolbar";
import type { QualitySummaryData } from "./CandidateTableToolbar";
import { useCandidateColumns } from "./useCandidateColumns";

const PAGE_SIZE = 20;

type SortKey = "score" | "status" | "created";

type LoadedCandidateState = {
  rows: Candidate[];
  mainPoolCandidates: Candidate[] | null;
  snapshot: CandidatePoolSnapshot;
  workflowPlan?: CandidateWorkflowPlan | null;
};

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onScore?: (candidate: Candidate) => void;
  showProductionControls?: boolean;
  showRowActions?: boolean;
  credentials?: import("@/types").BrainCredentials;
  viewMode?: CandidateQueueView;
  onCandidatePoolUpdated?: () => void;
}

export default function CandidateTable({
  credentials,
  notify,
  onCandidatePoolUpdated,
  onScore,
  showProductionControls = true,
  showRowActions = false,
  viewMode = "candidates",
}: Props) {
  const { candidates: globalCandidates, refreshAll } = useGlobalData();
  const actionApi = useApi<{ ok?: boolean; job_id?: string; task_id?: string; error?: string }>();
  const checkResultsApi = useApi<{ items?: CandidateCheckResult[] }>();
  const lifecycleApi = useApi<AlphaLifecycleHistoryResponse>();
  const singleCheckApi = useApi<CandidateCheckResult>();
  const batchCheckApi = useApi<{ ok?: boolean; job_id?: string; task_id?: string; error?: string }>();
  const callApi = actionApi.call;
  const callCheckResultsApi = checkResultsApi.call;
  const callLifecycleApi = lifecycleApi.call;
  const callSingleCheckApi = singleCheckApi.call;
  const callBatchCheckApi = batchCheckApi.call;

  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [serverMainPoolCandidates, setServerMainPoolCandidates] = useState<Candidate[] | null>(null);
  const [serverWorkflowPlan, setServerWorkflowPlan] = useState<CandidateWorkflowPlan | null>(null);
  const [candidateMeta, setCandidateMeta] = useState<CandidateListMeta>({ returned: 0, total: 0 });
  const [checkResults, setCheckResults] = useState<Map<string, CandidateCheckResult>>(new Map());
  const [lifecycleHistory, setLifecycleHistory] = useState<AlphaLifecycleHistoryResponse | null>(null);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);

  const [filter, setFilter] = useState("");
  const [showStarredOnly, setShowStarredOnly] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [currentPage, setCurrentPage] = useState(1);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortAsc, setSortAsc] = useState(false);
  const [targetPoolSize, setTargetPoolSize] = useState(DEFAULT_TARGET_POOL_SIZE);

  const pipeline = useCandidatePipeline();
  const sseManager = useSseManager();

  const lastPoolDeficitWarningRef = useRef<number>(0);
  const POOL_DEFICIT_WARNING_COOLDOWN_MS = 30 * 60 * 1000;

  const processCandidatesData = useCallback((result: typeof globalCandidates.data): LoadedCandidateState | null => {
    if (!result?.ok) return null;
    const nextRows = result.candidates || result.items || [];
    const nextMainPool = Array.isArray(result.main_pool_candidates) ? result.main_pool_candidates : null;
    const nextWorkflowPlan = (result.workflow_plan || result.candidate_workflow || null) as CandidateWorkflowPlan | null;
    setCandidates(nextRows);
    setServerMainPoolCandidates(nextMainPool);
    setServerWorkflowPlan(nextWorkflowPlan);
    setCandidateMeta({
      returned: Number(result.returned_count ?? nextRows.length),
      total: Number(result.total ?? result.total_count ?? nextRows.length),
    });
    const snapshot = candidatePoolSnapshot(nextRows, nextMainPool, targetPoolSize, nextWorkflowPlan);
    const eligibleCount = snapshot.eligibleCount;
    if (eligibleCount < targetPoolSize) {
      const now = Date.now();
      if (now - lastPoolDeficitWarningRef.current >= POOL_DEFICIT_WARNING_COOLDOWN_MS) {
        lastPoolDeficitWarningRef.current = now;
        notify("warning", `候选池不足: 当前合格候选 ${eligibleCount}，目标池容量 ${targetPoolSize}，建议启动候选池自动推进补充候选。`);
      }
    }
    return {
      rows: nextRows,
      mainPoolCandidates: nextMainPool,
      workflowPlan: nextWorkflowPlan,
      snapshot,
    };
  }, [notify, targetPoolSize]);

  useEffect(() => {
    if (globalCandidates.data) {
      processCandidatesData(globalCandidates.data);
    }
  }, [globalCandidates.data, processCandidatesData]);

  const loadCandidates = useCallback(async (): Promise<LoadedCandidateState | null> => {
    refreshAll();
    const loaded = processCandidatesData(globalCandidates.data);
    const [checkResultsResult, lifecycleResult] = await Promise.all([
      callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results"),
      callLifecycleApi<AlphaLifecycleHistoryResponse>("/api/alpha_lifecycle?limit=250"),
    ]);
    if (checkResultsResult?.ok) {
      setCheckResults(indexCheckResults(checkResultsResult.items || []));
    } else if (checkResultsResult?.error) {
      notify("error", apiErrorMessage(checkResultsResult, "检查结果加载失败"));
    }
    if (lifecycleResult?.ok) {
      setLifecycleHistory(lifecycleResult);
      setLifecycleError(null);
    } else if (lifecycleResult) {
      setLifecycleError(apiErrorMessage(lifecycleResult, "生命周期历史加载失败"));
    } else {
      setLifecycleError("生命周期历史加载失败");
    }
    return loaded;
  }, [refreshAll, processCandidatesData, globalCandidates.data, callCheckResultsApi, callLifecycleApi, notify]);

  const refreshCheckResults = useCallback(async () => {
    if (viewMode !== "submittable") return;
    const result = await callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results");
    if (result?.ok) {
      setCheckResults(indexCheckResults(result.items || []));
    } else if (result?.error) {
      notify("error", apiErrorMessage(result, "检查结果加载失败"));
    }
  }, [callCheckResultsApi, notify, viewMode]);

  useEffect(() => { void loadCandidates(); }, [loadCandidates]);
  useEffect(() => { void refreshCheckResults(); }, [refreshCheckResults]);

  const poolEligibleCandidates = useMemo(
    () => (serverMainPoolCandidates ? rankPoolCandidates(serverMainPoolCandidates) : rankPoolCandidates(candidates.filter(candidateRetainedPoolEligible))),
    [candidates, serverMainPoolCandidates],
  );
  const retainedPoolCandidates = useMemo(
    () => poolEligibleCandidates.slice(0, targetPoolSize),
    [poolEligibleCandidates, targetPoolSize],
  );

  const actions = useCandidateActions({
    pipeline,
    callApi,
    callSingleCheckApi,
    callBatchCheckApi,
    loadCandidates,
    refreshCheckResults,
    onCandidatePoolUpdated,
    notify,
    credentials,
    candidates,
    retainedPoolCandidates,
    poolEligibleCandidates,
    serverWorkflowPlan,
    targetPoolSize,
  });

  useEffect(() => {
    if (pipeline.task.jobId) {
      sseManager.connect("task", `/sse?job_id=${encodeURIComponent(pipeline.task.jobId)}`, {
        onEvent: actions.handleTaskEvent,
        onExhausted: actions.handleTaskStreamExhausted,
      });
    } else {
      sseManager.disconnect("task");
    }

    if (pipeline.check.jobId) {
      sseManager.connect("check", `/sse?job_id=${encodeURIComponent(pipeline.check.jobId)}`, {
        onEvent: actions.handleCheckEvent,
        onExhausted: actions.handleCheckStreamExhausted,
      });
    } else {
      sseManager.disconnect("check");
    }

    if (pipeline.optimization.jobId) {
      sseManager.connect("optimization", `/sse?job_id=${encodeURIComponent(pipeline.optimization.jobId)}`, {
        onEvent: actions.handleOptimizationEvent,
        onExhausted: actions.handleOptimizationStreamExhausted,
      });
    } else {
      sseManager.disconnect("optimization");
    }

    if (pipeline.simulation.jobId) {
      sseManager.connect("simulation", `/sse?job_id=${encodeURIComponent(pipeline.simulation.jobId)}`, {
        onEvent: actions.handleSimEvent,
        onExhausted: actions.handleSimStreamExhausted,
      });
    } else {
      sseManager.disconnect("simulation");
    }
  }, [
    pipeline.task.jobId, pipeline.check.jobId, pipeline.optimization.jobId, pipeline.simulation.jobId,
    actions.handleTaskEvent, actions.handleTaskStreamExhausted,
    actions.handleCheckEvent, actions.handleCheckStreamExhausted,
    actions.handleOptimizationEvent, actions.handleOptimizationStreamExhausted,
    actions.handleSimEvent, actions.handleSimStreamExhausted,
    sseManager,
  ]);

  const rawQueueCandidates = useMemo(
    () => candidates.filter((c) => candidateMatchesQueueView(c, viewMode, checkResults)),
    [candidates, checkResults, viewMode],
  );
  const displayQueueCandidates = useMemo(
    () => (viewMode === "candidates" ? candidateManagementDisplayCandidates(candidates, retainedPoolCandidates, serverWorkflowPlan) : rawQueueCandidates),
    [candidates, rawQueueCandidates, retainedPoolCandidates, serverWorkflowPlan, viewMode],
  );
  const visibleLifecycleTraces = useMemo(
    () => lifecycleTracesForCandidates(lifecycleHistory?.alpha_traces || [], displayQueueCandidates, filter),
    [displayQueueCandidates, filter, lifecycleHistory],
  );

  const sortedCandidates = useMemo(() => {
    const normalizedFilter = filter.trim().toLowerCase();
    const filtered = normalizedFilter
      ? displayQueueCandidates.filter((c) =>
          candidateText(c.expression).toLowerCase().includes(normalizedFilter) ||
          candidateText(c.family).toLowerCase().includes(normalizedFilter) ||
          candidateIdentity(c).toLowerCase().includes(normalizedFilter) ||
          candidateQualitySearchText(c).toLowerCase().includes(normalizedFilter)
        )
      : displayQueueCandidates;
    const starFiltered = showStarredOnly
      ? filtered.filter((c) => getStarred().has(candidateIdentity(c)))
      : filtered;
    return [...starFiltered].sort((a, b) => {
      let va: number; let vb: number;
      switch (sortKey) {
        case "score": va = a.scorecard?.total_score ?? 0; vb = b.scorecard?.total_score ?? 0; break;
        case "status": return candidateStatus(a).localeCompare(candidateStatus(b)) * (sortAsc ? 1 : -1);
        case "created": va = candidateCreatedAt(a); vb = candidateCreatedAt(b); break;
        default: return 0;
      }
      return sortAsc ? va - vb : vb - va;
    });
  }, [displayQueueCandidates, filter, sortAsc, sortKey, showStarredOnly]);

  const summaryCandidates = displayQueueCandidates;
  const qualitySummary = useMemo(
    () => summarizeCandidateQuality(summaryCandidates, retainedPoolCandidates.length, targetPoolSize),
    [summaryCandidates, retainedPoolCandidates.length, targetPoolSize],
  );
  const totalPages = Math.max(1, Math.ceil(sortedCandidates.length / PAGE_SIZE));
  const paginatedCandidates = useMemo(() => {
    const startIndex = (currentPage - 1) * PAGE_SIZE;
    return sortedCandidates.slice(startIndex, startIndex + PAGE_SIZE);
  }, [currentPage, sortedCandidates]);

  const currentPageIds = useMemo(
    () => paginatedCandidates.map((c) => candidateIdentity(c)),
    [paginatedCandidates],
  );

  const selectedCount = selectedIds.size;
  const canShowRowActions = showRowActions && Boolean(onScore);

  const handleBatchScore = useCallback(() => {
    if (!onScore) return;
    const selected = sortedCandidates.filter((c) => selectedIds.has(candidateIdentity(c)));
    selected.forEach((c) => onScore(c));
  }, [onScore, selectedIds, sortedCandidates]);

  const handleBatchCheck = useCallback(() => {
    const selected = sortedCandidates.filter((c) => selectedIds.has(candidateIdentity(c)));
    if (selected.length > 0) {
      void actions.startBatchCheck(selected);
    }
  }, [selectedIds, sortedCandidates, actions.startBatchCheck]);

  const handleBatchSimulate = useCallback(() => {
    const selected = sortedCandidates.filter((c) => selectedIds.has(candidateIdentity(c)));
    if (selected.length > 0) {
      actions.startSimulation(undefined, selected);
    }
  }, [selectedIds, sortedCandidates, actions.startSimulation]);

  useEffect(() => { setCurrentPage(1); }, [filter, sortKey, sortAsc, viewMode]);
  useEffect(() => { setCurrentPage((page) => Math.min(page, totalPages)); }, [totalPages]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) { setSortAsc(!sortAsc); } else { setSortKey(key); setSortAsc(false); }
  };
  const handleTargetPoolSizeChange = (value: string) => { setTargetPoolSize(clampTargetPoolSize(value)); };
  const handleFilterChange = (value: string) => { setFilter(sanitizeTextInput(value, MAX_FILTER_LENGTH)); };

  const handleToggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleToggleSelectAll = useCallback((ids: string[]) => {
    setSelectedIds((prev) => {
      const allSelected = ids.length > 0 && ids.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) {
        ids.forEach((id) => next.delete(id));
      } else {
        ids.forEach((id) => next.add(id));
      }
      return next;
    });
  }, []);

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const loading = globalCandidates.loading;
  const loadError = globalCandidates.error;
  const visibleStart = sortedCandidates.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const visibleEnd = Math.min(currentPage * PAGE_SIZE, sortedCandidates.length);
  const title = viewMode === "candidates" ? "候选管理" : `${queueViewLabel(viewMode)}候选`;
  const remoteTruncated = candidateMeta.total > candidateMeta.returned;
  const hasActions = canShowRowActions || showProductionControls;
  const candidateWorkflowBusy = (pipeline.task.state === "loading" || pipeline.task.state === "progress")
    || (pipeline.simulation.state === "loading" || pipeline.simulation.state === "progress")
    || (pipeline.optimization.state === "loading" || pipeline.optimization.state === "progress")
    || (pipeline.check.state === "loading" || pipeline.check.state === "progress");

  if (loading) {
    return (
      <ProgressFeedback state="loading" title="候选管理" progress={{ phase: "candidate_load", status_message: "正在加载候选数据。" }} />
    );
  }

  const detailPanelProps = useMemo(() => ({
    showProductionControls,
    taskState: pipeline.task.state, taskProgress: pipeline.task.progress, taskError: pipeline.task.error,
    taskStreamExhausted: sseManager.task.exhausted,
    onRetryTask: () => { void actions.generateCandidates(); },
    simState: pipeline.simulation.state, simProgress: pipeline.simulation.progress, simError: pipeline.simulation.error,
    onRetrySim: () => { actions.startSimulation(); },
    optimizationState: pipeline.optimization.state, optimizationProgress: pipeline.optimization.progress, optimizationError: pipeline.optimization.error,
    onRetryOptimization: () => { void actions.startOptimization(); },
    checkState: pipeline.check.state, checkProgress: pipeline.check.progress, checkError: pipeline.check.error,
    onRetryCheck: () => { void actions.startBatchCheck(actions.lastBatchCheckCandidatesRef.current || undefined); },
  }), [showProductionControls, pipeline.task.state, pipeline.task.progress, pipeline.task.error, sseManager.task.exhausted, actions.generateCandidates,
    pipeline.simulation.state, pipeline.simulation.progress, pipeline.simulation.error, actions.startSimulation,
    pipeline.optimization.state, pipeline.optimization.progress, pipeline.optimization.error, actions.startOptimization,
    pipeline.check.state, pipeline.check.progress, pipeline.check.error, actions.startBatchCheck, actions.lastBatchCheckCandidatesRef]);

  const { columnCount, renderHeader } = useCandidateColumns({
    sortKey,
    sortAsc,
    hasActions,
    checkResults,
    canShowRowActions,
    showProductionControls,
    candidateWorkflowBusy,
    checkingAlphaId: pipeline.checkingAlphaId,
    onSort: handleSort,
    onScore,
    onSimulate: (c: Candidate) => { actions.startSimulation(c); },
    onCheck: actions.startSingleCheck,
    allCurrentPageIds: currentPageIds,
    selectedIds,
    onToggleSelectAll: handleToggleSelectAll,
    onToggleSelect: handleToggleSelect,
  });

  const tableContainerRef = useRef<HTMLDivElement>(null);
  const ESTIMATED_ROW_HEIGHT = 48;
  const rowVirtualizer = useVirtualizer({
    count: paginatedCandidates.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 5,
  });

  return (
    <div className="animate-fade-in">
      <CandidateTableToolbar
        title={title}
        viewMode={viewMode}
        retainedCount={retainedPoolCandidates.length}
        targetPoolSize={targetPoolSize}
        poolEligibleCount={poolEligibleCandidates.length}
        rawQueueCount={rawQueueCandidates.length}
        sortedCount={sortedCandidates.length}
        candidateMeta={candidateMeta}
        filter={filter}
        remoteTruncated={remoteTruncated}
        showProductionControls={showProductionControls}
        candidateWorkflowBusy={candidateWorkflowBusy}
        taskState={pipeline.task.state}
        simState={pipeline.simulation.state}
        optimizationState={pipeline.optimization.state}
        onTargetPoolSizeChange={handleTargetPoolSizeChange}
        onGenerateCandidates={() => { void actions.generateCandidates(); }}
        onStartValidationQueue={actions.startOfficialValidationQueue}
        onStartOptimization={() => { void actions.startOptimization(); }}
        qualitySummary={qualitySummary as QualitySummaryData}
        lifecycleHistory={lifecycleHistory}
        lifecycleError={lifecycleError}
        lifecycleLoading={lifecycleApi.loading}
        visibleLifecycleTraces={visibleLifecycleTraces}
        detailPanel={detailPanelProps}
        loadError={loadError}
        apiLoading={globalCandidates.loading}
        onRetryLoad={loadCandidates}
        onFilterChange={handleFilterChange}
        showStarredOnly={showStarredOnly}
        onToggleStarFilter={() => setShowStarredOnly((v) => !v)}
        selectedIds={selectedIds}
        selectedCount={selectedCount}
        onClearSelection={handleClearSelection}
        onBatchScore={handleBatchScore}
        onBatchCheck={handleBatchCheck}
        onBatchSimulate={handleBatchSimulate}
        sortedCandidates={sortedCandidates}
      />

      <div className="panel">
        {pipeline.task.state === "success" && pipeline.taskSuccessBanner && (
          <div
            className="panel-body-padded"
            style={{
              borderBottom: "0.5px solid var(--color-border-default)",
              background: "var(--color-task-success-bg)",
              borderLeft: "3px solid var(--color-sparkline-dot)",
              margin: 0,
            }}
            role="status"
            aria-live="polite"
          >
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "4px 16px" }}>
              <span style={{ fontSize: 14, marginRight: 4 }}>✅</span>
              <span className="text-sm font-medium text-text-primary">
                候选池自动推进完成
              </span>
              <span className="text-xs text-text-secondary">
                新增 <span className="font-mono-value text-positive">{pipeline.taskSuccessBanner.newCount}</span> 个候选
              </span>
              {pipeline.taskSuccessBanner.optimizedCount > 0 && (
                <span className="text-xs text-text-secondary">
                  优化 <span className="font-mono-value text-accent">{pipeline.taskSuccessBanner.optimizedCount}</span> 个
                </span>
              )}
              <span className="text-xs text-text-tertiary">
                当前池状态：
                <span className="font-mono-value text-text-primary">{retainedPoolCandidates.length}/{targetPoolSize}</span>
              </span>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ marginTop: 6 }}
              onClick={() => pipeline.setTaskSuccessBanner(null)}
              aria-label="关闭成功提示"
            >
              关闭提示
            </button>
          </div>
        )}

        <div className="panel-body md:hidden">
          {paginatedCandidates.length === 0 ? (
            <EmptyState filter={!!filter} showProductionControls={showProductionControls} />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {paginatedCandidates.map((candidate, index) => (
                <CandidateMobileCard
                  key={`${candidateIdentity(candidate)}_mobile_${index}`}
                  candidate={candidate}
                  checkResults={checkResults}
                  canShowRowActions={canShowRowActions}
                  canSimulate={showProductionControls}
                  canCheck={showProductionControls}
                  workflowBusy={candidateWorkflowBusy}
                  simulationBusy={candidateWorkflowBusy}
                  checkingAlphaId={pipeline.checkingAlphaId}
                  checkBusy={candidateWorkflowBusy}
                  onScore={onScore}
                  onSimulate={actions.startSimulation}
                  onCheck={actions.startSingleCheck}
                />
              ))}
            </div>
          )}
        </div>

        <div ref={tableContainerRef} className="hidden md:block overflow-auto" style={{ maxWidth: "100%", height: "min(640px, 70vh)" }}>
          <table className="data-table card-view" style={{ minWidth: 980 }} aria-label="候选结果">
            <thead>
              {renderHeader()}
            </thead>
            <tbody style={{ position: "relative", height: rowVirtualizer.getTotalSize() }}>
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const candidate = paginatedCandidates[virtualRow.index];
                return (
                  <CandidateRow
                    key={`${candidateIdentity(candidate)}_v_${virtualRow.index}`}
                    candidate={candidate}
                    checkResults={checkResults}
                    hasActions={hasActions}
                    canShowRowActions={canShowRowActions}
                    showProductionControls={showProductionControls}
                    candidateWorkflowBusy={candidateWorkflowBusy}
                    checkingAlphaId={pipeline.checkingAlphaId}
                    onScore={onScore}
                    onSimulate={(c) => { actions.startSimulation(c); }}
                    onCheck={actions.startSingleCheck}
                    isSelected={selectedIds.has(candidateIdentity(candidate))}
                    onToggleSelect={handleToggleSelect}
                    style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${virtualRow.start}px)` }}
                  />
                );
              })}
              {paginatedCandidates.length === 0 && (
                <tr>
                  <td colSpan={columnCount} style={{ padding: "1.5rem", textAlign: "center" }}>
                    <EmptyState filter={!!filter} showProductionControls={showProductionControls} />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <CandidateTablePagination
          currentPage={currentPage}
          totalPages={totalPages}
          visibleStart={visibleStart}
          visibleEnd={visibleEnd}
          totalItems={sortedCandidates.length}
          pageSize={PAGE_SIZE}
          onPageChange={setCurrentPage}
        />
      </div>
    </div>
  );
}

function candidateManagementDisplayCandidates(
  rows: Candidate[],
  retainedCandidates: Candidate[],
  workflowPlan?: CandidateWorkflowPlan | null,
) {
  const queued = [
    ...workflowCandidatesForQueue(rows, [], workflowPlan?.validator?.next_candidate_ids || workflowPlan?.validator?.candidate_ids),
    ...workflowCandidatesForQueue(rows, [], workflowPlan?.rework?.candidate_ids),
    ...workflowCandidatesForQueue(rows, [], workflowPlan?.review?.candidate_ids),
    ...rows.filter(candidateNeedsOptimization),
  ];
  return rankPoolCandidates(uniqueCandidatesByIdentity([...retainedCandidates, ...queued]));
}

function uniqueCandidatesByIdentity(candidates: Candidate[]) {
  const seen = new Set<string>();
  const selected: Candidate[] = [];
  for (const candidate of candidates) {
    const id = candidateIdentity(candidate) || (candidate.expression || "");
    if (!id || seen.has(id)) continue;
    seen.add(id);
    selected.push(candidate);
  }
  return selected;
}
