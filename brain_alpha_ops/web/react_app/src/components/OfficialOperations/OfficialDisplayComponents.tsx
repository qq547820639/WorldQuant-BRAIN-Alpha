/** OfficialOperations display components: metrics, overview cards, log, action panels. */

import { memo, type ReactNode } from 'react';
import type {
  CloudAlphaCache,
  JobStatus,
  OfficialContextCache,
  SubmitReadinessResponse,
} from '@/types';
import type { OperationLogEntry, OperationMode, SyncRange } from './utils';
import {
  logDotTone,
  logTone,
  syncContextStatus,
  contextCacheComplete,
  syncDataOverview,
  syncStatusForDisplay,
} from './utils';

export const BlockerList = memo(function BlockerList({
  title,
  rows,
  empty,
}: {
  title: string;
  rows: string[];
  empty: string;
}) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">{title}</p>
      <ul className="mt-1 space-y-1">
        {(rows.length ? rows : [empty]).map((row, index) => (
          <li key={`${title}_${index}`} className="break-words">
            {row}
          </li>
        ))}
      </ul>
    </div>
  );
});

export const OperationMetric = memo(function OperationMetric({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  tone?: 'success' | 'warning' | 'neutral';
}) {
  const toneClass =
    tone === 'success'
      ? 'text-positive'
      : tone === 'warning'
        ? 'text-warning'
        : 'text-text-secondary';
  return (
    <div className="rounded-md border border-border-subtle bg-surface-1 p-2">
      <p className="text-xs text-text-tertiary">{label}</p>
      <p className={`font-mono-value text-sm font-medium ${toneClass}`}>{value}</p>
    </div>
  );
});

export const SummaryMetric = memo(function SummaryMetric({
  label,
  value,
  title,
  mono = false,
}: {
  label: string;
  value: string;
  title?: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-text-tertiary">{label}</dt>
      <dd
        className={`mt-1 truncate text-sm font-semibold text-text-primary ${mono ? 'font-mono-value' : ''}`}
        title={title || value}
      >
        {value}
      </dd>
    </div>
  );
});

export const OverviewCard = memo(function OverviewCard({
  label,
  value,
  detail,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: 'success' | 'warning' | 'neutral';
}) {
  const toneClass =
    tone === 'success'
      ? 'text-positive'
      : tone === 'warning'
        ? 'text-warning'
        : 'text-text-primary';
  return (
    <div className="panel min-w-0 p-3">
      <p className="text-xs text-text-tertiary">{label}</p>
      <p className={`font-mono-value text-lg font-semibold ${toneClass}`}>{value}</p>
      {detail && <p className="mt-1 text-xs text-text-secondary">{detail}</p>}
    </div>
  );
});

export const OperationLog = memo(function OperationLog({
  logs,
  onClear,
}: {
  logs: OperationLogEntry[];
  onClear?: () => void;
}) {
  return (
    <details className="rounded-md border border-border-subtle bg-[var(--color-surface-deep)] p-3">
      <summary className="cursor-pointer text-sm font-semibold text-text-primary">
        操作日志（{logs.length} 条）
      </summary>
      <div className="mt-3 flex items-center justify-between gap-3">
        <p className="text-xs text-text-tertiary">系统动作会写成可读事件，不展示命令或路径。</p>
        {onClear && (
          <button type="button" className="btn btn-secondary text-sm" onClick={onClear}>
            清空
          </button>
        )}
      </div>
      <div
        className="mt-3 max-h-40 min-w-0 overflow-y-auto rounded-md border border-border-subtle bg-[var(--color-surface-elevated)] p-3 text-sm leading-6 text-text-secondary"
        role="status"
        aria-live="polite"
        aria-label="官方操作时间线"
      >
        {logs.length ? (
          logs.map((entry, index) => (
            <div
              key={`${entry.time}_${index}`}
              className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-l border-border-subtle pb-3 pl-3 last:pb-0"
            >
              <span className={`mt-1 ${logDotTone(entry.tone)}`} aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-xs text-text-tertiary">{entry.time}</p>
                <p className={`break-words ${logTone(entry.tone)}`}>{entry.message}</p>
              </div>
            </div>
          ))
        ) : (
          <div className="text-text-tertiary">事件已清空。</div>
        )}
      </div>
    </details>
  );
});

export function OperationsLog({
  logs,
  onClear,
}: {
  logs: OperationLogEntry[];
  onClear: () => void;
}) {
  return <OperationLog logs={logs} onClear={onClear} />;
}

export const ActionPanel = memo(function ActionPanel({
  title,
  description,
  status,
  primaryLabel,
  disabled = false,
  onPrimary,
  secondaryLabel,
  secondaryDisabled = false,
  onSecondary,
  children,
}: {
  title: string;
  description: string;
  status: string;
  primaryLabel: string;
  disabled?: boolean;
  onPrimary?: () => void;
  secondaryLabel?: string;
  secondaryDisabled?: boolean;
  onSecondary?: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="panel min-w-0">
      <div className="panel-header">
        <span className="font-medium">{title}</span>
        <span className="badge badge-neutral">{status}</span>
      </div>
      <div className="panel-body-padded space-y-3">
        <p className="text-sm text-text-secondary">{description}</p>
        {children}
        <div className="flex gap-2">
          {onPrimary && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={disabled}
              onClick={onPrimary}
            >
              {primaryLabel}
            </button>
          )}
          {secondaryLabel && onSecondary && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={secondaryDisabled}
              onClick={onSecondary}
            >
              {secondaryLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
});

export function ActionButtons({
  syncRange,
  syncRunning,
  syncStartLoading,
  syncNeedsRetry,
  readinessLoading,
  checkResultsLoading,
  checkRowsCount,
  readiness,
  contextOnlyMode,
  onSyncRangeChange,
  onStartRefresh,
  onStopRefresh,
  onLoadReadiness,
  onLoadChecks,
}: {
  mode: OperationMode;
  syncRange: SyncRange;
  syncRunning: boolean;
  syncStartLoading: boolean;
  syncNeedsRetry: boolean;
  readinessLoading: boolean;
  checkResultsLoading: boolean;
  checkRowsCount: number;
  readiness: SubmitReadinessResponse | undefined;
  contextOnlyMode: boolean;
  onSyncRangeChange: (range: SyncRange) => void;
  onStartRefresh: () => void;
  onStopRefresh: () => void;
  onLoadReadiness: () => void;
  onLoadChecks: () => void;
}) {
  const refreshTitle = contextOnlyMode ? '仅刷新官方能力集' : '刷新官方能力集';
  const refreshDescription = contextOnlyMode
    ? '仅刷新官方字段、算子与 Dataset 上下文，不拉取云端 Alpha 快照。'
    : '同步云端 Alpha 快照，并刷新官方字段、算子与 Dataset 上下文。';

  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <ActionPanel
        title={refreshTitle}
        description={refreshDescription}
        status={syncRunning ? '运行中' : '待启动'}
        primaryLabel={syncRunning ? '刷新中...' : syncNeedsRetry ? '重新刷新' : '开始刷新'}
        disabled={syncRunning || syncStartLoading}
        onPrimary={onStartRefresh}
        secondaryLabel="停止"
        secondaryDisabled={!syncRunning}
        onSecondary={onStopRefresh}
      >
        <label className="mt-3 block text-xs text-text-secondary">
          <span className="mb-1 block text-text-tertiary">同步范围</span>
          <select
            className="input w-full text-sm"
            value={syncRange}
            disabled={syncRunning || syncStartLoading}
            onChange={(event) => onSyncRangeChange(event.target.value as SyncRange)}
            aria-label="同步范围"
          >
            <option value="all">全部（推荐）</option>
            <option value="3d">近 3 天（快速检查）</option>
            <option value="7d">近 7 天</option>
            <option value="recent">近期 30 天</option>
            <option value="6months">近 6 个月</option>
          </select>
          <span className="mt-1 block text-text-tertiary">
            默认完整同步；小范围同步更快，适合快速检查最近变化。
          </span>
        </label>
      </ActionPanel>
      <ActionPanel
        title="检查阻断复核"
        description="读取本地提交前阻断复核门禁，不调用真实提交。"
        status={readiness?.ready_to_submit ? '有候选' : readiness ? '仍阻断' : '待检查'}
        primaryLabel={readinessLoading ? '检查中...' : '读取复核'}
        disabled={readinessLoading}
        onPrimary={onLoadReadiness}
      />
      <ActionPanel
        title="回看检查结果"
        description="读取质量检查结果和阻断原因，方便继续迭代候选。"
        status={checkRowsCount > 0 ? `${checkRowsCount} 条记录` : '待读取'}
        primaryLabel={checkResultsLoading ? '加载中...' : '查看结果'}
        disabled={checkResultsLoading}
        onPrimary={onLoadChecks}
      />
    </div>
  );
}

export function MetricsDisplay({
  syncRunning,
  syncStatus,
  officialContextCache,
  cloudAlphaCache,
  readinessEligibleCount,
  readinessReadyToSubmit,
  checkRowsCount,
}: {
  syncRunning: boolean;
  syncStatus: JobStatus | null;
  officialContextCache?: OfficialContextCache;
  cloudAlphaCache?: CloudAlphaCache;
  readinessEligibleCount?: number;
  readinessReadyToSubmit?: boolean;
  checkRowsCount: number;
}) {
  const displaySyncStatus = syncStatusForDisplay(syncStatus, officialContextCache);
  const displaySyncState = { successful: false };
  const syncOverview = syncDataOverview(displaySyncStatus, syncRunning, cloudAlphaCache);

  return (
    <>
      <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4 lg:min-w-[420px]">
        <OperationMetric
          label="官方上下文"
          value={syncContextStatus(displaySyncStatus)}
          tone={
            syncRunning
              ? 'warning'
              : contextCacheComplete(displaySyncStatus?.official_context_cache) ||
                  displaySyncState.successful
                ? 'success'
                : 'neutral'
          }
        />
        <OperationMetric
          label="复核候选"
          value={String(readinessEligibleCount ?? '-')}
          tone={readinessReadyToSubmit ? 'success' : 'warning'}
        />
        <OperationMetric label="检查记录" value={String(checkRowsCount || '-')} />
        <OperationMetric label="真实提交" value="关闭" tone="success" />
      </div>

      <section className="grid gap-3 md:grid-cols-3" aria-label="官方同步数据总览">
        <OverviewCard
          label="同步状态"
          value={syncOverview.statusValue}
          detail={syncOverview.statusDetail}
          tone={syncOverview.statusTone}
        />
        <OverviewCard
          label="更新时间"
          value={syncOverview.updatedAtValue}
          detail={syncOverview.updatedAtDetail}
        />
        <OverviewCard
          label="分页拉取"
          value={syncOverview.totalValue}
          detail={syncOverview.totalDetail}
          tone={syncOverview.totalTone}
        />
      </section>

      {syncRunning && syncOverview.hasLiveMetrics && (
        <section className="grid gap-3 md:grid-cols-2" aria-label="同步实时指标">
          <OverviewCard
            label={syncOverview.etaLabel}
            value={syncOverview.etaValue}
            detail={syncOverview.etaDetail}
            tone="warning"
          />
          <OverviewCard
            label={syncOverview.rateLabel}
            value={syncOverview.rateValue}
            detail={syncOverview.rateDetail}
          />
        </section>
      )}
    </>
  );
}
