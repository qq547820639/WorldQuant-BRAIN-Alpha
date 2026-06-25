/**
 * View helpers extracted from App.tsx (Phase 2.1).
 */

import type { BacktestSlotsResponse, PhaseApiStatus } from '@/types';
import { backtestActiveCount, backtestSlotLimit } from '@/utils/backtestSlots';

export function formatBacktestBadge(data?: BacktestSlotsResponse | null): string | undefined {
  if (!data) return undefined;
  const limit = backtestSlotLimit(data, 0);
  if (limit <= 0) return undefined;
  const active = backtestActiveCount(data);
  return `${active}/${limit}`;
}

export function formatCloudBadge(total?: number): string | undefined {
  if (total == null) return undefined;
  return total >= 1000 ? `${(total / 1000).toFixed(1)}k` : String(total);
}

export function cloudBadgeTotal(
  payload?: { count?: number; total?: number; summary?: Record<string, unknown> } | null
): number | undefined {
  const summary = payload?.summary || {};
  return numericBadgeValue(
    payload?.count ?? payload?.total ?? summary.count ?? summary.total ?? summary.total_count
  );
}

function numericBadgeValue(value: unknown): number | undefined {
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

export function topbarConnectionStatus({
  connected,
  contextFresh,
  phaseStatus = 'ready',
}: {
  connected: boolean;
  contextFresh: boolean;
  phaseStatus?: PhaseApiStatus;
}) {
  if (phaseStatus === 'loading') {
    return {
      label: '状态读取中',
      tone: 'loading',
      dotClass: 'status-dot-pending',
      title: '正在读取本地 session 与缓存状态；读取完成前不判定为未连接。',
    };
  }
  if (phaseStatus === 'error') {
    return {
      label: '状态读取失败',
      tone: 'read-error',
      dotClass: 'status-dot-warning',
      title: '暂时无法确认 BRAIN 账户连接和本地缓存状态。',
    };
  }
  if (connected && contextFresh) {
    return {
      label: '已连接 · 在线模式',
      tone: 'connected',
      dotClass: 'status-dot-active',
      title: 'BRAIN 账户已连接，本地缓存可用。在线模式：可使用全部功能。',
    };
  }
  if (connected) {
    return {
      label: '已连接 · 待同步',
      tone: 'connected',
      dotClass: 'status-dot-warning',
      title: 'BRAIN 账户已连接，但还没有完整本地缓存。',
    };
  }
  if (contextFresh) {
    return {
      label: '缓存模式 · 离线可用',
      tone: 'cache-ready',
      dotClass: 'status-dot-warning',
      title: 'BRAIN 账户未连接；本地缓存可用于非提交候选流程，官方同步、回测和提交前复核仍需连接。',
    };
  }
  return {
    label: '未连接 · 需登录',
    tone: 'disconnected',
    dotClass: 'status-dot-error',
    title: 'BRAIN 账户未连接，且未检测到完整本地缓存。请填写凭据并测试连接。',
  };
}

export function fmtEta(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `${s}s`;
}
