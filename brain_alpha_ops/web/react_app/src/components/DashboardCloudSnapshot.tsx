import { memo } from 'react';
import type { CloudAlphaSummary, CloudAlphaWithMetrics } from '@/types';
import ProgressFeedback from '@/components/ProgressFeedback';

export type CloudSnapshotPayload = Partial<CloudAlphaSummary> &
  Record<string, unknown> & {
    alphas?: CloudAlphaWithMetrics[];
    summary?: Partial<CloudAlphaSummary> & Record<string, unknown>;
  };

export function cloudSnapshotSummary(cloud: CloudSnapshotPayload | null) {
  const summary = cloud?.summary || {};
  return {
    count: numberOrUndefined(summary.count ?? summary.total ?? summary.total_count),
    submitted_count: numberOrUndefined(cloud?.submitted_count ?? summary.submitted_count),
    passed_unsubmitted_count: numberOrUndefined(
      cloud?.passed_unsubmitted_count ?? summary.passed_unsubmitted_count
    ),
    is_stale: Boolean(cloud?.is_stale ?? summary.is_stale),
    loaded_at: stringOrUndefined(cloud?.loaded_at ?? summary.loaded_at),
    age_seconds: numberOrUndefined(cloud?.age_seconds ?? summary.age_seconds),
  };
}

export function cloudSnapshotPreviewRows(
  cloud: CloudSnapshotPayload | null
): CloudAlphaWithMetrics[] {
  const rows = cloud?.sample_alphas || cloud?.alphas || [];
  return Array.isArray(rows) ? rows : [];
}

function numberOrUndefined(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function stringOrUndefined(value: unknown) {
  const text = typeof value === 'string' ? value.trim() : '';
  return text || undefined;
}

export function formatSyncAge(ageSeconds?: number, loadedAt?: string) {
  if (typeof ageSeconds === 'number' && Number.isFinite(ageSeconds) && ageSeconds >= 0) {
    if (ageSeconds < 60) return '刚刚同步';
    if (ageSeconds < 3600) return `${Math.floor(ageSeconds / 60)} 分钟前`;
    if (ageSeconds < 86400) return `${Math.floor(ageSeconds / 3600)} 小时前`;
    return `${Math.floor(ageSeconds / 86400)} 天前`;
  }
  if (loadedAt) {
    const timestamp = Date.parse(loadedAt);
    if (Number.isFinite(timestamp)) {
      return new Date(timestamp).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    }
  }
  return '未同步';
}

function cloudAlphaId(row: CloudAlphaWithMetrics) {
  return String(row.alpha_id || row.id || '-');
}

function cloudAlphaPassFail(row: CloudAlphaWithMetrics) {
  const metrics = row.metrics && typeof row.metrics === 'object' ? row.metrics : {};
  return String(row.pass_fail || metrics.pass_fail || '');
}

function cloudAlphaMetric(row: CloudAlphaWithMetrics, key: string) {
  const metrics = row.metrics && typeof row.metrics === 'object' ? row.metrics : {};
  return numberOrUndefined(row[key] ?? metrics[key]);
}

function formatMetric(value: number | undefined) {
  return value == null ? '--' : value.toFixed(2);
}

interface DashboardCloudSnapshotProps {
  cloud: CloudSnapshotPayload | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onOpenSync: () => void;
}

export const DashboardCloudSnapshot = memo(function DashboardCloudSnapshot({
  cloud,
  loading,
  error,
  onRetry,
  onOpenSync,
}: DashboardCloudSnapshotProps) {
  const summary = cloudSnapshotSummary(cloud);
  const previewRows = cloudSnapshotPreviewRows(cloud);

  return (
    <div className="panel mb-4">
      <div className="panel-header">
        <span>云端 Alpha 缓存</span>
        {cloud && <span className="badge badge-neutral">{summary.count ?? '--'} 条</span>}
      </div>
      <div className="panel-body-padded">
        {loading ? (
          <ProgressFeedback
            state="loading"
            title="云端 Alpha"
            progress={{ phase: 'cloud', status_message: '加载中...' }}
            compact
          />
        ) : error ? (
          <ProgressFeedback
            state="error"
            title="云端 Alpha"
            error={error}
            onRetry={onRetry}
            compact
          />
        ) : cloud ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs mb-3">
              <div>
                <span className="text-text-tertiary">缓存总数</span>
                <p className="font-mono-value text-base text-text-primary">{summary.count ?? 0}</p>
              </div>
              <div>
                <span className="text-text-tertiary">已提交</span>
                <p className="font-mono-value text-base text-positive">
                  {summary.submitted_count ?? 0}
                </p>
              </div>
              <div>
                <span className="text-text-tertiary">已通过（未提交）</span>
                <p className="font-mono-value text-base text-warning">
                  {summary.passed_unsubmitted_count ?? 0}
                </p>
              </div>
              <div>
                <span className="text-text-tertiary">缓存状态</span>
                <p
                  className={`text-sm ${summary.is_stale ? 'font-medium text-warning' : 'text-text-secondary'}`}
                >
                  {summary.is_stale ? '已过期' : '有效'}
                </p>
                {summary.is_stale && (
                  <button
                    type="button"
                    className="mt-1 text-xs text-accent underline"
                    onClick={onOpenSync}
                  >
                    去手动同步
                  </button>
                )}
              </div>
            </div>
            {previewRows.length > 0 && (
              <div className="max-h-[200px] overflow-y-auto">
                <p className="mb-2 text-xs text-text-tertiary">
                  下方仅为页面预览；同步缓存总数以上方统计为准。
                </p>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Alpha ID</th>
                      <th>状态</th>
                      <th className="is-sortable num">Sharpe</th>
                      <th className="is-sortable num">Fitness</th>
                      <th className="is-sortable num">Turnover</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.slice(0, 10).map((a, i) => (
                      <tr key={i}>
                        <td className="id">{cloudAlphaId(a)}</td>
                        <td>
                          <span
                            className={`badge ${cloudAlphaPassFail(a) === 'PASS' ? 'badge-positive' : 'badge-negative'}`}
                          >
                            {cloudAlphaPassFail(a) || '--'}
                          </span>
                        </td>
                        <td className="num">{formatMetric(cloudAlphaMetric(a, 'sharpe'))}</td>
                        <td className="num">{formatMetric(cloudAlphaMetric(a, 'fitness'))}</td>
                        <td className="num">{formatMetric(cloudAlphaMetric(a, 'turnover'))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
});
