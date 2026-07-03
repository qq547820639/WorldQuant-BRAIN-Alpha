/** OfficialOperations summary components: sync history list and readiness summary sections. */

import { memo } from 'react';
import { readinessReasonLabel } from '@/helpers/readinessLabels';
import { classifyJobState } from '@/helpers/runPayload';
import type { SubmitReadinessResponse, SyncHistoryItem } from '@/types';
import { BlockerList, SummaryMetric } from './OfficialDisplayComponents';
import {
  contextSummaryField,
  countTitle,
  findingText,
  formatClock,
  formatCount,
  formatLocalBacktestStatus,
  formatOptionalNumber,
  officialContextSummaryMessage,
  reasonCountText,
  riskLevelLabel,
  actionStepLabel,
  shortOperationId,
} from './utils';

export const SyncHistoryList = memo(function SyncHistoryList({
  rows,
}: {
  rows: SyncHistoryItem[];
}) {
  return (
    <ul
      className="mt-3 divide-y divide-border-subtle rounded-md border border-border-subtle bg-[var(--color-surface-elevated)]"
      aria-label="最近官方同步列表"
    >
      {rows.slice(0, 5).map((row) => (
        <li key={row.job_id} className="grid gap-3 p-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`status-dot ${syncHistoryDotTone(row.status)}`} aria-hidden="true" />
              <span className="text-sm font-semibold text-text-primary">
                {syncHistoryStatusLabel(row.status)}
              </span>
              <span className="badge badge-neutral text-xs">
                {row.context_only ? '仅上下文' : '云端同步'}
              </span>
              <span className="font-mono-value text-xs text-text-tertiary" title={row.job_id}>
                {shortOperationId(row.job_id)}
              </span>
            </div>
            <p className="mt-1 break-words text-sm leading-6 text-text-secondary">
              {syncHistoryMessage(row)}
            </p>
          </div>
          <time
            className="text-xs text-text-tertiary sm:text-right"
            dateTime={syncHistoryDate(row)?.toISOString()}
          >
            {syncHistoryDate(row) ? formatClock(syncHistoryDate(row) ?? undefined) : '-'}
          </time>
        </li>
      ))}
    </ul>
  );
});

function syncHistoryStatusLabel(status: string) {
  const value = String(status || '').toLowerCase();
  const labels: Record<string, string> = {
    completed: '已完成',
    completed_with_warnings: '带警告',
    failed: '失败',
    running: '进行中',
    queued: '已排队',
    stopping: '停止中',
    stopped: '已停止',
    cancelled: '已取消',
    canceled: '已取消',
    idle: '待启动',
  };
  return labels[value] || '状态待确认';
}

function syncHistoryDotTone(status: string) {
  const state = classifyJobState({ status });
  if (state.successful && !state.warning) return 'status-dot-active';
  if (state.warning || state.active) return 'status-dot-warning';
  if (state.failed || state.interrupted || state.missing) return 'status-dot-error';
  return 'status-dot-idle';
}

function syncHistoryDate(row: SyncHistoryItem) {
  const ms = firstPositiveNumber(row.updated_at_ms, row.updated_at ? row.updated_at * 1000 : 0);
  return ms > 0 ? new Date(ms) : null;
}

function firstPositiveNumber(...values: Array<number | null | undefined>) {
  const value = values.find((item) => Number.isFinite(item) && Number(item) > 0);
  return Number.isFinite(value) ? Number(value) : 0;
}

function phaseLabel(status: { job_id?: string; status?: string; phase?: string }) {
  const code = String(status?.phase || 'idle');
  const labels: Record<string, string> = {
    context_refresh: '刷新上下文',
    scan: '扫描云端',
    context_fields: '刷新字段',
    context_operators: '刷新算子',
    context_datasets: '刷新数据集',
  };
  return labels[code.toLowerCase()] || '当前阶段';
}

function syncHistoryMessage(row: SyncHistoryItem) {
  const explicit = readableBackendText(row.status_message || '');
  const scanned = firstPositiveNumber(row.scanned);
  const total = firstPositiveNumber(row.api_reported_total, row.filter_window_count, row.total);
  const deltas = [
    row.added && row.added > 0 ? `新增 ${formatCount(row.added)}` : '',
    row.updated && row.updated > 0 ? `更新 ${formatCount(row.updated)}` : '',
    row.skipped && row.skipped > 0 ? `跳过 ${formatCount(row.skipped)}` : '',
    row.failed && row.failed > 0 ? `失败 ${formatCount(row.failed)}` : '',
  ].filter(Boolean);
  const scanText =
    scanned > 0 && total > 0
      ? `已拉取 ${formatCount(scanned)} 条；分页参考数 ${formatCount(total)} 条`
      : scanned > 0
        ? `已拉取 ${formatCount(scanned)} 条`
        : '';
  const parts = [scanText, deltas.length ? deltas.join('，') : ''].filter(Boolean);
  if (explicit && parts.length) return `${explicit}；${parts.join('；')}。`;
  if (explicit) return explicit;
  if (parts.length) return `${parts.join('；')}。`;
  return row.phase
    ? `阶段: ${phaseLabel({ job_id: row.job_id, status: 'idle', phase: row.phase })}`
    : '暂无同步摘要。';
}

function readableBackendText(raw: unknown) {
  const value = String((raw as string | number | boolean | null | undefined) || '').trim();
  const labels: Record<string, string> = {
    'Official context refreshed.': '官方上下文已刷新。',
    'candidate family lacks official simulation metrics': '候选族缺少官方仿真指标',
    'official context timeout': '官方上下文刷新超时，请稍后重试。',
    'unknown sync job': '找不到本次同步任务，请重新启动刷新。',
    'unknown job': '找不到本次任务，请重新启动流程。',
    JOB_NOT_FOUND: '找不到本次任务，请重新启动流程。',
    SESSION_INVALID:
      '本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。',
    'invalid local session':
      '本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。',
    OFFICIAL_CONTEXT_REFRESH_TIMEOUT: '官方上下文刷新超时，请稍后重试。',
  };
  if (labels[value]) return labels[value];
  if (isAllowedOfficialStatusText(value)) return value;
  return null;
}

function isAllowedOfficialStatusText(value: string) {
  if (!value) return false;
  return [
    /^官方上下文已刷新/,
    /^官方上下文刷新/,
    /^官方上下文刷新已停止/,
    /^正在刷新官方字段缓存/,
    /^正在刷新官方算子缓存/,
    /^云端同步完成/,
    /^连续读取刷新状态失败/,
    /^用户已停止本次官方上下文刷新/,
  ].some((pattern) => pattern.test(value));
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

export function SummarySections({
  readiness,
  displaySyncStatus,
  onNavigateToCandidates,
}: {
  readiness: SubmitReadinessResponse | null;
  displaySyncStatus: unknown;
  onNavigateToCandidates?: () => void;
}) {
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
