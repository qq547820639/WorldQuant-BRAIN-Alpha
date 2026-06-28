import type { BacktestSlotsResponse } from '@/types';

export const ACTIVE_BACKTEST_SLOT_STATUSES = new Set([
  'SUBMITTED',
  'RUNNING',
  'PENDING',
  'STARTING',
  'RATE_LIMITED',
  'POLL_ERROR',
  'CAPACITY_WAIT',
]);

export function isActiveBacktestSlotStatus(status: unknown) {
  const text = String((status as string | number | boolean | null | undefined) || '').toUpperCase();
  return ACTIVE_BACKTEST_SLOT_STATUSES.has(text);
}

export function backtestSlotLimit(
  payload: Pick<BacktestSlotsResponse, 'slot_limit' | 'queue_summary'> | null | undefined,
  fallback = 3
) {
  const fromPayload = Number(payload?.slot_limit);
  const fromSummary = Number(payload?.queue_summary?.slot_limit);
  const value = Number.isFinite(fromPayload) && fromPayload > 0 ? fromPayload : fromSummary;
  if (Number.isFinite(value) && value > 0) return Math.max(3, Math.trunc(value));
  return Math.max(0, Math.trunc(fallback));
}

export function backtestActiveCount(
  payload: Pick<BacktestSlotsResponse, 'active_count' | 'slots'> | null | undefined
) {
  const fromPayload = Number(payload?.active_count);
  if (Number.isFinite(fromPayload) && fromPayload >= 0) return Math.trunc(fromPayload);
  const slots = Array.isArray(payload?.slots) ? payload.slots : [];
  return slots.filter((slot) => isActiveBacktestSlotStatus(slot.status)).length;
}
