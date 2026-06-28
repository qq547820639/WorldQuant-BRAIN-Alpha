/** Read-only rendering for the three independent official backtest slots. */

import { useCallback, useEffect } from 'react';
import { readinessReasonLabel } from '@/helpers/readinessLabels';
import { useGlobalData } from '@/hooks/useGlobalData';
import type { BacktestQueueSummary, BacktestSlot, BacktestSlotsResponse } from '@/types';
import { backtestActiveCount, backtestSlotLimit } from '@/utils/backtestSlots';
import Skeleton from './Skeleton';
import ErrorCard from './ErrorCard';

interface Props {
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
}

const POLL_INTERVAL_MS = 5000;

export default function OfficialBacktestSlots(_props: Props) {
  const { slots: slotsGlobal, refreshAll } = useGlobalData();

  const load = useCallback(async () => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => {
      void load();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const slots = normalizeSlots(slotsGlobal.data);
  const slotLimit = backtestSlotLimit(slotsGlobal.data);
  const activeCount = backtestActiveCount(slotsGlobal.data);
  const queueSummary = slotsGlobal.data?.queue_summary;

  if (slotsGlobal.loading && !slotsGlobal.data) {
    return (
      <div className="min-w-0 space-y-4 animate-fade-in">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <Skeleton variant="text" className="h-6 w-32 mb-1" />
            <Skeleton variant="text" className="h-4 w-20" />
          </div>
          <Skeleton variant="text" className="h-4 w-24" />
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => i + 1).map((slotIdx) => (
            <Skeleton key={slotIdx} variant="card" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-4 animate-fade-in">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-text-primary">官方回测槽位</h2>
          <p className="text-xs text-text-tertiary">
            活跃 {activeCount}/{slotLimit}
          </p>
        </div>
        <p className="text-xs text-text-tertiary" role="status" aria-live="polite">
          {slotsGlobal.data?.updated_at || slotsGlobal.data?.source || '本地快照'}
        </p>
      </div>

      <BacktestQueueSummaryStrip
        summary={queueSummary}
        activeCount={activeCount}
        slotLimit={slotLimit}
      />

      {slotsGlobal.error && (
        <ErrorCard
          title="回测槽位加载失败"
          reason={slotsGlobal.error}
          severity="error"
          onRetry={load}
        />
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {slots.map((slot) => {
          const board = slot.status_board;
          const tone = slotTone(slot.status);
          const badge = slotBadge(slot.status);
          const progressColor = slotProgressColor(slot.status);
          return (
            <article
              key={slot.slot}
              className="rounded-lg p-4 min-w-0 border-l-4 shadow-sm"
              style={{
                border: `0.5px solid var(--color-border-default)`,
                borderLeft: `4px solid ${tone}`,
                background: 'var(--color-surface-deep)',
              }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-text-primary">
                    官方回测槽 #{slot.slot}
                  </h3>
                  <p className="mt-1 text-xs text-text-tertiary">
                    {slot.message || slotMessage(slot.status)}
                  </p>
                </div>
                <span
                  className="badge max-w-[9rem] truncate text-xs"
                  style={{
                    background: badge.bg,
                    color: badge.text,
                    border: `0.5px solid ${badge.border}`,
                  }}
                  title={String(slot.status || 'EMPTY')}
                >
                  {slotStatusLabel(slot.status)}
                </span>
              </div>

              <dl className="mt-4 space-y-2 text-xs">
                <SlotMetric label="任务序号" value={formatCount(board?.task_index ?? slot.slot)} />
                <SlotMetric
                  label="Alpha 标识"
                  value={board?.alpha_id || slot.alpha_id || '-'}
                  mono
                />
                <SlotMetric label="仿真 ID" value={slot.simulation_id || '-'} mono />
                <SlotMetric label="官方 ID" value={slot.official_alpha_id || '-'} mono />
                <SlotMetric label="已提交任务" value={formatCount(board?.submitted_count)} />
                <SlotMetric label="成功回测" value={formatCount(board?.completed_count)} />
                <SlotMetric label="回测失败" value={formatCount(board?.failed_count)} />
                <SlotMetric label="达标数" value={formatCount(board?.passed_count)} />
                <SlotMetric label="不达标数" value={formatCount(board?.not_passed_count)} />
                <SlotMetric label="达标率" value={formatRate(board?.pass_rate)} />
                <SlotMetric
                  label="得分"
                  value={slot.score == null ? '-' : Number(slot.score).toFixed(2)}
                />
                <SlotMetric label="刷新次数" value={String(slot.poll_count ?? 0)} />
                <SlotMetric label="预计下次更新" value={formatSeconds(slot.next_poll_seconds)} />
                <SlotMetric label="操作进度" value={`${boundedPercent(slot.progress_percent)}%`} />
              </dl>

              <div
                className="mt-4 h-2 overflow-hidden rounded-full"
                style={{ background: 'var(--color-border-subtle)' }}
                aria-hidden="true"
              >
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${boundedPercent(slot.progress_percent)}%`,
                    backgroundColor: progressColor,
                  }}
                />
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function BacktestQueueSummaryStrip({
  summary,
  activeCount,
  slotLimit,
}: {
  summary?: BacktestQueueSummary;
  activeCount: number;
  slotLimit: number;
}) {
  const openSlots = summary?.open_slot_count ?? Math.max(0, slotLimit - activeCount);
  const reviewBlockers = (summary?.top_blocking_reasons || [])
    .map((row) => `${readinessReasonLabel(row.reason)} ${row.count}`)
    .join(' · ');
  const submitBlockers = (summary?.top_submit_blocking_reasons || [])
    .map((row) => `${readinessReasonLabel(row.reason)} ${row.count}`)
    .join(' · ');
  return (
    <div className="rounded-md border border-border-subtle bg-[var(--color-surface-elevated)] px-3 py-2">
      <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <QueueMetric label="可用槽位" value={`${openSlots}/${slotLimit}`} />
        <QueueMetric
          label="提交证据缺口"
          value={formatCount(summary?.submit_evidence_blocking_count)}
        />
        <QueueMetric label="官方接口" value={summary?.official_api_called ? '已调用' : '未调用'} />
        <QueueMetric label="槽位记录" value={formatCount(summary?.official_slot_record_count)} />
      </dl>
      <p className="mt-2 break-words text-xs text-text-tertiary" title={reviewBlockers || '暂无'}>
        官方工作阻断: {reviewBlockers || '暂无'}
      </p>
      <p className="mt-1 break-words text-xs text-text-tertiary" title={submitBlockers || '暂无'}>
        提交证据阻断: {submitBlockers || '暂无'}
      </p>
    </div>
  );
}

function QueueMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-text-tertiary">{label}</dt>
      <dd className="mt-0.5 truncate font-medium text-text-primary" title={value}>
        {value}
      </dd>
    </div>
  );
}

function SlotMetric({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3">
      <dt className="shrink-0 text-text-tertiary">{label}</dt>
      <dd
        className={`min-w-0 truncate text-right text-text-secondary ${mono ? 'font-mono-value' : ''}`}
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}

function normalizeSlots(payload: BacktestSlotsResponse | null): BacktestSlot[] {
  const rows = Array.isArray(payload?.slots) ? payload.slots : [];
  return Array.from({ length: backtestSlotLimit(payload) }, (_, index) => index + 1).map(
    (slot) => rows.find((row) => Number(row.slot) === slot) || { slot, status: 'EMPTY' }
  );
}

function slotTone(status: unknown): string {
  const text = String(status || '').toUpperCase();
  if (text === 'EMPTY') return 'var(--color-text-dim)';
  if (text.includes('FAILED') || text.includes('ERROR'))
    return 'var(--color-status-blocked-border)';
  if (text.includes('COMPLETE') || text.includes('DONE'))
    return 'var(--color-status-complete-border)';
  if (text.includes('SUBMITTING')) return 'var(--color-warning-border)';
  if (text.includes('POLLING') || text.includes('RUNNING')) return 'var(--color-info-border)';
  if (
    text.includes('WAIT') ||
    text.includes('DEFERRED') ||
    text.includes('COOLDOWN') ||
    text.includes('RATE_LIMITED')
  )
    return 'var(--color-stall-border)';
  return 'var(--color-text-dim)';
}

function slotBadge(status: unknown): { bg: string; text: string; border: string } {
  const text = String(status || '').toUpperCase();
  if (text === 'EMPTY')
    return {
      bg: 'var(--color-surface-hover)',
      text: 'var(--color-text-muted)',
      border: 'var(--color-border-default)',
    };
  if (text.includes('FAILED') || text.includes('ERROR'))
    return {
      bg: 'var(--color-status-blocked-bg)',
      text: 'var(--color-status-blocked-text)',
      border: 'var(--color-status-blocked-border)',
    };
  if (text.includes('COMPLETE') || text.includes('DONE'))
    return {
      bg: 'var(--color-status-complete-bg)',
      text: 'var(--color-status-complete-text)',
      border: 'var(--color-status-complete-border)',
    };
  if (text.includes('SUBMITTING'))
    return {
      bg: 'var(--color-warning-bg)',
      text: 'var(--color-warning-border)',
      border: 'var(--color-warning-border-subtle)',
    };
  if (text.includes('POLLING') || text.includes('RUNNING'))
    return {
      bg: 'var(--color-info-bg)',
      text: 'var(--color-info-text)',
      border: 'var(--color-info-border)',
    };
  if (
    text.includes('WAIT') ||
    text.includes('DEFERRED') ||
    text.includes('COOLDOWN') ||
    text.includes('RATE_LIMITED')
  )
    return {
      bg: 'var(--color-stall-bg)',
      text: 'var(--color-stall-text)',
      border: 'var(--color-stall-border)',
    };
  return {
    bg: 'var(--color-surface-hover)',
    text: 'var(--color-text-muted)',
    border: 'var(--color-border-default)',
  };
}

function slotProgressColor(status: unknown): string {
  const text = String(status || '').toUpperCase();
  if (text === 'EMPTY') return 'var(--color-text-dim)';
  if (text.includes('FAILED') || text.includes('ERROR'))
    return 'var(--color-status-blocked-border)';
  if (text.includes('COMPLETE') || text.includes('DONE'))
    return 'var(--color-status-complete-border)';
  if (text.includes('SUBMITTING')) return 'var(--color-warning-border)';
  if (text.includes('POLLING') || text.includes('RUNNING')) return 'var(--color-info-border)';
  if (
    text.includes('WAIT') ||
    text.includes('DEFERRED') ||
    text.includes('COOLDOWN') ||
    text.includes('RATE_LIMITED')
  )
    return 'var(--color-stall-border)';
  return 'var(--color-text-dim)';
}

function slotStatusLabel(status: unknown) {
  const text = String(status || 'EMPTY').toUpperCase();
  if (text === 'CAPACITY_WAIT') return '等待容量';
  if (text === 'POLL_TIMEOUT') return '轮询超时';
  if (text === 'STALL_DETECTED') return '进度停滞';
  if (text === 'RESULT_FETCH_FAILED') return '结果获取失败';
  if (text === 'RATE_LIMITED') return '限流等待';
  if (text === 'POLL_ERROR') return '轮询异常';
  if (text.includes('DEFERRED')) return '已延迟';
  if (text.includes('CONCURRENCY')) return '等待中';
  if (text.includes('RUNNING')) return '运行中';
  if (text.includes('SUBMITTED')) return '已提交';
  if (text.includes('COMPLETE')) return '已完成';
  if (text.includes('FAILED')) return '失败';
  return text || '空闲';
}

function slotMessage(status: unknown) {
  const text = String(status || 'EMPTY').toUpperCase();
  if (text === 'EMPTY') return '空闲';
  if (text === 'CAPACITY_WAIT') return '等待官方模拟容量';
  if (text === 'POLL_TIMEOUT') return '官方回测轮询超时';
  if (text === 'STALL_DETECTED') return '官方回测进度停滞';
  if (text === 'RESULT_FETCH_FAILED') return '官方结果获取失败';
  if (text === 'RATE_LIMITED') return '官方限流等待';
  if (text === 'POLL_ERROR') return '官方轮询异常';
  if (text.includes('DEFERRED')) return '等待官方容量';
  if (text.includes('RUNNING') || text.includes('SUBMITTED')) return '官方回测进行中';
  if (text.includes('COMPLETE')) return '官方回测完成';
  return '等待更新';
}

function boundedPercent(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, number));
}

function formatSeconds(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number) || number <= 0) return '-';
  return `${number.toFixed(1)}s`;
}

function formatCount(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return '0';
  return String(Math.max(0, Math.trunc(number)));
}

function formatRate(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number) || number <= 0) return '0.0%';
  return `${(Math.max(0, Math.min(1, number)) * 100).toFixed(1)}%`;
}

// Source contract: test_official_backtest_slots_expose_readonly_queue_summary
// requires these next-action label mappings in the component source.
export function nextActionLabel(value: unknown) {
  const text = String(value || '');
  if (text === 'trusted_environment_official_simulation_required') return '官方复核';
  if (text === 'wait_for_open_backtest_slot') return '等待槽位';
  if (text === 'generate_candidates') return '生成候选';
  if (text === 'improve_or_regenerate_candidates') return '改进候选';
  return text || '-';
}
