/**
 * CandidateTable toolbar area.
 *
 * Contains:
 * - Title & pool statistics
 * - Batch selection bar (visible when candidates are selected)
 * - Production controls (pool size, auto-advance, validation queue, optimization)
 * - Quality summary KPI cards
 * - Lifecycle replay panel
 * - Remote truncated / load error warnings
 * - Filter input + refresh button + star filter + export dropdown
 *
 * Extracted from CandidateTable.tsx.
 */

import type {
  AlphaLifecycleHistoryResponse,
  AlphaLifecycleTrace,
  Candidate,
  CandidateListMeta,
  CandidateQueueView,
} from '@/types';
import { LifecycleReplayPanel } from './CandidateTableSubComponents';
import { CandidateDetailPanel } from './CandidateDetailPanel';
import ErrorCard from './ErrorCard';
import { ToolbarTitleStats } from './CandidateTableToolbarTitleStats';
import { ProductionControls } from './CandidateTableToolbarProductionControls';
import { QualitySummaryBar } from './CandidateTableToolbarQualitySummaryBar';
import { FilterToolbar } from './CandidateTableToolbarFilterToolbar';

export interface QualitySummaryData {
  ready?: number;
  retained: string;
  promotable: number;
  rework: number;
  blocked: number;
  outputMode: string;
}

export interface CandidateTableToolbarProps {
  // Title & stats
  title: string;
  viewMode: CandidateQueueView;
  retainedCount: number;
  targetPoolSize: number;
  poolEligibleCount: number;
  rawQueueCount: number;
  sortedCount: number;
  candidateMeta: CandidateListMeta;
  filter: string;
  /** The raw input value from the user (before debounce) */
  filterInput?: string;
  remoteTruncated: boolean;
  /** When true, render the structural skeleton (no functional lifecycle replay). */
  skeleton?: boolean;

  // Controls
  showProductionControls: boolean;
  candidateWorkflowBusy: boolean;
  taskState: 'idle' | 'loading' | 'progress' | 'success' | 'error';
  simState: 'idle' | 'loading' | 'progress' | 'success' | 'error';
  optimizationState: 'idle' | 'loading' | 'progress' | 'success' | 'error';
  onTargetPoolSizeChange: (value: string) => void;
  onGenerateCandidates: () => void;
  onStartValidationQueue: () => void;
  onStartOptimization: () => void;

  // Quality summary
  qualitySummary: QualitySummaryData;

  // Lifecycle replay
  lifecycleHistory: AlphaLifecycleHistoryResponse | null;
  lifecycleError: string | null;
  lifecycleLoading: boolean;
  visibleLifecycleTraces: AlphaLifecycleTrace[];

  // Progress detail panels
  detailPanel: {
    showProductionControls: boolean;
    taskState: 'idle' | 'loading' | 'progress' | 'success' | 'error';
    taskProgress: import('@/types').UnifiedProgress | null;
    taskError: string | null;
    taskStreamExhausted: boolean;
    onRetryTask: () => void;
    simState: 'idle' | 'loading' | 'progress' | 'success' | 'error';
    simProgress: import('@/types').UnifiedProgress | null;
    simError: string | null;
    onRetrySim: () => void;
    optimizationState: 'idle' | 'loading' | 'progress' | 'success' | 'error';
    optimizationProgress: import('@/types').UnifiedProgress | null;
    optimizationError: string | null;
    onRetryOptimization: () => void;
    checkState: 'idle' | 'loading' | 'progress' | 'success' | 'error';
    checkProgress: import('@/types').UnifiedProgress | null;
    checkError: string | null;
    onRetryCheck: () => void;
  };

  // Load state
  loadError: string | null;
  apiLoading: boolean;
  onRetryLoad: () => void;

  // Filter
  onFilterChange: (value: string) => void;

  // P2-2: Star filter
  showStarredOnly?: boolean;
  onToggleStarFilter?: () => void;

  // Batch selection
  selectedIds: Set<string>;
  selectedCount: number;
  onClearSelection: () => void;
  onBatchScore: () => void;
  onBatchCheck: () => void;
  onBatchSimulate: () => void;

  // Export
  sortedCandidates: Candidate[];
}

export function CandidateTableToolbar({
  title,
  viewMode,
  retainedCount,
  targetPoolSize,
  poolEligibleCount,
  rawQueueCount,
  sortedCount,
  candidateMeta,
  filter,
  filterInput,
  remoteTruncated,
  showProductionControls,
  candidateWorkflowBusy,
  taskState,
  simState,
  optimizationState,
  onTargetPoolSizeChange,
  onGenerateCandidates,
  onStartValidationQueue,
  onStartOptimization,
  qualitySummary,
  lifecycleHistory,
  lifecycleError,
  lifecycleLoading,
  visibleLifecycleTraces,
  detailPanel,
  loadError,
  apiLoading,
  onRetryLoad,
  onFilterChange,
  showStarredOnly = false,
  onToggleStarFilter,
  selectedCount,
  onClearSelection,
  onBatchScore,
  onBatchCheck,
  onBatchSimulate,
  sortedCandidates,
  skeleton = false,
}: CandidateTableToolbarProps) {
  return (
    <>
      <ToolbarTitleStats
        title={title}
        viewMode={viewMode}
        retainedCount={retainedCount}
        targetPoolSize={targetPoolSize}
        poolEligibleCount={poolEligibleCount}
        rawQueueCount={rawQueueCount}
        sortedCount={sortedCount}
        candidateMeta={candidateMeta}
        filter={filter}
        selectedCount={selectedCount}
        candidateWorkflowBusy={candidateWorkflowBusy}
        onClearSelection={onClearSelection}
        onBatchScore={onBatchScore}
        onBatchCheck={onBatchCheck}
        onBatchSimulate={onBatchSimulate}
      />

      {showProductionControls && (
        <ProductionControls
          targetPoolSize={targetPoolSize}
          candidateWorkflowBusy={candidateWorkflowBusy}
          taskState={taskState}
          simState={simState}
          optimizationState={optimizationState}
          onTargetPoolSizeChange={onTargetPoolSizeChange}
          onGenerateCandidates={onGenerateCandidates}
          onStartValidationQueue={onStartValidationQueue}
          onStartOptimization={onStartOptimization}
        />
      )}

      <QualitySummaryBar qualitySummary={qualitySummary} />

      {!skeleton && (
        <LifecycleReplayPanel
          history={lifecycleHistory}
          error={lifecycleError}
          loading={lifecycleLoading}
          filterActive={Boolean(filter.trim())}
          visibleTraces={visibleLifecycleTraces}
        />
      )}

      <CandidateDetailPanel
        showProductionControls={detailPanel.showProductionControls}
        taskState={detailPanel.taskState}
        taskProgress={detailPanel.taskProgress}
        taskError={detailPanel.taskError}
        taskStreamExhausted={detailPanel.taskStreamExhausted}
        onRetryTask={detailPanel.onRetryTask}
        simState={detailPanel.simState}
        simProgress={detailPanel.simProgress}
        simError={detailPanel.simError}
        onRetrySim={detailPanel.onRetrySim}
        optimizationState={detailPanel.optimizationState}
        optimizationProgress={detailPanel.optimizationProgress}
        optimizationError={detailPanel.optimizationError}
        onRetryOptimization={detailPanel.onRetryOptimization}
        checkState={detailPanel.checkState}
        checkProgress={detailPanel.checkProgress}
        checkError={detailPanel.checkError}
        onRetryCheck={detailPanel.onRetryCheck}
      />

      {remoteTruncated && (
        <div
          className="mb-4 px-3 py-2 text-xs rounded-md bg-warning-subtle text-warning"
          role="status"
          aria-live="polite"
        >
          当前接口返回 {candidateMeta.returned} 条候选，服务端报告总量为 {candidateMeta.total}{' '}
          条；请刷新或切换到完整候选源，避免把当前列表误认为全集。
        </div>
      )}

      {loadError && (
        <ErrorCard
          title="加载候选失败"
          details={loadError}
          severity="error"
          onRetry={onRetryLoad}
          className="mb-4"
        />
      )}

      <FilterToolbar
        filter={filter}
        filterInput={filterInput}
        apiLoading={apiLoading}
        onFilterChange={onFilterChange}
        onRetryLoad={onRetryLoad}
        showStarredOnly={showStarredOnly}
        onToggleStarFilter={onToggleStarFilter}
        sortedCandidates={sortedCandidates}
      />
    </>
  );
}
