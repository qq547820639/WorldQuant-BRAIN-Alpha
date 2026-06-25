import { useCallback, useEffect, useMemo } from 'react';
import { useApi } from '@/hooks/useApi';
import { useGlobalData } from '@/hooks/useGlobalData';
import { useCandidatePipeline } from '@/hooks/useCandidatePipeline';
import { useSseManager } from '@/hooks/useSseManager';
import { useCandidateActions } from '@/hooks/useCandidateActions';
import { useCandidateTableState, PAGE_SIZE } from '@/hooks/useCandidateTableState';
import { useCandidateTableData } from '@/hooks/useCandidateTableData';
import type { AlphaLifecycleHistoryResponse, Candidate } from '@/types';
import {
  candidateIdentity,
  queueViewLabel,
  CandidateCheckResult,
  CandidateQueueView,
} from './CandidateTableUtils';
import CandidateTablePagination from './CandidateTablePagination';
import { CandidateTableToolbar } from './CandidateTableToolbar';
import type { QualitySummaryData } from './CandidateTableToolbar';
import CandidateTableDesktop from './CandidateTableDesktop';
import CandidateTableMobile from './CandidateTableMobile';
import CandidateTableLoading from './CandidateTableLoading';

interface Props {
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  onScore?: (candidate: Candidate) => void;
  showProductionControls?: boolean;
  showRowActions?: boolean;
  credentials?: import('@/types').BrainCredentials;
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
  viewMode = 'candidates',
}: Props) {
  const { candidates: globalCandidates, refreshAll } = useGlobalData();
  const actionApi = useApi<{ ok?: boolean; job_id?: string; task_id?: string; error?: string }>();
  const checkResultsApi = useApi<{ items?: CandidateCheckResult[] }>();
  const lifecycleApi = useApi<AlphaLifecycleHistoryResponse>();
  const singleCheckApi = useApi<CandidateCheckResult>();
  const batchCheckApi = useApi<{
    ok?: boolean;
    job_id?: string;
    task_id?: string;
    error?: string;
  }>();
  const callApi = actionApi.call;
  const callCheckResultsApi = checkResultsApi.call;
  const callLifecycleApi = lifecycleApi.call;
  const callSingleCheckApi = singleCheckApi.call;
  const callBatchCheckApi = batchCheckApi.call;

  const pipeline = useCandidatePipeline();
  const sseManager = useSseManager();

  const tableState = useCandidateTableState({
    totalItems: 0,
    viewMode,
  });

  const tableData = useCandidateTableData({
    globalCandidatesData: globalCandidates.data,
    refreshAll,
    callCheckResultsApi,
    callLifecycleApi,
    notify,
    viewMode,
    targetPoolSize: tableState.targetPoolSize,
    filter: tableState.filter,
    showStarredOnly: tableState.showStarredOnly,
    sortKey: tableState.sortKey,
    sortAsc: tableState.sortAsc,
    currentPage: tableState.currentPage,
    lifecycleLoading: lifecycleApi.loading,
  });

  const {
    candidates,
    serverMainPoolCandidates,
    serverWorkflowPlan,
    candidateMeta,
    checkResults,
    lifecycleHistory,
    lifecycleError,
    poolEligibleCandidates,
    retainedPoolCandidates,
    rawQueueCandidates,
    visibleLifecycleTraces,
    sortedCandidates,
    qualitySummary,
    paginatedCandidates,
    currentPageIds,
    remoteTruncated,
    loadCandidates,
    refreshCheckResults,
  } = tableData;

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
    targetPoolSize: tableState.targetPoolSize,
  });

  useEffect(() => {
    if (pipeline.task.jobId) {
      sseManager.connect('task', `/sse?job_id=${encodeURIComponent(pipeline.task.jobId)}`, {
        onEvent: actions.handleTaskEvent,
        onExhausted: actions.handleTaskStreamExhausted,
      });
    } else {
      sseManager.disconnect('task');
    }

    if (pipeline.check.jobId) {
      sseManager.connect('check', `/sse?job_id=${encodeURIComponent(pipeline.check.jobId)}`, {
        onEvent: actions.handleCheckEvent,
        onExhausted: actions.handleCheckStreamExhausted,
      });
    } else {
      sseManager.disconnect('check');
    }

    if (pipeline.optimization.jobId) {
      sseManager.connect(
        'optimization',
        `/sse?job_id=${encodeURIComponent(pipeline.optimization.jobId)}`,
        {
          onEvent: actions.handleOptimizationEvent,
          onExhausted: actions.handleOptimizationStreamExhausted,
        }
      );
    } else {
      sseManager.disconnect('optimization');
    }

    if (pipeline.simulation.jobId) {
      sseManager.connect(
        'simulation',
        `/sse?job_id=${encodeURIComponent(pipeline.simulation.jobId)}`,
        {
          onEvent: actions.handleSimEvent,
          onExhausted: actions.handleSimStreamExhausted,
        }
      );
    } else {
      sseManager.disconnect('simulation');
    }
  }, [
    pipeline.task.jobId,
    pipeline.check.jobId,
    pipeline.optimization.jobId,
    pipeline.simulation.jobId,
    actions.handleTaskEvent,
    actions.handleTaskStreamExhausted,
    actions.handleCheckEvent,
    actions.handleCheckStreamExhausted,
    actions.handleOptimizationEvent,
    actions.handleOptimizationStreamExhausted,
    actions.handleSimEvent,
    actions.handleSimStreamExhausted,
    sseManager,
  ]);

  const candidateWorkflowBusy =
    pipeline.task.state === 'loading' ||
    pipeline.task.state === 'progress' ||
    pipeline.simulation.state === 'loading' ||
    pipeline.simulation.state === 'progress' ||
    pipeline.optimization.state === 'loading' ||
    pipeline.optimization.state === 'progress' ||
    pipeline.check.state === 'loading' ||
    pipeline.check.state === 'progress';

  const handleBatchScore = useCallback(() => {
    if (!onScore) return;
    const selected = sortedCandidates.filter((c) =>
      tableState.selectedIds.has(candidateIdentity(c))
    );
    selected.forEach((c) => onScore(c));
  }, [onScore, tableState.selectedIds, sortedCandidates]);

  const handleBatchCheck = useCallback(() => {
    const selected = sortedCandidates.filter((c) =>
      tableState.selectedIds.has(candidateIdentity(c))
    );
    if (selected.length > 0) {
      void actions.startBatchCheck(selected);
    }
  }, [tableState.selectedIds, sortedCandidates, actions.startBatchCheck]);

  const handleBatchSimulate = useCallback(() => {
    const selected = sortedCandidates.filter((c) =>
      tableState.selectedIds.has(candidateIdentity(c))
    );
    if (selected.length > 0) {
      actions.startSimulation(undefined, selected);
    }
  }, [tableState.selectedIds, sortedCandidates, actions.startSimulation]);

  const loading = globalCandidates.loading;
  const loadError = globalCandidates.error;
  const title = viewMode === 'candidates' ? '候选管理' : `${queueViewLabel(viewMode)}候选`;

  const detailPanelProps = useMemo(
    () => ({
      showProductionControls,
      taskState: pipeline.task.state,
      taskProgress: pipeline.task.progress,
      taskError: pipeline.task.error,
      taskStreamExhausted: sseManager.task.exhausted,
      onRetryTask: () => {
        void actions.generateCandidates();
      },
      simState: pipeline.simulation.state,
      simProgress: pipeline.simulation.progress,
      simError: pipeline.simulation.error,
      onRetrySim: () => {
        actions.startSimulation();
      },
      optimizationState: pipeline.optimization.state,
      optimizationProgress: pipeline.optimization.progress,
      optimizationError: pipeline.optimization.error,
      onRetryOptimization: () => {
        void actions.startOptimization();
      },
      checkState: pipeline.check.state,
      checkProgress: pipeline.check.progress,
      checkError: pipeline.check.error,
      onRetryCheck: () => {
        void actions.startBatchCheck(actions.lastBatchCheckCandidatesRef.current || undefined);
      },
    }),
    [
      showProductionControls,
      pipeline.task.state,
      pipeline.task.progress,
      pipeline.task.error,
      sseManager.task.exhausted,
      actions.generateCandidates,
      pipeline.simulation.state,
      pipeline.simulation.progress,
      pipeline.simulation.error,
      actions.startSimulation,
      pipeline.optimization.state,
      pipeline.optimization.progress,
      pipeline.optimization.error,
      actions.startOptimization,
      pipeline.check.state,
      pipeline.check.progress,
      pipeline.check.error,
      actions.startBatchCheck,
      actions.lastBatchCheckCandidatesRef,
    ]
  );

  const totalPages = Math.max(1, Math.ceil(sortedCandidates.length / PAGE_SIZE));

  if (loading) {
    return (
      <CandidateTableLoading
        title={title}
        viewMode={viewMode}
        targetPoolSize={tableState.targetPoolSize}
        showProductionControls={showProductionControls}
        onTargetPoolSizeChange={tableState.handleTargetPoolSizeChange}
        onRetryLoad={loadCandidates}
      />
    );
  }

  return (
    <div className="animate-fade-in">
      <CandidateTableToolbar
        title={title}
        viewMode={viewMode}
        retainedCount={retainedPoolCandidates.length}
        targetPoolSize={tableState.targetPoolSize}
        poolEligibleCount={poolEligibleCandidates.length}
        rawQueueCount={rawQueueCandidates.length}
        sortedCount={sortedCandidates.length}
        candidateMeta={candidateMeta}
        filter={tableState.filter}
        filterInput={tableState.filterInput}
        remoteTruncated={remoteTruncated}
        showProductionControls={showProductionControls}
        candidateWorkflowBusy={candidateWorkflowBusy}
        taskState={pipeline.task.state}
        simState={pipeline.simulation.state}
        optimizationState={pipeline.optimization.state}
        onTargetPoolSizeChange={tableState.handleTargetPoolSizeChange}
        onGenerateCandidates={() => {
          void actions.generateCandidates();
        }}
        onStartValidationQueue={actions.startOfficialValidationQueue}
        onStartOptimization={() => {
          void actions.startOptimization();
        }}
        qualitySummary={qualitySummary}
        lifecycleHistory={lifecycleHistory}
        lifecycleError={lifecycleError}
        lifecycleLoading={lifecycleApi.loading}
        visibleLifecycleTraces={visibleLifecycleTraces}
        detailPanel={detailPanelProps}
        loadError={loadError}
        apiLoading={globalCandidates.loading}
        onRetryLoad={loadCandidates}
        onFilterChange={tableState.handleFilterChange}
        showStarredOnly={tableState.showStarredOnly}
        onToggleStarFilter={tableState.handleToggleStarFilter}
        selectedIds={tableState.selectedIds}
        selectedCount={tableState.selectedCount}
        onClearSelection={tableState.handleClearSelection}
        onBatchScore={handleBatchScore}
        onBatchCheck={handleBatchCheck}
        onBatchSimulate={handleBatchSimulate}
        sortedCandidates={sortedCandidates}
      />

      <div className="panel">
        {pipeline.task.state === 'success' && pipeline.taskSuccessBanner && (
          <div
            className="panel-body-padded"
            style={{
              borderBottom: '0.5px solid var(--color-border-default)',
              background: 'var(--color-task-success-bg)',
              borderLeft: '3px solid var(--color-sparkline-dot)',
              margin: 0,
            }}
            role="status"
            aria-live="polite"
          >
            <div
              style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 16px' }}
            >
              <span style={{ fontSize: 14, marginRight: 4 }}>✅</span>
              <span className="text-sm font-medium text-text-primary">候选池自动推进完成</span>
              <span className="text-xs text-text-secondary">
                新增{' '}
                <span className="font-mono-value text-positive">
                  {pipeline.taskSuccessBanner.newCount}
                </span>{' '}
                个候选
              </span>
              {pipeline.taskSuccessBanner.optimizedCount > 0 && (
                <span className="text-xs text-text-secondary">
                  优化{' '}
                  <span className="font-mono-value text-accent">
                    {pipeline.taskSuccessBanner.optimizedCount}
                  </span>{' '}
                  个
                </span>
              )}
              <span className="text-xs text-text-tertiary">
                当前池状态：
                <span className="font-mono-value text-text-primary">
                  {retainedPoolCandidates.length}/{tableState.targetPoolSize}
                </span>
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

        <CandidateTableMobile
          candidates={paginatedCandidates}
          checkResults={checkResults}
          onScore={onScore}
          onSimulate={actions.startSimulation}
          onCheck={actions.startSingleCheck}
          showRowActions={showRowActions}
          showProductionControls={showProductionControls}
          workflowBusy={candidateWorkflowBusy}
          checkingAlphaId={pipeline.checkingAlphaId}
          filter={tableState.filter}
          onClearFilter={() => tableState.setFilterInput('')}
          onGenerateCandidates={() => {
            void actions.generateCandidates();
          }}
        />

        <CandidateTableDesktop
          candidates={paginatedCandidates}
          checkResults={checkResults}
          selectedIds={tableState.selectedIds}
          onToggleSelect={tableState.handleToggleSelect}
          onToggleSelectAll={tableState.handleToggleSelectAll}
          sortKey={tableState.sortKey}
          sortAsc={tableState.sortAsc}
          onSort={tableState.handleSort}
          onScore={onScore}
          onSimulate={(c) => {
            actions.startSimulation(c);
          }}
          onCheck={actions.startSingleCheck}
          showRowActions={showRowActions}
          showProductionControls={showProductionControls}
          workflowBusy={candidateWorkflowBusy}
          checkingAlphaId={pipeline.checkingAlphaId}
          allCurrentPageIds={currentPageIds}
          filter={tableState.filter}
          onClearFilter={() => tableState.setFilterInput('')}
          onGenerateCandidates={() => {
            void actions.generateCandidates();
          }}
        />

        <CandidateTablePagination
          currentPage={tableState.currentPage}
          totalPages={totalPages}
          visibleStart={tableState.visibleStart}
          visibleEnd={tableState.visibleEnd}
          totalItems={sortedCandidates.length}
          pageSize={PAGE_SIZE}
          onPageChange={tableState.setCurrentPage}
        />
      </div>
    </div>
  );
}
