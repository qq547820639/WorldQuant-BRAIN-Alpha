/** Summary grid sections for readiness, convergence, and context overview. */

import { readinessReasonLabel } from '@/helpers/readinessLabels';
import type { SubmitReadinessResponse } from '@/types';
import {
  BlockerList,
  SummaryMetric,
  countTitle,
  reasonCountText,
  findingText,
  riskLevelLabel,
  actionStepLabel,
  formatOptionalNumber,
  formatLocalBacktestStatus,
  contextSummaryField,
  officialContextSummaryMessage,
  shortOperationId,
} from '.';

interface Props {
  readiness: SubmitReadinessResponse | null;
  displaySyncStatus: unknown;
  onNavigateToCandidates?: () => void;
}

const officialEvidenceActionCodes = new Set([
  'candidate_family_missing_cloud_similarity',
  'candidate_family_missing_official_alpha_id',
  'candidate_family_missing_official_metrics',
  'missing_cloud_similarity',
  'missing_official_alpha_id',
  'missing_official_metrics',
  'official_validation_without_simulation',
  'run official simulation/check in a trusted environment',
]);

const submitBandActionCodes = new Set([
  'candidate_family_not_submit_band',
  'decision_band_not_submit_candidate',
  'optimize',
  'research_only',
]);

function readinessActionSignals(
  blockers: Array<{ reason?: string }>,
  familyBlockers: Array<{ reason?: string }>,
  gaps: Array<{ code?: string; message?: string }>,
  bestCandidateReasons: string[],
  nextSteps: string[],
  decisionBand?: string
) {
  return [
    ...blockers.map((row) => row.reason || ''),
    ...familyBlockers.map((row) => row.reason || ''),
    ...gaps.flatMap((row) => [row.code || '', row.message || '']),
    ...bestCandidateReasons,
    ...nextSteps,
    decisionBand || '',
  ]
    .map((item) => String(item || '').trim())
    .filter(Boolean);
}

export default function SummarySections({
  readiness,
  displaySyncStatus,
  onNavigateToCandidates,
}: Props) {
  const allReadinessBlockers = readiness?.top_blocking_reasons || [];
  const allFamilyBlockers = readiness?.top_family_blocking_reasons || [];
  const allProductionGaps = readiness?.production_gaps || readiness?.findings || [];
  const allNextSteps = readiness?.required_next_steps || [];
  const bestCandidate = readiness?.best_candidate || {};
  const allBestCandidateReasons = bestCandidate.blocking_reasons || [];
  const readinessActionCodes = readinessActionSignals(
    allReadinessBlockers,
    allFamilyBlockers,
    allProductionGaps,
    allBestCandidateReasons,
    allNextSteps,
    bestCandidate.decision_band
  );
  const needsOfficialEvidenceAction = Boolean(
    readiness && readinessActionCodes.some((code) => officialEvidenceActionCodes.has(code))
  );
  const needsSubmitBandAction = Boolean(
    readiness && readinessActionCodes.some((code) => submitBandActionCodes.has(code))
  );
  const hasBestCandidateEvidence = Boolean(
    bestCandidate.alpha_id ||
    bestCandidate.official_alpha_id ||
    bestCandidate.decision_band ||
    allBestCandidateReasons.length
  );
  const summaryCounts = readiness?.summary_counts || {};
  const officialContextSummary = officialContextSummaryMessage(
    displaySyncStatus as import('@/types').JobStatus | null
  );

  return (
    <section className="grid gap-4 lg:grid-cols-3">
      <section className="rounded-md border border-border-subtle bg-[var(--color-surface-deep)] p-4">
        <h3 className="text-sm font-semibold text-text-primary">阻断复核摘要</h3>
        <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
          <SummaryMetric label="复核通过" value={readiness?.ready_to_submit ? '是' : '否'} />
          <SummaryMetric label="复核候选" value={String(readiness?.eligible_count ?? 0)} />
          <SummaryMetric label="候选总数" value={String(readiness?.candidate_count ?? 0)} />
          <SummaryMetric
            label="最近验证"
            value={readiness?.latest_job_id ? shortOperationId(readiness.latest_job_id) : '-'}
            title={readiness?.latest_job_id}
            mono
          />
        </dl>
        <div className="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
          <BlockerList
            title={countTitle('当前阻断', allReadinessBlockers.length)}
            rows={allReadinessBlockers.map(reasonCountText)}
            empty="暂无就绪数据"
          />
          <BlockerList
            title={countTitle('候选族阻断', allFamilyBlockers.length)}
            rows={allFamilyBlockers.map(reasonCountText)}
            empty="暂无候选族阻断"
          />
          <BlockerList
            title={countTitle('下一步', allNextSteps.length)}
            rows={allNextSteps.map(actionStepLabel)}
            empty="先读取阻断复核证据"
          />
        </div>
        {(needsOfficialEvidenceAction || needsSubmitBandAction) && (
          <div className="mt-3 border-l-2 border-accent pl-3 text-sm leading-6 text-text-secondary">
            <p className="font-semibold text-text-primary">补齐官方证据</p>
            {needsOfficialEvidenceAction && (
              <p className="mt-1">
                前往「候选管理」，优先点击「自动推进候选池」；仅当官方证据缺失时，使用「运行官方验证队列」或候选行「单行补模拟」补齐
                official_alpha_id 与 official_metrics。完成后回到这里点击「读取复核」。
              </p>
            )}
            {needsSubmitBandAction && (
              <p className="mt-1">
                当前候选尚未进入 submit_candidate
                复核带；先让候选管理自动维护主池并继续筛选/评分，进入复核带后由自动流程补齐官方模拟证据。
              </p>
            )}
            {onNavigateToCandidates && (
              <button
                type="button"
                className="btn btn-secondary mt-2 text-sm"
                onClick={onNavigateToCandidates}
              >
                前往候选管理
              </button>
            )}
          </div>
        )}
      </section>

      <section className="rounded-md border border-border-subtle bg-[var(--color-surface-deep)] p-4">
        <h3 className="text-sm font-semibold text-text-primary">收敛诊断</h3>
        <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
          <SummaryMetric
            label="官方验证"
            value={String(summaryCounts.official_validation_passed ?? 0)}
          />
          <SummaryMetric label="官方仿真" value={String(summaryCounts.officially_simulated ?? 0)} />
          <SummaryMetric label="复核带" value={String(summaryCounts.submission_ready ?? 0)} />
          <SummaryMetric
            label="候选族"
            value={String(readiness?.job_family_candidate_count ?? 0)}
          />
        </dl>
        <div className="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
          <BlockerList
            title={countTitle('生产缺口', allProductionGaps.length)}
            rows={allProductionGaps.map(findingText)}
            empty="先读取阻断复核证据"
          />
          <BlockerList
            title={countTitle('最佳候选阻断', allBestCandidateReasons.length)}
            rows={allBestCandidateReasons.map((reason) => readinessReasonLabel(reason))}
            empty="暂无最佳候选阻断"
          />
        </div>
        <div className="mt-3 rounded-md border border-border-subtle bg-[var(--color-surface-elevated)] p-3 text-sm leading-6 text-text-secondary">
          <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">
            最佳候选证据
          </p>
          <dl className="mt-2 grid grid-cols-2 gap-3">
            <SummaryMetric
              label="Alpha"
              value={hasBestCandidateEvidence ? bestCandidate.alpha_id || '-' : '-'}
              mono
            />
            <SummaryMetric
              label="分数"
              value={hasBestCandidateEvidence ? formatOptionalNumber(bestCandidate.score) : '-'}
            />
            <SummaryMetric
              label="决策"
              value={
                hasBestCandidateEvidence
                  ? readinessReasonLabel(bestCandidate.decision_band || '')
                  : '-'
              }
            />
            <SummaryMetric
              label="相似度"
              value={
                hasBestCandidateEvidence ? formatOptionalNumber(bestCandidate.max_similarity) : '-'
              }
            />
            <SummaryMetric
              label="本地回测"
              value={formatLocalBacktestStatus(
                bestCandidate.local_backtest_passed,
                hasBestCandidateEvidence
              )}
            />
            <SummaryMetric
              label="风险"
              value={
                hasBestCandidateEvidence ? riskLevelLabel(bestCandidate.risk_level || '') : '-'
              }
            />
          </dl>
        </div>
      </section>

      <section className="rounded-md border border-border-subtle bg-[var(--color-surface-deep)] p-4">
        <h3 className="text-sm font-semibold text-text-primary">官方上下文摘要</h3>
        <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
          <SummaryMetric
            label="字段"
            value={contextSummaryField(
              displaySyncStatus as import('@/types').JobStatus | null,
              'fields_count'
            )}
          />
          <SummaryMetric
            label="算子"
            value={contextSummaryField(
              displaySyncStatus as import('@/types').JobStatus | null,
              'operators_count'
            )}
          />
          <SummaryMetric
            label="数据集"
            value={contextSummaryField(
              displaySyncStatus as import('@/types').JobStatus | null,
              'datasets_count'
            )}
          />
        </dl>
        <p className="mt-3 text-sm leading-6 text-text-secondary">{officialContextSummary}</p>
      </section>
    </section>
  );
}
