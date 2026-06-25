import type { CandidateListMeta, CandidateQueueView } from '@/types';
import { queueViewLabel } from './CandidateTableUtils';

export interface ToolbarTitleStatsProps {
  title: string;
  viewMode: CandidateQueueView;
  retainedCount: number;
  targetPoolSize: number;
  poolEligibleCount: number;
  rawQueueCount: number;
  sortedCount: number;
  candidateMeta: CandidateListMeta;
  filter: string;
  selectedCount: number;
  candidateWorkflowBusy: boolean;
  onClearSelection: () => void;
  onBatchScore: () => void;
  onBatchCheck: () => void;
  onBatchSimulate: () => void;
}

export function ToolbarTitleStats({
  title,
  viewMode,
  retainedCount,
  targetPoolSize,
  poolEligibleCount,
  rawQueueCount,
  sortedCount,
  candidateMeta,
  filter,
  selectedCount,
  candidateWorkflowBusy,
  onClearSelection,
  onBatchScore,
  onBatchCheck,
  onBatchSimulate,
}: ToolbarTitleStatsProps) {
  return (
    <>
      <h1 className="text-xl font-medium text-text-primary mb-1">{title}</h1>
      <p className="text-sm text-text-tertiary mb-4" role="status" aria-live="polite">
        {viewMode === 'candidates'
          ? `主池 ${retainedCount}/${targetPoolSize} · 可推进 ${poolEligibleCount} · 历史 ${rawQueueCount}`
          : `显示 ${sortedCount} / ${rawQueueCount} 个候选`}
        {candidateMeta.total > 0 && ` · 已返回 ${candidateMeta.returned}/${candidateMeta.total}`}
        {viewMode !== 'candidates' && ` · ${queueViewLabel(viewMode)}`}
        {filter && ' · 已过滤'}
      </p>

      {selectedCount > 0 && (
        <div
          className="mb-4 px-3 py-2 rounded-md flex flex-wrap items-center gap-3"
          style={{
            background: 'var(--color-batch-select-bg)',
            border: '1px solid var(--color-batch-select-border)',
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
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClearSelection}>
            取消选择
          </button>
        </div>
      )}
    </>
  );
}
