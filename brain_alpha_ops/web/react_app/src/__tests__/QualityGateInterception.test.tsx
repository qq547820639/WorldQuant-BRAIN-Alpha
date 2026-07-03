/**
 * Workstream F2.4 — Quality gate interception display behavior tests.
 *
 * Behavior under test:
 *  - QualityCheckPanel renders the summary header with counts and the
 *    10-metric quality strip (候选 / 本地通过 / 本地阻断 / 仿真分数 /
 *    待官方复核 / 可用槽位 / 官方仿真 / 阻断复核候选 / 提交证据缺口 / 官方接口).
 *  - QualityCheckPanel renders threshold text and blocking reasons
 *    (interception reasons surfaced via readinessReasonLabel, e.g.
 *    high_cloud_similarity → "云端相似度过高",
 *    lifecycle_history_blocked → "历史生命周期要求归档").
 *  - QualityCheckPanel renders loading state and error state with retry.
 *  - ActionableError renders the structured payload (cause / impact_scope /
 *    suggested_action / recovery button) and surfaces retry_after for
 *    official_rate_limited; falls back to ErrorCard when no payload.
 *
 * Mocks useGlobalData / useApi so QualityCheckPanel receives deterministic
 * slots + readiness data without network or provider nesting.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { BacktestSlotsResponse, SubmitReadinessResponse } from '@/types';
import type { ActionableErrorPayload } from '@/types';

// ── Module mocks ───────────────────────────────────────────

const slotsState = {
  data: null as BacktestSlotsResponse | null,
  error: null as string | null,
  loading: false,
  lastErrorMeta: null,
};
const readinessState = {
  data: null as SubmitReadinessResponse | null,
  error: null as string | null,
  loading: false,
  lastErrorMeta: null,
  call: vi.fn(),
};

vi.mock('@/hooks/useGlobalData', () => ({
  useGlobalData: () => ({
    slots: slotsState,
    candidates: { data: null, error: null, loading: false, lastErrorMeta: null },
    cloud: { data: null, error: null, loading: false, lastErrorMeta: null },
    config: { data: null, error: null, loading: false, lastErrorMeta: null },
    refreshAll: vi.fn(),
  }),
}));

vi.mock('@/hooks/useApi', () => ({
  useApi: () => readinessState,
}));

// Stub CandidateTable to avoid pulling the virtualizer + useGlobalData chain.
vi.mock('@/components/CandidateTable', () => ({
  default: () => <div data-testid="candidate-table-stub" />,
}));

import QualityCheckPanel from '@/components/QualityCheckPanel';
import ActionableError from '@/components/ActionableError';

// ── Fixtures ───────────────────────────────────────────────

const SLOT_PAYLOAD: BacktestSlotsResponse = {
  ok: true,
  slot_limit: 3,
  active_count: 1,
  slots: [{ slot: 1, status: 'RUNNING' }],
  queue_summary: {
    candidate_count: 12,
    local_valid_count: 8,
    blocked_candidate_count: 4,
    above_simulation_score_count: 5,
    review_candidate_count: 3,
    open_slot_count: 2,
    slot_limit: 3,
    submit_evidence_blocking_count: 1,
    official_api_called: true,
    next_action: 'trusted_environment_official_simulation_required',
    top_blocking_reasons: [
      { reason: 'high_cloud_similarity', count: 2 },
      { reason: 'lifecycle_history_blocked', count: 1 },
    ],
    top_submit_blocking_reasons: [{ reason: 'missing_official_metrics', count: 1 }],
  },
};

const READINESS_PAYLOAD: SubmitReadinessResponse = {
  ok: true,
  official_api_called: true,
  eligible_count: 2,
  summary_counts: {
    officially_simulated: 4,
    submission_ready: 2,
  },
  threshold_summary: {
    min_sharpe: 1.25,
    min_fitness: 1.0,
    platform_max_turnover: 0.7,
    max_self_correlation: 0.7,
  },
  top_blocking_reasons: [{ reason: 'local_backtest_failed', count: 3 }],
  top_family_blocking_reasons: [{ reason: 'candidate_family_missing_official_metrics', count: 1 }],
};

const resetState = () => {
  slotsState.data = SLOT_PAYLOAD;
  slotsState.error = null;
  slotsState.loading = false;
  readinessState.data = READINESS_PAYLOAD;
  readinessState.error = null;
  readinessState.loading = false;
  readinessState.call.mockResolvedValue(READINESS_PAYLOAD);
};

const NOTIFY = vi.fn();

// ── QualityCheckPanel — summary strip ──────────────────────

describe('QualityCheckPanel — summary strip', () => {
  beforeEach(() => {
    resetState();
    NOTIFY.mockClear();
  });

  it('renders the header with local/official/eligible counts', () => {
    render(<QualityCheckPanel notify={NOTIFY} />);
    expect(screen.getByText('达标检查')).toBeDefined();
    // localValid=8, officiallySimulated=4, eligible=2
    expect(screen.getByText(/本地通过 8/)).toBeDefined();
    expect(screen.getByText(/官方仿真 4/)).toBeDefined();
    expect(screen.getByText(/复核候选 2/)).toBeDefined();
  });

  it('renders all 10 quality metrics with values', () => {
    render(<QualityCheckPanel notify={NOTIFY} />);
    // Labels (unique text).
    expect(screen.getByText('候选')).toBeDefined();
    expect(screen.getByText('本地通过')).toBeDefined();
    expect(screen.getByText('本地阻断')).toBeDefined();
    expect(screen.getByText('仿真分数')).toBeDefined();
    expect(screen.getByText('待官方复核')).toBeDefined();
    expect(screen.getByText('可用槽位')).toBeDefined();
    expect(screen.getByText('官方仿真')).toBeDefined();
    expect(screen.getByText('阻断复核候选')).toBeDefined();
    expect(screen.getByText('提交证据缺口')).toBeDefined();
    expect(screen.getByText('官方接口')).toBeDefined();
    // Distinct values.
    expect(screen.getByText('12')).toBeDefined(); // total
    expect(screen.getByText('5')).toBeDefined(); // aboveSimulationScore
    expect(screen.getByText('1')).toBeDefined(); // submitEvidenceBlocked
    expect(screen.getByText('已调用')).toBeDefined(); // officialApiCalled
    // "4" appears for both 本地阻断 and 官方仿真.
    expect(screen.getAllByText('4').length).toBe(2);
    // openSlots/slotLimit rendered as "2/3".
    expect(screen.getByText('2/3')).toBeDefined();
  });

  it('renders threshold text with sharpe/fitness/turnover/correlation', () => {
    render(<QualityCheckPanel notify={NOTIFY} />);
    expect(screen.getByText(/夏普 1.25/)).toBeDefined();
    expect(screen.getByText(/适应度 1\b/)).toBeDefined();
    expect(screen.getByText(/换手率 <= 0.70/)).toBeDefined();
    expect(screen.getByText(/自相关 <= 0.70/)).toBeDefined();
  });

  it('renders interception blocking reasons via readinessReasonLabel', () => {
    render(<QualityCheckPanel notify={NOTIFY} />);
    // queue.top_blocking_reasons → high_cloud_similarity + lifecycle_history_blocked
    expect(screen.getByText(/云端相似度过高 2/)).toBeDefined();
    expect(screen.getByText(/历史生命周期要求归档 1/)).toBeDefined();
    // queue.top_submit_blocking_reasons → missing_official_metrics
    expect(screen.getAllByText(/缺少官方仿真指标 1/).length).toBeGreaterThan(0);
    // readiness.top_family_blocking_reasons
    expect(screen.getByText(/候选族缺少官方仿真指标 1/)).toBeDefined();
  });

  it('renders the next-action label derived from queue.next_action', () => {
    render(<QualityCheckPanel notify={NOTIFY} />);
    expect(screen.getByText(/在可信环境运行官方仿真/)).toBeDefined();
  });

  it('falls back to "等待候选和门禁数据" when next_action is empty', () => {
    resetState();
    slotsState.data = {
      ...SLOT_PAYLOAD,
      queue_summary: { ...SLOT_PAYLOAD.queue_summary, next_action: '' },
    };
    render(<QualityCheckPanel notify={NOTIFY} />);
    expect(screen.getByText(/等待候选和门禁数据/)).toBeDefined();
  });
});

// ── QualityCheckPanel — loading & error states ─────────────

describe('QualityCheckPanel — loading and error states', () => {
  beforeEach(() => resetState());

  it('renders the loading placeholder while slots or readiness is loading', () => {
    resetState();
    slotsState.loading = true;
    readinessState.loading = false;
    render(<QualityCheckPanel notify={NOTIFY} />);
    expect(screen.getByText('正在加载质量门禁快照。')).toBeDefined();
  });

  it('renders an alert with retry button when slots fails to load', () => {
    resetState();
    slotsState.error = '后端连接超时';
    const { container } = render(<QualityCheckPanel notify={NOTIFY} />);
    const alert = container.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert?.textContent).toContain('达标检查数据加载失败');
    expect(alert?.textContent).toContain('后端连接超时');
    const retry = screen.getByText('重试');
    expect(retry).toBeDefined();
    fireEvent.click(retry);
    expect(readinessState.call).toHaveBeenCalled();
  });

  it('renders "暂无" placeholders when no blocking reasons are present', () => {
    resetState();
    slotsState.data = {
      ...SLOT_PAYLOAD,
      queue_summary: {
        ...SLOT_PAYLOAD.queue_summary,
        top_blocking_reasons: [],
        top_submit_blocking_reasons: [],
      },
    };
    readinessState.data = {
      ...READINESS_PAYLOAD,
      top_blocking_reasons: [],
      top_family_blocking_reasons: [],
    };
    render(<QualityCheckPanel notify={NOTIFY} />);
    const placeholders = screen.getAllByText(
      (content, element) => element?.tagName === 'P' && content.includes('暂无')
    );
    expect(placeholders.length).toBeGreaterThanOrEqual(3);
  });
});

// ── ActionableError — payload rendering ────────────────────

const makePayload = (overrides: Partial<ActionableErrorPayload> = {}): ActionableErrorPayload => ({
  kind: 'official_rate_limited',
  cause: 'BRAIN 官方接口限流（429）。',
  impact_scope: '当前候选无法提交官方仿真',
  suggested_action: '请稍后重试或查看回测队列。',
  recovery_action_id: 'review_official_slots',
  recovery_url: '/backtests',
  i18n_key: 'error.official_rate_limited',
  severity: 'warning',
  context: {},
  ...overrides,
});

describe('ActionableError — structured payload rendering', () => {
  it('renders cause, impact_scope, suggested_action and recovery button', () => {
    render(<ActionableError payload={makePayload()} />);
    expect(screen.getByText('BRAIN 官方接口限流（429）。')).toBeDefined();
    expect(screen.getByText('当前候选无法提交官方仿真')).toBeDefined();
    expect(screen.getByText('请稍后重试或查看回测队列。')).toBeDefined();
    // recovery_action_id review_official_slots → "查看回测队列"
    expect(screen.getByText('查看回测队列')).toBeDefined();
  });

  it('renders the kind badge label and role=alert for a11y', () => {
    const { container } = render(<ActionableError payload={makePayload()} />);
    const alert = container.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert?.getAttribute('aria-live')).toBe('assertive');
    // kind=official_rate_limited → "官方限流"
    expect(screen.getByText('官方限流')).toBeDefined();
    expect(alert?.getAttribute('data-error-kind')).toBe('official_rate_limited');
  });

  it('surfaces retry_after text for official_rate_limited when context.retry_after > 0', () => {
    render(<ActionableError payload={makePayload({ context: { retry_after: 30 } })} />);
    expect(screen.getByText(/预计 30 秒后恢复/)).toBeDefined();
  });

  it('omits retry_after text when retry_after is missing or zero', () => {
    const { rerender } = render(<ActionableError payload={makePayload({ context: {} })} />);
    expect(screen.queryByText(/秒后恢复/)).toBeNull();

    rerender(<ActionableError payload={makePayload({ context: { retry_after: 0 } })} />);
    expect(screen.queryByText(/秒后恢复/)).toBeNull();
  });

  it('omits impact_scope and suggested_action paragraphs when empty', () => {
    render(
      <ActionableError
        payload={makePayload({ impact_scope: '', suggested_action: '', recovery_action_id: '' })}
      />
    );
    expect(screen.queryByText('影响范围')).toBeNull();
    expect(screen.queryByText('建议操作')).toBeNull();
    expect(screen.queryByText('查看回测队列')).toBeNull();
  });
});

// ── ActionableError — recovery dispatch ────────────────────

describe('ActionableError — recovery dispatch', () => {
  it('navigates via onNavigate when recovery_url maps to a CardViewId', () => {
    const onNavigate = vi.fn();
    render(
      <ActionableError
        payload={makePayload({ recovery_url: '/config', recovery_action_id: 'reconnect_session' })}
        onNavigate={onNavigate}
      />
    );
    fireEvent.click(screen.getByText('重新连接'));
    expect(onNavigate).toHaveBeenCalledWith('config');
  });

  it('calls onRecoveryAction for non-navigation recovery urls', () => {
    const onNavigate = vi.fn();
    const onRecoveryAction = vi.fn();
    render(
      <ActionableError
        payload={makePayload({
          recovery_url: '/operations/refresh',
          recovery_action_id: 'refresh_cache',
        })}
        onNavigate={onNavigate}
        onRecoveryAction={onRecoveryAction}
      />
    );
    fireEvent.click(screen.getByText('刷新缓存'));
    expect(onNavigate).not.toHaveBeenCalled();
    expect(onRecoveryAction).toHaveBeenCalledTimes(1);
    expect(onRecoveryAction.mock.calls[0][0]).toBe('refresh_cache');
  });
});

// ── ActionableError — fallback & classification ────────────

describe('ActionableError — fallback and classification', () => {
  it('falls back to ErrorCard when no payload and error is a string', () => {
    render(<ActionableError error="网络断开" />);
    // String errors are classified (network_timeout) and rendered via the structured card.
    expect(screen.getByText('网络超时')).toBeDefined();
  });

  it('classifies a 429 status code as official_rate_limited and renders the fallback payload', () => {
    render(<ActionableError error={{ status_code: 429 }} />);
    expect(screen.getByText('官方限流')).toBeDefined();
    expect(screen.getByText(/BRAIN 官方接口限流/)).toBeDefined();
  });

  it('classifies a 503 status code as local_service_unavailable', () => {
    render(<ActionableError error={{ status_code: 503 }} />);
    expect(screen.getByText('本地服务未启动')).toBeDefined();
  });

  it('renders the title override when provided', () => {
    render(<ActionableError payload={makePayload()} title="自定义错误标题" />);
    expect(screen.getByText('自定义错误标题')).toBeDefined();
  });
});
