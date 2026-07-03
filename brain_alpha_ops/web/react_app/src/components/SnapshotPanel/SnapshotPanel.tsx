/** Read-only data and research snapshot views. */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiErrorMessage } from '@/helpers/errorExperience';
import { useDebounce } from '@/hooks/useDebounce';
import { useApi } from '@/hooks/useApi';
import ProgressFeedback from '@/components/ProgressFeedback';
import type { CardViewId } from '@/types';
import {
  MAX_FILTER_LENGTH,
  type SnapshotRow,
  type SnapshotPayload,
  truthy,
  rowText,
  normalizeSnapshotRow,
  defaultMetrics,
  sanitizeTextInput,
  displayKind,
  statusBadge,
} from './utils';
import { SNAPSHOT_VIEWS, type SnapshotView, checkpointComparisonSummary } from './snapshotViews';

export type { SnapshotView };

function SnapshotDesktopTable({
  rows,
  emptyMessage,
  title,
}: {
  rows: SnapshotRow[];
  emptyMessage: string;
  title: string;
}) {
  return (
    <div className="hidden max-w-full overflow-auto md:block">
      <table className="data-table min-w-[820px] w-full text-sm" aria-label={`${title}表格`}>
        <thead>
          <tr
            className="text-left text-xs uppercase tracking-wider"
            style={{ borderBottom: '1px solid', borderColor: 'var(--color-border-medium)' }}
          >
            <th scope="col" className="p-3 text-text-tertiary">
              类型
            </th>
            <th scope="col" className="p-3 text-text-tertiary">
              名称
            </th>
            <th scope="col" className="p-3 text-text-tertiary">
              状态
            </th>
            <th scope="col" className="p-3 text-text-tertiary">
              指标
            </th>
            <th scope="col" className="p-3 text-text-tertiary">
              详情
            </th>
            <th scope="col" className="p-3 text-text-tertiary">
              时间
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="p-6 text-center text-text-tertiary">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr
                key={`${row.kind}_${row.id}_${index}`}
                className="transition-colors"
                style={{ borderBottom: '1px solid', borderColor: 'var(--color-border-faded)' }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.backgroundColor =
                    'var(--color-surface-hover)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.backgroundColor = '';
                }}
              >
                <td className="p-3 text-xs text-text-tertiary">{displayKind(row.kind)}</td>
                <td className="p-3 font-mono-value text-xs text-accent">
                  {row.title || row.id || '-'}
                </td>
                <td className="p-3">
                  <span className={`badge text-xs ${statusBadge(row.status)}`}>
                    {row.status || '-'}
                  </span>
                </td>
                <td className="p-3 font-mono-value text-xs">{row.metric || '-'}</td>
                <td
                  className="p-3 text-xs text-text-secondary max-w-md truncate"
                  title={row.detail}
                >
                  {row.detail || '-'}
                </td>
                <td className="p-3 font-mono-value text-xs text-text-tertiary">
                  {row.timestamp || '-'}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function SnapshotMobileCard({ row }: { row: SnapshotRow }) {
  return (
    <article
      className="rounded-md p-4 text-sm"
      style={{
        border: '1px solid',
        borderColor: 'var(--color-border-medium-alpha)',
        backgroundColor: 'var(--color-surface-deep-alpha)',
      }}
    >
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-text-tertiary">
            {displayKind(row.kind || 'snapshot')}
          </p>
          <p className="mt-1 break-words font-mono-value text-xs text-accent">
            {row.title || row.id || '-'}
          </p>
        </div>
        <span className={`badge shrink-0 text-xs ${statusBadge(row.status)}`}>
          {row.status || '-'}
        </span>
      </div>
      <dl className="mt-4 grid gap-3 text-xs">
        <div>
          <dt className="text-text-tertiary">指标</dt>
          <dd className="mt-1 break-words font-mono-value text-text-primary">
            {row.metric || '-'}
          </dd>
        </div>
        <div>
          <dt className="text-text-tertiary">详情</dt>
          <dd className="mt-1 break-words text-text-secondary">{row.detail || '-'}</dd>
        </div>
        <div>
          <dt className="text-text-tertiary">时间</dt>
          <dd className="mt-1 break-words font-mono-value text-text-tertiary">
            {row.timestamp || '-'}
          </dd>
        </div>
      </dl>
    </article>
  );
}

interface Props {
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  viewMode: SnapshotView;
  onNavigate?: (view: CardViewId) => void;
}

export default function SnapshotPanel({ notify, viewMode, onNavigate }: Props) {
  const api = useApi<SnapshotPayload>();
  const [filterInput, setFilterInput] = useState('');
  const filter = useDebounce(filterInput, 300);
  const config = SNAPSHOT_VIEWS[viewMode];
  const callApi = api.call;

  const load = useCallback(async () => {
    const result = await callApi<SnapshotPayload>(config.endpoint);
    if (result?.error) notify('error', apiErrorMessage(result, `${config.title}加载失败`));
  }, [callApi, config.endpoint, notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const payload = api.data || {};
  const rows = useMemo(() => config.rows(payload).map(normalizeSnapshotRow), [config, payload]);
  const metrics = useMemo(
    () => config.metrics?.(payload, rows) || defaultMetrics(payload, rows),
    [config, payload, rows]
  );
  const normalizedFilter = filter.trim().toLowerCase();
  const filteredRows = normalizedFilter
    ? rows.filter((row) => rowText(row).includes(normalizedFilter))
    : rows;
  const comparisonSummary =
    viewMode === 'checkpoint_status' ? checkpointComparisonSummary(payload) : '';

  if (api.loading && !api.data) {
    return (
      <ProgressFeedback
        state="loading"
        title={config.title}
        progress={{ phase: 'snapshot_load', status_message: `正在加载 ${config.title}。` }}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-4 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-text-primary">{config.title}</h2>
          <p className="text-xs text-text-tertiary">{config.subtitle}</p>
        </div>
        <button
          type="button"
          onClick={load}
          className="btn btn-secondary btn-sm"
          disabled={api.loading}
        >
          刷新
        </button>
      </div>

      <ProgressFeedback
        state={api.error ? 'error' : api.loading ? 'loading' : 'idle'}
        title={config.title}
        progress={{
          phase: api.loading ? 'snapshot_load' : 'completed',
          status_message: api.loading
            ? `正在刷新 ${config.title}。`
            : `${config.title} 快照已加载。`,
        }}
        error={api.error}
        onRetry={load}
        compact={!api.loading && !api.error}
      />

      {viewMode === 'checkpoint_status' && (
        <div
          className="rounded-lg p-4"
          style={{
            border: '1px solid',
            borderColor: 'var(--color-warning-border-subtle)',
            backgroundColor: 'var(--color-warning-bg)',
          }}
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-medium text-accent">
                {truthy(payload.resume_available)
                  ? '检测到可继续的上次进度'
                  : '暂无可继续的上次进度'}
              </p>
              <p className="mt-1 text-xs text-text-secondary">
                {truthy(payload.resume_available)
                  ? '先回到候选管理确认候选状态，再进入质量门禁复核是否满足提交前检查。'
                  : '新的生产搜索会在候选管理中创建续跑记录与历史记录。'}
              </p>
              {comparisonSummary && <p className="mt-2 text-xs text-accent">{comparisonSummary}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => onNavigate?.('candidates')}
                disabled={!onNavigate}
              >
                进入候选管理
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => onNavigate?.('quality_check')}
                disabled={!onNavigate}
              >
                查看质量门禁
              </button>
            </div>
          </div>
        </div>
      )}

      {api.error && (
        <div
          className="panel"
          role="alert"
          aria-live="assertive"
          style={{
            borderColor: 'var(--color-error-border)',
            backgroundColor: 'var(--color-error-bg)',
          }}
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-negative text-sm">
              加载 {config.title} 失败: {api.error}
            </p>
            <button
              type="button"
              onClick={load}
              className="btn btn-secondary btn-sm"
              disabled={api.loading}
            >
              重试
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {metrics.map((metric) => (
          <div key={metric.label} className="kpi-card">
            <p className="kpi-card-label">{metric.label}</p>
            <p className="kpi-card-value">{metric.value}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="text"
          aria-label={`筛选 ${config.title}`}
          placeholder="筛选行..."
          value={filterInput}
          maxLength={MAX_FILTER_LENGTH}
          onChange={(event) =>
            setFilterInput(sanitizeTextInput(event.target.value, MAX_FILTER_LENGTH))
          }
          className="w-full min-w-0 rounded-md px-3 py-2 text-sm sm:flex-1"
          style={{
            backgroundColor: 'var(--color-surface-elevated)',
            border: '1px solid',
            borderColor: 'var(--color-border-medium)',
            color: 'var(--color-text-bright)',
          }}
        />
        <p className="text-xs text-text-tertiary" role="status" aria-live="polite">
          {filteredRows.length} / {rows.length} 行
        </p>
      </div>

      <div className="panel overflow-hidden p-0">
        <SnapshotMobileList rows={filteredRows} emptyMessage={config.empty} title={config.title} />
        <SnapshotDesktopTable
          rows={filteredRows}
          emptyMessage={config.empty}
          title={config.title}
        />
      </div>
    </div>
  );
}

function SnapshotMobileList({
  rows,
  emptyMessage,
  title,
}: {
  rows: SnapshotRow[];
  emptyMessage: string;
  title: string;
}) {
  return (
    <div className="space-y-3 p-3 md:hidden" aria-label={`${title}移动列表`}>
      {rows.length === 0 ? (
        <div
          className="rounded-md px-4 py-6 text-center text-sm text-text-tertiary"
          style={{
            border: '1px solid',
            borderColor: 'var(--color-border-faded-strong)',
            backgroundColor: 'var(--color-surface-deep-faded)',
          }}
        >
          {emptyMessage}
        </div>
      ) : (
        rows.map((row, index) => (
          <SnapshotMobileCard key={`${row.kind}_${row.id}_mobile_${index}`} row={row} />
        ))
      )}
    </div>
  );
}
