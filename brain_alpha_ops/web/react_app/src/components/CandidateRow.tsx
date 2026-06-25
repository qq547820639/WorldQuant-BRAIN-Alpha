/**
 * Single candidate row for the desktop table view.
 * Extracted from CandidateTable.tsx.
 */

import { memo, useCallback, useState } from 'react';
import type { Candidate, CandidateCheckResult } from '@/types';
import ScoreBreakdown from './ScoreBreakdown';
import { isStarred, toggleStar } from '@/utils/starredCandidates';
import {
  candidateBlockerText,
  candidateIdentity,
  candidateOutputDetail,
  candidateOutputSummary,
  candidateQualityBadge,
  candidateStatus,
  candidateText,
  officialEvidenceText,
  safeCandidateDisplayText,
  statusBadgeClass,
} from './CandidateTableUtils';

export interface CandidateRowProps {
  candidate: Candidate;
  checkResults: Map<string, CandidateCheckResult>;
  hasActions: boolean;
  canShowRowActions: boolean;
  showProductionControls: boolean;
  candidateWorkflowBusy: boolean;
  checkingAlphaId: string | null;
  onScore?: (candidate: Candidate) => void;
  onSimulate?: (candidate: Candidate) => void;
  onCheck?: (candidate: Candidate) => void;
  // Batch selection
  isSelected: boolean;
  onToggleSelect: (id: string) => void;
  /** Optional style for virtual scrolling positioning */
  style?: React.CSSProperties;
  /** Ref for dynamic row height measurement */
  rowRef?: React.Ref<HTMLTableRowElement>;
}

export const CandidateRow = memo(function CandidateRow({
  candidate,
  checkResults,
  hasActions,
  canShowRowActions,
  showProductionControls,
  candidateWorkflowBusy,
  checkingAlphaId,
  onScore,
  onSimulate,
  onCheck,
  isSelected,
  onToggleSelect,
  style,
  rowRef,
}: CandidateRowProps) {
  const quality = candidateQualityBadge(candidate);
  const evidence = officialEvidenceText(candidate, checkResults);
  const identity = candidateIdentity(candidate);

  // P2-2: Star toggle
  const [starred, setStarred] = useState(() => isStarred(identity));
  const handleToggleStar = useCallback(() => {
    const newState = toggleStar(identity);
    setStarred(newState);
  }, [identity]);

  return (
    <tr ref={rowRef} style={style}>
      {/* Batch selection checkbox */}
      <td style={{ textAlign: 'center', padding: '4px 2px' }}>
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggleSelect(identity)}
          aria-label={`选择候选 ${identity}`}
        />
      </td>
      {/* Star toggle */}
      <td style={{ textAlign: 'center', padding: '4px 2px' }}>
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
          title={starred ? '取消收藏' : '收藏此候选'}
        >
          ⭐
        </button>
      </td>
      <td className="id">{identity.slice(0, 16) || '--'}</td>
      <td>
        <div
          className="font-mono text-xs text-text-secondary break-words"
          title={candidateText(candidate.expression)}
        >
          {candidateText(candidate.expression) || '--'}
        </div>
        <div className="text-2xs text-text-tertiary mt-1">
          {safeCandidateDisplayText(candidate.family, '家族待确认')}
        </div>
      </td>
      <td className="num score-cell" style={{ fontWeight: 500, color: 'var(--color-text-bright)' }}>
        <span className="score-value">{candidate.scorecard?.total_score?.toFixed(1) ?? '--'}</span>
        {candidate.scorecard && (
          <div className="score-tooltip">
            <ScoreBreakdown scorecard={candidate.scorecard} />
          </div>
        )}
      </td>
      <td>
        <span className={`badge ${statusBadgeClass(candidateStatus(candidate))}`}>
          {candidateStatus(candidate) || '--'}
        </span>
      </td>
      <td>
        <span className={`badge ${quality.tone}`} title={quality.title}>
          {quality.label}
        </span>
      </td>
      <td className="text-xs text-text-secondary">{candidateBlockerText(candidate)}</td>
      <td className="text-xs">
        <div className="font-medium text-text-primary">{candidateOutputSummary(candidate)}</div>
        <div className="text-text-tertiary mt-1">{candidateOutputDetail(candidate)}</div>
      </td>
      <td className="text-xs">
        <div className="text-text-secondary">{evidence}</div>
        <div className="text-text-tertiary mt-1">
          {candidateText(candidate.simulation_id) || 'simulation:--'}
        </div>
      </td>
      {hasActions && (
        <td>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {canShowRowActions && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                aria-label={`评分 ${identity}`}
                disabled={candidateWorkflowBusy}
                onClick={() => onScore?.(candidate)}
              >
                评分
              </button>
            )}
            {showProductionControls && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                aria-label={`单行补查 ${identity}`}
                disabled={candidateWorkflowBusy}
                onClick={() => onCheck?.(candidate)}
              >
                {checkingAlphaId === identity ? '检查中...' : '单行补查'}
              </button>
            )}
            {showProductionControls && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                aria-label={`单行补模拟 ${identity}`}
                disabled={candidateWorkflowBusy}
                onClick={() => onSimulate?.(candidate)}
              >
                单行补模拟
              </button>
            )}
          </div>
        </td>
      )}
    </tr>
  );
});
