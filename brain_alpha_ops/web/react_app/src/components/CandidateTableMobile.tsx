import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { Candidate, CandidateCheckResult } from '@/types';
import { candidateIdentity } from './CandidateTableUtils';
import { CandidateMobileCard } from './CandidateTableSubComponents';
import EmptyState from './EmptyState';

interface CandidateTableMobileProps {
  candidates: Candidate[];
  checkResults: Map<string, CandidateCheckResult>;
  onScore?: (candidate: Candidate) => void;
  onSimulate: (candidate: Candidate) => void;
  onCheck: (candidate: Candidate) => void;
  showRowActions: boolean;
  showProductionControls: boolean;
  workflowBusy: boolean;
  checkingAlphaId: string | null;
  filter: string;
  onClearFilter: () => void;
  onGenerateCandidates: () => void;
}

const ESTIMATED_MOBILE_CARD_HEIGHT = 160;

export default function CandidateTableMobile({
  candidates,
  checkResults,
  onScore,
  onSimulate,
  onCheck,
  showRowActions,
  showProductionControls,
  workflowBusy,
  checkingAlphaId,
  filter,
  onClearFilter,
  onGenerateCandidates,
}: CandidateTableMobileProps) {
  const canShowRowActions = showRowActions && Boolean(onScore);
  const mobileContainerRef = useRef<HTMLDivElement>(null);
  const mobileVirtualizer = useVirtualizer({
    count: candidates.length,
    getScrollElement: () => mobileContainerRef.current,
    estimateSize: () => ESTIMATED_MOBILE_CARD_HEIGHT,
    overscan: 10,
  });

  return (
    <div
      ref={mobileContainerRef}
      className="panel-body md:hidden overflow-auto"
      style={{ height: 'min(640px, 70vh)' }}
    >
      {candidates.length === 0 ? (
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
            <button type="button" className="btn btn-secondary btn-sm" onClick={onClearFilter}>
              清除筛选
            </button>
          ) : showProductionControls ? (
            <button type="button" className="btn btn-primary btn-sm" onClick={onGenerateCandidates}>
              启动自动推进
            </button>
          ) : null}
        </EmptyState>
      ) : (
        <div style={{ position: 'relative', height: mobileVirtualizer.getTotalSize() }}>
          {mobileVirtualizer.getVirtualItems().map((virtualItem) => {
            const candidate = candidates[virtualItem.index];
            return (
              <CandidateMobileCard
                key={`${candidateIdentity(candidate)}_mobile_${virtualItem.index}`}
                candidate={candidate}
                checkResults={checkResults}
                canShowRowActions={canShowRowActions}
                canSimulate={showProductionControls}
                canCheck={showProductionControls}
                workflowBusy={workflowBusy}
                simulationBusy={workflowBusy}
                checkingAlphaId={checkingAlphaId}
                checkBusy={workflowBusy}
                onScore={onScore}
                onSimulate={onSimulate}
                onCheck={onCheck}
                cardRef={(node) => {
                  if (node) mobileVirtualizer.measureElement(node);
                }}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${virtualItem.start}px)`,
                }}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
