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

import { useCallback, useRef, useState } from "react";
import type {
  AlphaLifecycleHistoryResponse,
  AlphaLifecycleTrace,
  Candidate,
  CandidateListMeta,
  CandidateQueueView,
} from "@/types";
import {
  queueViewLabel,
  candidateIdentity,
  candidateText,
  MIN_TARGET_POOL_SIZE,
  MAX_TARGET_POOL_SIZE,
} from "./CandidateTableUtils";
import {
  QualitySummaryItem,
  LifecycleReplayPanel,
} from "./CandidateTableSubComponents";
import { CandidateDetailPanel } from "./CandidateDetailPanel";
import ErrorCard from "./ErrorCard";

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
  remoteTruncated: boolean;

  // Controls
  showProductionControls: boolean;
  candidateWorkflowBusy: boolean;
  taskState: "idle" | "loading" | "progress" | "success" | "error";
  simState: "idle" | "loading" | "progress" | "success" | "error";
  optimizationState: "idle" | "loading" | "progress" | "success" | "error";
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
    taskState: "idle" | "loading" | "progress" | "success" | "error";
    taskProgress: import("@/types").UnifiedProgress | null;
    taskError: string | null;
    taskStreamExhausted: boolean;
    onRetryTask: () => void;
    simState: "idle" | "loading" | "progress" | "success" | "error";
    simProgress: import("@/types").UnifiedProgress | null;
    simError: string | null;
    onRetrySim: () => void;
    optimizationState: "idle" | "loading" | "progress" | "success" | "error";
    optimizationProgress: import("@/types").UnifiedProgress | null;
    optimizationError: string | null;
    onRetryOptimization: () => void;
    checkState: "idle" | "loading" | "progress" | "success" | "error";
    checkProgress: import("@/types").UnifiedProgress | null;
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

// ── Export helpers ──

function exportCSV(candidates: Candidate[], filename: string): void {
  const headers = ["ID", "表达式", "家族", "状态", "总分", "Sharpe", "Fitness", "Turnover", "阻断原因"];
  const rows = candidates.map((c) => [
    candidateIdentity(c) ?? "",
    candidateText(c.expression) ?? "",
    candidateText(c.family) ?? "",
    c.status ?? "",
    c.scorecard?.total_score ?? "",
    c.scorecard?.sharpe ?? "",
    c.scorecard?.fitness ?? "",
    c.scorecard?.turnover ?? "",
    (Array.isArray(c.blocking_reasons) ? c.blocking_reasons.join(";") : "") ?? "",
  ]);
  const csv = [headers, ...rows]
    .map((r) => r.map((v) => `"${String(v ?? "")}"`).join(","))
    .join("\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportJSON(candidates: Candidate[], filename: string): void {
  const json = JSON.stringify(candidates, null, 2);
  const blob = new Blob([json], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
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
  selectedIds,
  selectedCount,
  onClearSelection,
  onBatchScore,
  onBatchCheck,
  onBatchSimulate,
  sortedCandidates,
}: CandidateTableToolbarProps) {
  const [exportOpen, setExportOpen] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);

  const handleExportCSV = useCallback(() => {
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    exportCSV(sortedCandidates, `candidates_${ts}.csv`);
    setExportOpen(false);
  }, [sortedCandidates]);

  const handleExportJSON = useCallback(() => {
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    exportJSON(sortedCandidates, `candidates_${ts}.json`);
    setExportOpen(false);
  }, [sortedCandidates]);

  return (
    <>
      <h1 className="text-xl font-medium text-text-primary mb-1">{title}</h1>
      <p className="text-sm text-text-tertiary mb-4" role="status" aria-live="polite">
        {viewMode === "candidates"
          ? `主池 ${retainedCount}/${targetPoolSize} · 可推进 ${poolEligibleCount} · 历史 ${rawQueueCount}`
          : `显示 ${sortedCount} / ${rawQueueCount} 个候选`}
        {candidateMeta.total > 0 && ` · 已返回 ${candidateMeta.returned}/${candidateMeta.total}`}
        {viewMode !== "candidates" && ` · ${queueViewLabel(viewMode)}`}
        {filter && " · 已过滤"}
      </p>

      {/* Batch selection bar */}
      {selectedCount > 0 && (
        <div
          className="mb-4 px-3 py-2 rounded-md flex flex-wrap items-center gap-3"
          style={{
            background: "var(--color-batch-select-bg)",
            border: "1px solid var(--color-batch-select-border)",
          }}
          role="status"
          aria-live="polite"
        >
          <span className="text-sm font-medium text-text-primary">
            已选 <span className="font-mono-value text-accent">{selectedCount}</span> 个
          </span>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={candidateWorkflowBusy || selectedCount === 0}
            aria-busy={candidateWorkflowBusy}
            onClick={onBatchScore}
          >
            批量评分
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={candidateWorkflowBusy || selectedCount === 0}
            aria-busy={candidateWorkflowBusy}
            onClick={onBatchCheck}
          >
            批量补查
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={candidateWorkflowBusy || selectedCount === 0}
            aria-busy={candidateWorkflowBusy}
            onClick={onBatchSimulate}
          >
            批量补模拟
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onClearSelection}
          >
            取消选择
          </button>
        </div>
      )}

      {showProductionControls && (
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <label className="flex items-center gap-2 text-sm font-medium text-text-secondary">
            目标池容量
            <input
              type="number"
              min={MIN_TARGET_POOL_SIZE}
              max={MAX_TARGET_POOL_SIZE}
              value={targetPoolSize}
              disabled={candidateWorkflowBusy}
              onChange={(event) => onTargetPoolSizeChange(event.target.value)}
              className="form-input w-20"
            />
          </label>
          <button
            type="button"
            onClick={onGenerateCandidates}
            disabled={candidateWorkflowBusy}
            aria-busy={taskState === "loading" || taskState === "progress"}
            className="btn btn-primary btn-sm"
            title="自动维护目标池容量，并在非提交边界内继续官方模拟与质量检查"
          >
            {taskState === "loading" || taskState === "progress" ? "推进中..." : "自动推进候选池"}
          </button>
          <button
            type="button"
            onClick={onStartValidationQueue}
            disabled={candidateWorkflowBusy}
            aria-busy={simState === "loading" || simState === "progress"}
            className="btn btn-secondary btn-sm"
            title="自动推进中断或单批证据缺失时使用；按 Top3 进入官方模拟后自动接质量门槛检查，不执行真实 Alpha submit"
          >
            {simState === "loading" || simState === "progress" ? "模拟中..." : "运行官方验证队列"}
          </button>
          <button
            type="button"
            onClick={onStartOptimization}
            disabled={candidateWorkflowBusy}
            aria-busy={optimizationState === "loading" || optimizationState === "progress"}
            className="btn btn-secondary btn-sm"
            title="根据服务端返工队列进行本地优化；不会携带凭据，也不会提交 Alpha"
          >
            {optimizationState === "loading" || optimizationState === "progress" ? "优化中..." : "优化返工队列"}
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
        <QualitySummaryItem label="主池保留" value={String(qualitySummary.retained)} />
        <QualitySummaryItem label="可推进" value={String(qualitySummary.promotable)} />
        <QualitySummaryItem label="需优化" value={String(qualitySummary.rework)} />
        <QualitySummaryItem label="阻断" value={String(qualitySummary.blocked)} />
        <QualitySummaryItem label="输出模式" value={qualitySummary.outputMode} />
      </div>

      <LifecycleReplayPanel
        history={lifecycleHistory}
        error={lifecycleError}
        loading={lifecycleLoading}
        filterActive={Boolean(filter.trim())}
        visibleTraces={visibleLifecycleTraces}
      />

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
        <div className="mb-4 px-3 py-2 text-xs rounded-md bg-warning-subtle text-warning" role="status" aria-live="polite">
          当前接口返回 {candidateMeta.returned} 条候选，服务端报告总量为 {candidateMeta.total} 条；请刷新或切换到完整候选源，避免把当前列表误认为全集。
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

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <input
          type="text"
          aria-label="过滤候选"
          placeholder="按表达式、家族、ID、质量原因搜索..."
          value={filter}
          maxLength={200}
          onChange={(event) => onFilterChange(event.target.value)}
          className="form-input flex-1"
        />
        <button type="button" onClick={onRetryLoad} disabled={apiLoading} aria-busy={apiLoading} className="btn btn-secondary btn-sm">
          {apiLoading ? "刷新中..." : "刷新"}
        </button>
        {onToggleStarFilter && (
          <button
            type="button"
            onClick={onToggleStarFilter}
            className={`btn btn-sm ${showStarredOnly ? "btn-primary" : "btn-secondary"}`}
            title={showStarredOnly ? "显示全部候选" : "仅显示收藏"}
          >
            ⭐ {showStarredOnly ? "收藏中" : "仅收藏"}
          </button>
        )}
        {/* Export dropdown */}
        <div ref={exportRef} style={{ position: "relative" }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={sortedCandidates.length === 0}
            onClick={() => setExportOpen((v) => !v)}
            aria-haspopup="true"
            aria-expanded={exportOpen}
          >
            导出 ▾
          </button>
          {exportOpen && (
            <div
              className="dropdown-menu"
              style={{
                position: "absolute",
                right: 0,
                top: "100%",
                marginTop: 4,
                zIndex: 50,
                minWidth: 120,
                background: "var(--color-divider)",
                border: "1px solid var(--color-scrollbar-thumb)",
                borderRadius: 6,
                padding: "4px 0",
                boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
              }}
            >
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 12px" }}
                onClick={handleExportCSV}
              >
                CSV
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ display: "block", width: "100%", textAlign: "left", padding: "6px 12px" }}
                onClick={handleExportJSON}
              >
                JSON
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
