/** Progress bar and status metrics display. */

import { memo } from 'react';
import ProgressFeedback from '@/components/ProgressFeedback';
import type { UnifiedProgress, JobStatus } from '@/types';

interface ProofMetricProps {
  label: string;
  value: string;
  tone?: 'neutral' | 'success' | 'danger';
}

export function ProofMetric({ label, value, tone = 'neutral' }: ProofMetricProps) {
  const colorClass =
    tone === 'success'
      ? 'text-positive'
      : tone === 'danger'
        ? 'text-negative'
        : 'text-text-primary';
  return (
    <div className="kpi-card">
      <p className="kpi-card-label">{label}</p>
      <p className={`font-mono-value text-lg font-medium ${colorClass}`}>{value}</p>
    </div>
  );
}

export function productionSummary(status: JobStatus | null) {
  const result = isRecord(status?.result) ? status.result : null;
  const rs = isRecord(result?.summary) ? result.summary : null;
  const pd = isRecord(status?.progress?.data) ? status.progress.data : null;
  return {
    officialValidationAttempted: firstNum(
      rs?.official_validation_attempted,
      pd?.official_validation_attempted
    ),
    officialValidationPassed: firstNum(
      rs?.official_validation_passed,
      pd?.official_validation_passed
    ),
    officiallySimulated: firstNum(rs?.officially_simulated, pd?.officially_simulated),
    backtestsSubmitted: firstNum(rs?.backtests_submitted, pd?.backtests_submitted),
    submittedThisRun: firstNum(rs?.submitted_this_run, pd?.submitted_this_run),
    autoSubmitted: firstNum(rs?.auto_submitted, pd?.auto_submitted),
  };
}

function firstNum(...values: unknown[]) {
  for (const v of values) {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

interface Props {
  running: boolean;
  loading?: boolean;
  progress: UnifiedProgress | null;
  error: string | null;
  status: JobStatus | null;
  hasEvidence: boolean;
}

export default memo(function JobProgressBar({
  running,
  loading,
  progress,
  error,
  status,
  hasEvidence,
}: Props) {
  const summary = productionSummary(status);

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <ProofMetric
          label="官方验证"
          value={
            hasEvidence
              ? `${summary.officialValidationPassed}/${summary.officialValidationAttempted}`
              : '--'
          }
        />
        <ProofMetric
          label="官方回测"
          value={hasEvidence ? String(summary.officiallySimulated) : '--'}
        />
        <ProofMetric
          label="本轮真实提交（应为 0）"
          value={hasEvidence ? String(summary.submittedThisRun) : '--'}
          tone={summary.submittedThisRun > 0 ? 'danger' : 'success'}
        />
        <ProofMetric
          label="自动提交"
          value={hasEvidence ? String(summary.autoSubmitted) : '0'}
          tone={summary.autoSubmitted > 0 ? 'danger' : 'success'}
        />
      </div>

      {(running || loading) && (
        <div className="mb-4">
          <ProgressFeedback
            state={error ? 'error' : 'progress'}
            title="流水线进度"
            progress={progress}
            error={error}
            compact
          />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-text-tertiary mt-2">
            <span>
              轮次: {status?.cycle ?? 0}/{status?.max_cycles ?? 0}
            </span>
            <span>阶段: {status?.phase ?? '--'}</span>
            <span>候选数: {status?.progress?.candidates_generated ?? 0}</span>
            <span>回测数: {status?.progress?.backtests_completed ?? 0}</span>
          </div>
        </div>
      )}

      {!running && error && (
        <div className="mb-4">
          <ProgressFeedback
            state="error"
            title="流水线进度"
            progress={status?.progress}
            error={error}
            compact
          />
        </div>
      )}
    </>
  );
});
