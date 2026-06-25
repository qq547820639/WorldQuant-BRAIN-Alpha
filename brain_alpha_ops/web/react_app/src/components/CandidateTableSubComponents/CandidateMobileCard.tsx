import { useCallback, useState, memo } from 'react';
import type { Candidate } from '@/types';
import { isStarred, toggleStar } from '@/utils/starredCandidates';
import {
  candidateBlockerText,
  candidateIdentity,
  candidateOutputDetail,
  candidateOutputSummary,
  candidateQualityBadge,
  candidateStatus,
  candidateText,
  CandidateCheckResult,
  officialEvidenceText,
  statusBadgeClass,
} from '../CandidateTableUtils';

export const CandidateMobileCard = memo(function CandidateMobileCard({
  candidate,
  checkResults,
  canShowRowActions,
  canSimulate,
  canCheck,
  workflowBusy,
  simulationBusy,
  checkingAlphaId,
  checkBusy,
  onScore,
  onSimulate,
  onCheck,
  cardRef,
  style,
}: {
  candidate: Candidate;
  checkResults: Map<string, CandidateCheckResult>;
  canShowRowActions: boolean;
  canSimulate: boolean;
  canCheck: boolean;
  workflowBusy: boolean;
  simulationBusy: boolean;
  checkingAlphaId: string | null;
  checkBusy: boolean;
  onScore?: (candidate: Candidate) => void;
  onSimulate?: (candidate: Candidate) => void;
  onCheck?: (candidate: Candidate) => void;
  cardRef?: React.Ref<HTMLDivElement>;
  style?: React.CSSProperties;
}) {
  const quality = candidateQualityBadge(candidate);
  const evidence = officialEvidenceText(candidate, checkResults);
  const identity = candidateIdentity(candidate);
  const hasActions = canShowRowActions || canSimulate || canCheck;
  const [starred, setStarred] = useState(() => isStarred(identity));
  const handleToggleStar = useCallback(() => {
    const newState = toggleStar(identity);
    setStarred(newState);
  }, [identity]);
  return (
    <div ref={cardRef} className="panel" style={{ padding: '12px', ...style }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button
              type="button"
              onClick={handleToggleStar}
              aria-label={starred ? '取消收藏' : '收藏'}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontSize: 16,
                lineHeight: 1,
                padding: 0,
                opacity: starred ? 1 : 0.3,
                transition: 'opacity 0.15s',
              }}
            >
              ⭐
            </button>
            <p className="text-xs font-mono text-info">
              {candidateIdentity(candidate).slice(0, 24) || '--'}
            </p>
          </div>
          <p className="text-xs font-mono text-text-secondary mt-2 break-words">
            {candidateText(candidate.expression) || '--'}
          </p>
        </div>
        <span className={`badge shrink-0 ${quality.tone}`}>{quality.label}</span>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 8,
          marginTop: 12,
          fontSize: '0.75rem',
        }}
      >
        <div>
          <span className="text-text-tertiary">评分</span>
          <p className="font-mono-value text-text-primary">
            {candidate.scorecard?.total_score?.toFixed(1) ?? '--'}
          </p>
        </div>
        <div>
          <span className="text-text-tertiary">状态</span>
          <p className="mt-1">
            <span className={`badge ${statusBadgeClass(candidateStatus(candidate))}`}>
              {candidateStatus(candidate) || '--'}
            </span>
          </p>
        </div>
        <div style={{ gridColumn: 'span 2' }}>
          <span className="text-text-tertiary">阻断原因</span>
          <p className="text-text-secondary break-words">{candidateBlockerText(candidate)}</p>
        </div>
        <div style={{ gridColumn: 'span 2' }}>
          <span className="text-text-tertiary">官方证据</span>
          <p className="text-text-secondary break-words">{evidence}</p>
        </div>
        <div style={{ gridColumn: 'span 2' }}>
          <span className="text-text-tertiary">输出</span>
          <p className="text-text-primary">{candidateOutputSummary(candidate)}</p>
          <p className="text-text-tertiary">{candidateOutputDetail(candidate)}</p>
        </div>
      </div>
      {hasActions && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
          {canShowRowActions && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ width: '100%' }}
              aria-label={`评分 ${candidateIdentity(candidate)}`}
              disabled={workflowBusy}
              onClick={() => onScore?.(candidate)}
            >
              评分
            </button>
          )}
          {canCheck && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ width: '100%' }}
              aria-label={`单行补查 ${identity}`}
              disabled={checkBusy}
              onClick={() => onCheck?.(candidate)}
            >
              {checkingAlphaId === identity ? '检查中...' : '单行补查'}
            </button>
          )}
          {canSimulate && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ width: '100%' }}
              aria-label={`单行补模拟 ${identity}`}
              disabled={simulationBusy}
              onClick={() => onSimulate?.(candidate)}
            >
              单行补模拟
            </button>
          )}
        </div>
      )}
    </div>
  );
});
