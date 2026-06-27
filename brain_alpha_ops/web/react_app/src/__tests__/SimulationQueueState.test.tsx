/**
 * Workstream F2.5 — Simulation queue state display behavior tests.
 *
 * Behavior under test:
 *  - OfficialBacktestSlots renders exactly slot_limit slot cards, padding
 *    missing slots with EMPTY (空闲) status.
 *  - Each slot surfaces its status badge / message / metrics / progress bar
 *    for the key states: idle (EMPTY), submitting (SUBMITTED), polling
 *    (RUNNING/POLLING), cooldown (RATE_LIMITED/COOLDOWN/DEFERRED), done
 *    (COMPLETE), failed (FAILED).
 *  - Cooldown slots surface the remaining wait via next_poll_seconds and the
 *    "限流等待" / "等待官方容量" message.
 *  - Simulating slots surface progress_percent in the progress bar.
 *  - BacktestQueueSummaryStrip shows open slots, evidence gaps, official api.
 *  - Loading skeleton and ErrorCard retry.
 *  - ActionableError renders simulation-specific error kinds
 *    (simulation_concurrency_exceeded / network_timeout / queue_blocked).
 *
 * Mocks useGlobalData so OfficialBacktestSlots receives deterministic
 * BacktestSlotsResponse data without network or provider nesting.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { BacktestSlotsResponse, BacktestSlot } from '@/types';
import type { ActionableErrorPayload } from '@/types/errors';

// ── Module mocks ───────────────────────────────────────────

const slotsState = {
  data: null as BacktestSlotsResponse | null,
  error: null as string | null,
  loading: false,
  lastErrorMeta: null,
};
const refreshAll = vi.fn();

vi.mock('@/hooks/useGlobalData', () => ({
  useGlobalData: () => ({
    slots: slotsState,
    candidates: { data: null, error: null, loading: false, lastErrorMeta: null },
    cloud: { data: null, error: null, loading: false, lastErrorMeta: null },
    config: { data: null, error: null, loading: false, lastErrorMeta: null },
    refreshAll,
  }),
}));

import OfficialBacktestSlots from '@/components/OfficialBacktestSlots';
import ActionableError from '@/components/ActionableError';

const NOTIFY = vi.fn();

const resetState = (overrides: Partial<BacktestSlotsResponse> = {}) => {
  slotsState.data = {
    ok: true,
    slot_limit: 3,
    active_count: 0,
    slots: [],
    updated_at: '2026-06-26T10:00:00Z',
    ...overrides,
  };
  slotsState.error = null;
  slotsState.loading = false;
  refreshAll.mockClear();
};

const makeSlot = (overrides: Partial<BacktestSlot>): BacktestSlot => ({
  slot: 1,
  status: 'EMPTY',
  ...overrides,
});

// ── OfficialBacktestSlots — slot rendering ─────────────────

describe('OfficialBacktestSlots — slot rendering', () => {
  beforeEach(() => resetState());

  it('renders exactly slot_limit slot cards, padding missing slots with EMPTY', () => {
    resetState({ slot_limit: 3, active_count: 0, slots: [] });
    render(<OfficialBacktestSlots notify={NOTIFY} />);
    // Three slot headings.
    expect(screen.getByText('官方回测槽 #1')).toBeDefined();
    expect(screen.getByText('官方回测槽 #2')).toBeDefined();
    expect(screen.getByText('官方回测槽 #3')).toBeDefined();
    // EMPTY status → "空闲" badge + message.
    const idle = screen.getAllByText('空闲');
    expect(idle.length).toBe(3);
  });

  it('renders the active/limit header and updated_at source', () => {
    resetState({
      slot_limit: 3,
      active_count: 2,
      slots: [makeSlot({ slot: 1, status: 'RUNNING' }), makeSlot({ slot: 2, status: 'SUBMITTED' })],
      updated_at: '2026-06-26T12:00:00Z',
    });
    render(<OfficialBacktestSlots notify={NOTIFY} />);
    expect(screen.getByText('活跃 2/3')).toBeDefined();
    expect(screen.getByText('2026-06-26T12:00:00Z')).toBeDefined();
  });
});

// ── Slot status badges & messages ──────────────────────────

describe('OfficialBacktestSlots — slot status badges and messages', () => {
  beforeEach(() => resetState());

  const cases: Array<{ status: string; badge: string; message: string }> = [
    { status: 'SUBMITTED', badge: '已提交', message: '官方回测进行中' },
    { status: 'RUNNING', badge: '运行中', message: '官方回测进行中' },
    { status: 'COMPLETE', badge: '已完成', message: '官方回测完成' },
    { status: 'FAILED', badge: '失败', message: '等待更新' },
    { status: 'RATE_LIMITED', badge: '限流等待', message: '官方限流等待' },
    { status: 'DEFERRED', badge: '已延迟', message: '等待官方容量' },
    { status: 'CAPACITY_WAIT', badge: '等待容量', message: '等待官方模拟容量' },
    { status: 'POLL_TIMEOUT', badge: '轮询超时', message: '官方回测轮询超时' },
    { status: 'STALL_DETECTED', badge: '进度停滞', message: '官方回测进度停滞' },
  ];

  it.each(cases)(
    'renders $badge badge and $message message for status=$status',
    ({ status, badge, message }) => {
      resetState({
        slot_limit: 1,
        active_count: 1,
        slots: [makeSlot({ slot: 1, status })],
      });
      render(<OfficialBacktestSlots notify={NOTIFY} />);
      expect(screen.getByText(badge)).toBeDefined();
      expect(screen.getByText(message)).toBeDefined();
    }
  );
});

// ── Cooldown & simulating progress ─────────────────────────

describe('OfficialBacktestSlots — cooldown and simulating progress', () => {
  beforeEach(() => resetState());

  it('surfaces remaining wait via next_poll_seconds on a RATE_LIMITED slot', () => {
    resetState({
      slot_limit: 1,
      active_count: 1,
      slots: [makeSlot({ slot: 1, status: 'RATE_LIMITED', next_poll_seconds: 45.5 })],
    });
    render(<OfficialBacktestSlots notify={NOTIFY} />);
    // formatSeconds(45.5) → "45.5s"
    expect(screen.getByText('45.5s')).toBeDefined();
    expect(screen.getByText('限流等待')).toBeDefined();
  });

  it('shows "-" for next_poll_seconds when zero or missing', () => {
    resetState({
      slot_limit: 1,
      active_count: 1,
      slots: [makeSlot({ slot: 1, status: 'RUNNING', next_poll_seconds: 0 })],
    });
    render(<OfficialBacktestSlots notify={NOTIFY} />);
    const dashes = screen.getAllByText('-');
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it('renders the progress bar width from progress_percent for a RUNNING slot', () => {
    resetState({
      slot_limit: 1,
      active_count: 1,
      slots: [makeSlot({ slot: 1, status: 'RUNNING', progress_percent: 65 })],
    });
    const { container } = render(<OfficialBacktestSlots notify={NOTIFY} />);
    expect(screen.getAllByText('操作进度').length).toBeGreaterThan(0);
    expect(screen.getByText('65%')).toBeDefined();
    // The progress bar fill has width:65%.
    const fill = container.querySelector<HTMLElement>('.h-full.rounded-full');
    expect(fill).not.toBeNull();
    expect(fill.style.width).toBe('65%');
  });

  it('clamps progress_percent to [0, 100]', () => {
    resetState({
      slot_limit: 1,
      active_count: 1,
      slots: [makeSlot({ slot: 1, status: 'RUNNING', progress_percent: 150 })],
    });
    render(<OfficialBacktestSlots notify={NOTIFY} />);
    expect(screen.getByText('100%')).toBeDefined();
  });

  it('renders status_board metrics (submitted/completed/failed/passed/pass_rate)', () => {
    resetState({
      slot_limit: 1,
      active_count: 1,
      slots: [
        makeSlot({
          slot: 1,
          status: 'RUNNING',
          alpha_id: 'alpha-xyz',
          simulation_id: 'sim-001',
          official_alpha_id: 'OFF-001',
          score: 1.87,
          poll_count: 3,
          status_board: {
            task_index: 1,
            submitted_count: 10,
            completed_count: 7,
            failed_count: 2,
            passed_count: 5,
            not_passed_count: 2,
            pass_rate: 0.714,
          },
        }),
      ],
    });
    render(<OfficialBacktestSlots notify={NOTIFY} />);
    expect(screen.getByText('alpha-xyz')).toBeDefined();
    expect(screen.getByText('sim-001')).toBeDefined();
    expect(screen.getByText('OFF-001')).toBeDefined();
    expect(screen.getByText('1.87')).toBeDefined();
    expect(screen.getAllByText('3').length).toBeGreaterThan(0); // poll_count
    expect(screen.getByText('10')).toBeDefined(); // submitted_count
    expect(screen.getByText('7')).toBeDefined(); // completed_count
    // "2" appears for both failed_count and not_passed_count.
    expect(screen.getAllByText('2').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('5')).toBeDefined(); // passed_count
    expect(screen.getByText('71.4%')).toBeDefined(); // pass_rate
  });
});

// ── Queue summary strip ────────────────────────────────────

describe('OfficialBacktestSlots — queue summary strip', () => {
  beforeEach(() => resetState());

  it('renders open slots, evidence gaps, official api and blocker reasons', () => {
    resetState({
      slot_limit: 3,
      active_count: 1,
      slots: [makeSlot({ slot: 1, status: 'RUNNING' })],
      queue_summary: {
        open_slot_count: 2,
        submit_evidence_blocking_count: 3,
        official_api_called: true,
        official_slot_record_count: 5,
        top_blocking_reasons: [{ reason: 'high_cloud_similarity', count: 2 }],
        top_submit_blocking_reasons: [{ reason: 'missing_official_metrics', count: 3 }],
      },
    });
    render(<OfficialBacktestSlots notify={NOTIFY} />);
    expect(screen.getByText('可用槽位')).toBeDefined();
    expect(screen.getByText('2/3')).toBeDefined();
    expect(screen.getByText('提交证据缺口')).toBeDefined();
    expect(screen.getAllByText('3').length).toBeGreaterThan(0);
    expect(screen.getByText('已调用')).toBeDefined();
    expect(screen.getByText('5')).toBeDefined(); // slot_record_count
    expect(screen.getByText(/云端相似度过高 2/)).toBeDefined();
    expect(screen.getByText(/缺少官方仿真指标 3/)).toBeDefined();
  });

  it('shows "暂无" placeholders when no blocking reasons', () => {
    resetState({
      slot_limit: 1,
      slots: [],
      queue_summary: { top_blocking_reasons: [], top_submit_blocking_reasons: [] },
    });
    render(<OfficialBacktestSlots notify={NOTIFY} />);
    const placeholders = screen.getAllByText(
      (content, element) => element?.tagName === 'P' && content.includes('暂无')
    );
    expect(placeholders.length).toBe(2);
  });
});

// ── Loading & error states ─────────────────────────────────

describe('OfficialBacktestSlots — loading and error states', () => {
  beforeEach(() => resetState());

  it('renders skeleton cards while loading and no data yet', () => {
    resetState();
    slotsState.loading = true;
    slotsState.data = null;
    const { container } = render(<OfficialBacktestSlots notify={NOTIFY} />);
    // Skeleton renders placeholder cards (no slot headings).
    expect(screen.queryByText('官方回测槽 #1')).toBeNull();
    // Skeleton uses the animate-pulse class.
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('renders ErrorCard with retry when slots fail to load', () => {
    resetState();
    slotsState.error = '官方接口不可达';
    render(<OfficialBacktestSlots notify={NOTIFY} />);
    expect(screen.getByText('回测槽位加载失败')).toBeDefined();
    expect(screen.getByText(/官方接口不可达/)).toBeDefined();
    const retry = screen.getByText('重试');
    fireEvent.click(retry);
    expect(refreshAll).toHaveBeenCalled();
  });
});

// ── ActionableError — simulation-specific error kinds ──────

const makePayload = (
  kind: 'simulation_concurrency_exceeded' | 'network_timeout' | 'queue_blocked',
  overrides: Partial<ActionableErrorPayload> = {}
): ActionableErrorPayload => {
  const base: ActionableErrorPayload = {
    kind,
    cause: '',
    impact_scope: '',
    suggested_action: '',
    recovery_action_id: 'wait_and_retry',
    recovery_url: '/backtests',
    i18n_key: `error.${kind}`,
    severity: 'warning',
    context: {},
    ...overrides,
  };
  return base;
};

describe('ActionableError — simulation queue error kinds', () => {
  it('renders simulation_concurrency_exceeded with "并发超限" badge and recovery CTA', () => {
    render(
      <ActionableError
        payload={makePayload('simulation_concurrency_exceeded', {
          cause: 'BRAIN 回测并发槽位已满。',
          impact_scope: '新提交的仿真请求被拒绝',
          suggested_action: '请等待已有回测完成后再提交。',
          recovery_action_id: 'review_official_slots',
        })}
      />
    );
    expect(screen.getByText('并发超限')).toBeDefined();
    expect(screen.getByText('BRAIN 回测并发槽位已满。')).toBeDefined();
    expect(screen.getByText('新提交的仿真请求被拒绝')).toBeDefined();
    expect(screen.getByText('请等待已有回测完成后再提交。')).toBeDefined();
    expect(screen.getByText('查看回测队列')).toBeDefined();
  });

  it('renders network_timeout with "网络超时" badge and "稍后重试" CTA', () => {
    const onRecoveryAction = vi.fn();
    render(
      <ActionableError
        payload={makePayload('network_timeout', {
          cause: '网络请求超时。',
          suggested_action: '请稍后重试或检查网络状态。',
          recovery_action_id: 'wait_and_retry',
          recovery_url: '/operations/refresh',
        })}
        onRecoveryAction={onRecoveryAction}
      />
    );
    expect(screen.getByText('网络超时')).toBeDefined();
    expect(screen.getByText('网络请求超时。')).toBeDefined();
    fireEvent.click(screen.getByText('稍后重试'));
    expect(onRecoveryAction).toHaveBeenCalledWith('wait_and_retry', expect.any(Object));
  });

  it('renders queue_blocked with "队列阻塞" badge', () => {
    render(
      <ActionableError
        payload={makePayload('queue_blocked', {
          cause: '官方模拟队列阻塞。',
          suggested_action: '请在回测监控查看队列状态。',
          recovery_action_id: 'review_official_slots',
        })}
      />
    );
    expect(screen.getByText('队列阻塞')).toBeDefined();
    expect(screen.getByText('官方模拟队列阻塞。')).toBeDefined();
    expect(screen.getByText('请在回测监控查看队列状态。')).toBeDefined();
  });

  it('classifies a 408 status as network_timeout and 503 as local_service_unavailable', () => {
    const { rerender } = render(<ActionableError error={{ status_code: 408 }} />);
    expect(screen.getByText('网络超时')).toBeDefined();

    rerender(<ActionableError error={{ status_code: 503 }} />);
    expect(screen.getByText('本地服务未启动')).toBeDefined();
  });
});
