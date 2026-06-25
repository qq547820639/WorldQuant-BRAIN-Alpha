import { memo } from 'react';
import type { AlphaLifecycleHistoryResponse, AlphaLifecycleTrace } from '@/types';
import {
  candidateText,
  numericResultField,
  lifecycleNextActionLabel,
  lifecycleStatusBadgeClass,
  lifecycleStatusLabel,
  lifecycleTraceTitle,
  safeLifecycleNote,
  shortLifecycleTraceId,
} from '../CandidateTableUtils';

export const LifecycleReplayPanel = memo(function LifecycleReplayPanel({
  error,
  filterActive,
  history,
  loading,
  visibleTraces,
}: {
  error: string | null;
  filterActive: boolean;
  history: AlphaLifecycleHistoryResponse | null;
  loading: boolean;
  visibleTraces: AlphaLifecycleTrace[];
}) {
  const summary: NonNullable<AlphaLifecycleHistoryResponse['summary']> = history?.summary || {};
  const recordCount = numericResultField(summary.record_count ?? history?.count);
  const alphaCount = numericResultField(summary.alpha_count);
  const traceRows = visibleTraces.slice(0, 4);
  return (
    <section className="panel mb-4" aria-label="生命周期回放">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <span>生命周期回放</span>
          <span className="badge badge-neutral">本地只读</span>
          <span className="badge badge-neutral">非提交</span>
          {filterActive && <span className="badge badge-info">已过滤</span>}
        </div>
      </div>
      <div className="panel-body-padded">
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))' }}
        >
          <LifecycleMetric label="记录" value={loading && !history ? '...' : String(recordCount)} />
          <LifecycleMetric label="Alpha" value={String(alphaCount)} />
          <LifecycleMetric
            label="通过"
            value={String(numericResultField(summary.passed_count))}
            tone="text-positive"
          />
          <LifecycleMetric
            label="阻断/失败"
            value={`${numericResultField(summary.blocked_count)}/${numericResultField(summary.failed_count)}`}
            tone="text-negative"
          />
          <LifecycleMetric
            label="已提交"
            value={String(numericResultField(summary.submitted_count))}
          />
        </div>

        {error ? (
          <p
            className="mt-4 rounded-md border border-negative/40 bg-negative/10 px-3 py-2 text-xs text-negative"
            role="alert"
          >
            {error}
          </p>
        ) : traceRows.length > 0 ? (
          <div className="mt-4 grid gap-2">
            {traceRows.map((trace) => (
              <div
                key={trace.trace_key || trace.expression_digest || trace.latest_event_at}
                className="rounded-md border border-border-subtle bg-surface-2 px-3 py-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p
                      className="truncate font-mono-value text-xs text-accent"
                      title={lifecycleTraceTitle(trace)}
                    >
                      {shortLifecycleTraceId(trace)}
                    </p>
                    <p className="mt-1 text-xs text-text-tertiary">
                      {candidateText(trace.latest_stage) || '--'} ·{' '}
                      {candidateText(trace.latest_status) || '--'}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`badge ${lifecycleStatusBadgeClass(trace)}`}>
                      {lifecycleStatusLabel(trace)}
                    </span>
                    <span className="badge badge-neutral">
                      {lifecycleNextActionLabel(trace.next_action)}
                    </span>
                    <span className="font-mono-value text-xs text-text-tertiary">
                      {numericResultField(trace.event_count)} events
                    </span>
                  </div>
                </div>
                {safeLifecycleNote(trace.last_note) && (
                  <p
                    className="mt-2 truncate text-xs text-text-secondary"
                    title={safeLifecycleNote(trace.last_note)}
                  >
                    {safeLifecycleNote(trace.last_note)}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-xs text-text-tertiary">
            {loading ? '正在读取生命周期历史。' : '暂无匹配的生命周期记录。'}
          </p>
        )}
      </div>
    </section>
  );
});

export const LifecycleMetric = memo(function LifecycleMetric({
  label,
  tone = 'text-text-primary',
  value,
}: {
  label: string;
  tone?: string;
  value: string;
}) {
  return (
    <div className="min-w-0 border-l border-border-subtle pl-3">
      <p className="text-2xs font-semibold uppercase tracking-wider text-text-tertiary">{label}</p>
      <p className={`font-mono-value text-base font-medium ${tone}`}>{value}</p>
    </div>
  );
});
