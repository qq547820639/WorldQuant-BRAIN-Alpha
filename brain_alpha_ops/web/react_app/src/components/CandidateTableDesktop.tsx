import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { Candidate, CandidateCheckResult } from '@/types';
import { candidateIdentity } from './CandidateTableUtils';
import { CandidateRow } from './CandidateRow';
import { useCandidateColumns } from './useCandidateColumns';
import EmptyState from './EmptyState';

type SortKey = 'score' | 'status' | 'created';

interface CandidateTableDesktopProps {
  candidates: Candidate[];
  checkResults: Map<string, CandidateCheckResult>;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onToggleSelectAll: (ids: string[]) => void;
  sortKey: SortKey;
  sortAsc: boolean;
  onSort: (key: SortKey) => void;
  onScore?: (candidate: Candidate) => void;
  onSimulate: (candidate: Candidate) => void;
  onCheck: (candidate: Candidate) => void;
  showRowActions: boolean;
  showProductionControls: boolean;
  workflowBusy: boolean;
  checkingAlphaId: string | null;
  allCurrentPageIds: string[];
  filter: string;
  onClearFilter: () => void;
  onGenerateCandidates: () => void;
}

const ESTIMATED_ROW_HEIGHT = 48;

export default function CandidateTableDesktop({
  candidates,
  checkResults,
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
  sortKey,
  sortAsc,
  onSort,
  onScore,
  onSimulate,
  onCheck,
  showRowActions,
  showProductionControls,
  workflowBusy,
  checkingAlphaId,
  allCurrentPageIds,
  filter,
  onClearFilter,
  onGenerateCandidates,
}: CandidateTableDesktopProps) {
  const canShowRowActions = showRowActions && Boolean(onScore);
  const hasActions = canShowRowActions || showProductionControls;

  const { columnCount, renderHeader } = useCandidateColumns({
    sortKey,
    sortAsc,
    hasActions,
    checkResults,
    canShowRowActions,
    showProductionControls,
    candidateWorkflowBusy: workflowBusy,
    checkingAlphaId,
    onSort,
    onScore,
    onSimulate,
    onCheck,
    allCurrentPageIds,
    selectedIds,
    onToggleSelectAll,
    onToggleSelect,
  });

  const tableContainerRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: candidates.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 10,
  });

  return (
    <div
      ref={tableContainerRef}
      className="hidden md:block overflow-auto"
      style={{ maxWidth: '100%', height: 'min(640px, 70vh)' }}
    >
      <table className="data-table card-view" style={{ minWidth: 980 }} aria-label="候选结果">
        <thead>{renderHeader()}</thead>
        <tbody style={{ position: 'relative', height: rowVirtualizer.getTotalSize() }}>
          {rowVirtualizer.getVirtualItems().map((virtualRow) => {
            const candidate = candidates[virtualRow.index];
            return (
              <CandidateRow
                key={`${candidateIdentity(candidate)}_v_${virtualRow.index}`}
                candidate={candidate}
                checkResults={checkResults}
                hasActions={hasActions}
                canShowRowActions={canShowRowActions}
                showProductionControls={showProductionControls}
                candidateWorkflowBusy={workflowBusy}
                checkingAlphaId={checkingAlphaId}
                onScore={onScore}
                onSimulate={onSimulate}
                onCheck={onCheck}
                isSelected={selectedIds.has(candidateIdentity(candidate))}
                onToggleSelect={onToggleSelect}
                rowRef={(node) => {
                  if (node) rowVirtualizer.measureElement(node);
                }}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              />
            );
          })}
          {candidates.length === 0 && (
            <tr>
              <td colSpan={columnCount} style={{ padding: '1.5rem', textAlign: 'center' }}>
                <EmptyState
                  title={filter ? '没有匹配的候选' : '暂无候选记录'}
                  description={
                    filter
                      ? '尝试调整筛选条件，或清除筛选查看全部候选。'
                      : showProductionControls
                        ? '候选 Alpha 通过顶部「自动推进候选池」启动生产搜索、预筛与本地排序；官方验证队列和质量检查单独推进。全流程保持非提交边界，提交仍需人工确认。'
                        : '请先运行非提交验证产生候选，或从候选管理页面选择一个候选进入评分。'
                  }
                >
                  {filter ? (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={onClearFilter}
                    >
                      清除筛选
                    </button>
                  ) : showProductionControls ? (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={onGenerateCandidates}
                    >
                      启动自动推进
                    </button>
                  ) : null}
                </EmptyState>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
