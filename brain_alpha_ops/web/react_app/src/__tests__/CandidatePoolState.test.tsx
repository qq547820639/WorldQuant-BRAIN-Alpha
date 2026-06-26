/**
 * Workstream F2.2 — Candidate pool state display behavior tests.
 *
 * Behavior under test:
 *  - CandidateTableDesktop renders candidates with lifecycle status badges.
 *  - FilterToolbar input drives candidate filtering.
 *  - Clicking the 评分 row action fires onScore(candidate) — opens detail.
 *  - Empty state + loading skeleton.
 *
 * Mounts presentational subcomponents directly to avoid pulling
 * useGlobalData / useApi / useSseManager providers.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CandidateTableDesktop from '@/components/CandidateTableDesktop';
import CandidateTableLoading from '@/components/CandidateTableLoading';
import { FilterToolbar } from '@/components/CandidateTableToolbarFilterToolbar';
import {
  candidateMatchesQueueView,
  statusBadgeClass,
} from '@/components/CandidateTableUtils';
import type { Candidate, CandidateCheckResult } from '@/types';

// jsdom has no real layout, so the default @tanstack/react-virtual
// virtualizer returns zero visible items. Stub it to expose all items.
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getTotalSize: () => count * 48,
    getVirtualItems: () =>
      Array.from({ length: count }, (_, index) => ({
        index,
        start: index * 48,
        key: `v_${index}`,
        size: 48,
        lane: 0,
      })),
    measureElement: () => {},
  }),
}));

const makeCandidate = (overrides: Partial<Candidate>): Candidate => ({
  alpha_id: 'alpha-default',
  expression: 'rank(close)',
  family: 'price_volume',
  hypothesis: 'momentum',
  lifecycle_status: 'draft',
  ...overrides,
});

const baseDesktopProps = (overrides: Record<string, unknown> = {}) => ({
  candidates: [] as Candidate[],
  checkResults: new Map<string, CandidateCheckResult>(),
  selectedIds: new Set<string>(),
  onToggleSelect: vi.fn(),
  onToggleSelectAll: vi.fn(),
  sortKey: 'score' as const,
  sortAsc: false,
  onSort: vi.fn(),
  onSimulate: vi.fn(),
  onCheck: vi.fn(),
  showRowActions: false,
  showProductionControls: true,
  workflowBusy: false,
  checkingAlphaId: null,
  allCurrentPageIds: [] as string[],
  filter: '',
  onClearFilter: vi.fn(),
  onGenerateCandidates: vi.fn(),
  ...overrides,
});

// ── CandidateTableDesktop — lifecycle state badges ─────────

describe('CandidateTableDesktop — lifecycle state badges', () => {
  it('renders lifecycle_status text for each candidate', () => {
    const candidates = [
      makeCandidate({ alpha_id: 'a-draft', lifecycle_status: 'draft' }),
      makeCandidate({ alpha_id: 'a-scored', lifecycle_status: 'locally_scored' }),
      makeCandidate({
        alpha_id: 'a-queued',
        lifecycle_status: 'queued_for_simulation',
      }),
      makeCandidate({ alpha_id: 'a-sim', lifecycle_status: 'simulating' }),
    ];
    render(
      <CandidateTableDesktop
        {...baseDesktopProps({
          candidates,
          allCurrentPageIds: candidates.map((c) => c.alpha_id),
        })}
      />
    );
    expect(screen.getByText('draft')).toBeDefined();
    expect(screen.getByText('locally_scored')).toBeDefined();
    expect(screen.getByText('queued_for_simulation')).toBeDefined();
    expect(screen.getByText('simulating')).toBeDefined();
  });

  it('renders the candidate expression text and truncated alpha_id', () => {
    const candidates = [
      makeCandidate({
        alpha_id: 'alpha-truncated-id-12345',
        expression: 'ts_rank(close, 5)',
      }),
    ];
    render(
      <CandidateTableDesktop
        {...baseDesktopProps({
          candidates,
          allCurrentPageIds: ['alpha-truncated-id-12345'],
        })}
      />
    );
    expect(screen.getByText('alpha-truncated-')).toBeDefined();
    expect(screen.getByText('ts_rank(close, 5)')).toBeDefined();
  });

  it('applies badge-positive / badge-negative / badge-warning by lifecycle status', () => {
    const candidates = [
      makeCandidate({ alpha_id: 'a-sub', lifecycle_status: 'submitted' }),
      makeCandidate({ alpha_id: 'a-fail', lifecycle_status: 'simulation_failed' }),
      makeCandidate({ alpha_id: 'a-running', lifecycle_status: 'simulating' }),
    ];
    const { container } = render(
      <CandidateTableDesktop
        {...baseDesktopProps({
          candidates,
          allCurrentPageIds: candidates.map((c) => c.alpha_id),
        })}
      />
    );
    const positive = container.querySelector('.badge.badge-positive');
    const negative = container.querySelector('.badge.badge-negative');
    const warning = container.querySelector('.badge.badge-warning');
    expect(positive?.textContent).toBe('submitted');
    expect(negative?.textContent).toBe('simulation_failed');
    expect(warning?.textContent).toBe('simulating');
  });

  it('renders score value when scorecard.total_score is present, "--" otherwise', () => {
    const withScore = [
      makeCandidate({
        alpha_id: 'a-score',
        scorecard: { total_score: 7.4 } as Candidate['scorecard'],
      }),
    ];
    const { unmount } = render(
      <CandidateTableDesktop
        {...baseDesktopProps({
          candidates: withScore,
          allCurrentPageIds: ['a-score'],
        })}
      />
    );
    expect(screen.getAllByText('7.4').length).toBeGreaterThan(0);
    unmount();

    render(
      <CandidateTableDesktop
        {...baseDesktopProps({
          candidates: [makeCandidate({ alpha_id: 'a-no-score' })],
          allCurrentPageIds: ['a-no-score'],
        })}
      />
    );
    expect(screen.getAllByText('--').length).toBeGreaterThan(0);
  });
});

// ── Selecting a candidate opens the detail panel ───────────

describe('CandidateTableDesktop — row selection / detail panel trigger', () => {
  it('calls onScore when the 评分 button is clicked (opens detail panel)', () => {
    const onScore = vi.fn();
    const candidate = makeCandidate({ alpha_id: 'a-detail' });
    render(
      <CandidateTableDesktop
        {...baseDesktopProps({
          candidates: [candidate],
          allCurrentPageIds: ['a-detail'],
          showRowActions: true,
          onScore,
        })}
      />
    );
    fireEvent.click(screen.getByLabelText(`评分 a-detail`));
    expect(onScore).toHaveBeenCalledWith(candidate);
  });

  it('calls onToggleSelect with the candidate identity when checkbox is toggled', () => {
    const onToggleSelect = vi.fn();
    render(
      <CandidateTableDesktop
        {...baseDesktopProps({
          candidates: [makeCandidate({ alpha_id: 'a-sel' })],
          allCurrentPageIds: ['a-sel'],
          onToggleSelect,
        })}
      />
    );
    fireEvent.click(screen.getByLabelText(`选择候选 a-sel`));
    expect(onToggleSelect).toHaveBeenCalledWith('a-sel');
  });

  it('disables row action buttons while workflowBusy is true', () => {
    const onScore = vi.fn();
    render(
      <CandidateTableDesktop
        {...baseDesktopProps({
          candidates: [makeCandidate({ alpha_id: 'a-busy' })],
          allCurrentPageIds: ['a-busy'],
          showRowActions: true,
          workflowBusy: true,
          onScore,
        })}
      />
    );
    const btn = screen.getByLabelText(`评分 a-busy`);
    expect(btn.closest('button')?.disabled).toBe(true);
    fireEvent.click(btn);
    expect(onScore).not.toHaveBeenCalled();
  });
});

// ── Empty state ────────────────────────────────────────────

describe('CandidateTableDesktop — empty state', () => {
  it('renders "暂无候选记录" empty state when no candidates and no filter', () => {
    render(
      <CandidateTableDesktop
        {...baseDesktopProps({ candidates: [], showProductionControls: false })}
      />
    );
    expect(screen.getByText('暂无候选记录')).toBeDefined();
    expect(screen.getByText(/请先运行非提交验证产生候选/)).toBeDefined();
  });

  it('renders "没有匹配的候选" empty state + "清除筛选" button when filter is set', () => {
    const onClearFilter = vi.fn();
    render(
      <CandidateTableDesktop
        {...baseDesktopProps({
          candidates: [],
          filter: 'momentum',
          onClearFilter,
        })}
      />
    );
    expect(screen.getByText('没有匹配的候选')).toBeDefined();
    fireEvent.click(screen.getByText('清除筛选'));
    expect(onClearFilter).toHaveBeenCalledTimes(1);
  });

  it('renders "启动自动推进" CTA in empty state when production controls are on', () => {
    const onGenerate = vi.fn();
    render(
      <CandidateTableDesktop
        {...baseDesktopProps({
          candidates: [],
          showProductionControls: true,
          onGenerateCandidates: onGenerate,
        })}
      />
    );
    fireEvent.click(screen.getByText('启动自动推进'));
    expect(onGenerate).toHaveBeenCalledTimes(1);
  });
});

// ── FilterToolbar — filter input behavior ──────────────────

describe('FilterToolbar — filter input behavior', () => {
  const baseFilterProps = (overrides: Record<string, unknown> = {}) => ({
    filter: '',
    apiLoading: false,
    onFilterChange: vi.fn(),
    onRetryLoad: vi.fn(),
    sortedCandidates: [] as Candidate[],
    ...overrides,
  });

  it('calls onFilterChange on input; refresh button toggles with apiLoading', () => {
    const onFilterChange = vi.fn();
    const onRetryLoad = vi.fn();
    const { rerender } = render(
      <FilterToolbar
        {...baseFilterProps({ onFilterChange, apiLoading: true, onRetryLoad })}
      />
    );
    fireEvent.change(screen.getByLabelText('过滤候选'), {
      target: { value: 'momentum' },
    });
    expect(onFilterChange).toHaveBeenCalledWith('momentum');
    expect(screen.getByText('刷新中...').closest('button')?.disabled).toBe(true);

    rerender(
      <FilterToolbar
        {...baseFilterProps({ onFilterChange, apiLoading: false, onRetryLoad })}
      />
    );
    fireEvent.click(screen.getByText('刷新'));
    expect(onRetryLoad).toHaveBeenCalledTimes(1);
  });

  it('opens export dropdown with CSV/JSON options; disabled when no candidates', () => {
    const { rerender } = render(
      <FilterToolbar
        {...baseFilterProps({
          sortedCandidates: [makeCandidate({ alpha_id: 'a-exp' })],
        })}
      />
    );
    fireEvent.click(screen.getByText('导出 ▾'));
    expect(screen.getByLabelText('导出为 CSV 格式')).toBeDefined();
    expect(screen.getByLabelText('导出为 JSON 格式')).toBeDefined();

    rerender(<FilterToolbar {...baseFilterProps({ sortedCandidates: [] })} />);
    expect(screen.getByText('导出 ▾').closest('button')?.disabled).toBe(true);
  });
});

// ── state filter utility (viewMode-based) ──────────────────

describe('candidateMatchesQueueView — state filter logic', () => {
  const results = new Map<string, CandidateCheckResult>();
  const match = (status: string, view: Parameters<typeof candidateMatchesQueueView>[1]) =>
    candidateMatchesQueueView(
      makeCandidate({ lifecycle_status: status }),
      view,
      results
    );

  it('matches candidates view universally and routes statuses to dedicated views', () => {
    expect(match('simulating', 'candidates')).toBe(true);
    expect(match('pending_backtest', 'pending_backtest')).toBe(true);
    expect(match('running', 'running_backtest')).toBe(true);
    expect(match('failed_backtest', 'backtest_rework')).toBe(true);
    expect(
      candidateMatchesQueueView(
        makeCandidate({
          lifecycle_status: 'submission_ready',
          quality_diagnosis: { submission_ready: true },
        }),
        'passed',
        results
      )
    ).toBe(true);
    expect(
      candidateMatchesQueueView(
        makeCandidate({
          lifecycle_status: 'submitted',
          submission: { stage: 'submitted' },
        }),
        'submitted',
        results
      )
    ).toBe(true);
  });
});

// ── Loading state ──────────────────────────────────────────

describe('CandidateTableLoading — skeleton state', () => {
  const props = {
    title: '候选管理',
    viewMode: 'candidates' as const,
    targetPoolSize: 10,
    showProductionControls: true,
    onTargetPoolSizeChange: vi.fn(),
    onRetryLoad: vi.fn(),
  };

  it('renders 8 desktop skeleton rows and 加载中... header', () => {
    const { container } = render(<CandidateTableLoading {...props} />);
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThanOrEqual(8);
    expect(screen.getByText('加载中...')).toBeDefined();
  });

  it('renders the title in the toolbar header', () => {
    render(<CandidateTableLoading {...props} title="等待回测候选" />);
    expect(screen.getByText('等待回测候选')).toBeDefined();
  });
});

// ── statusBadgeClass — lifecycle status → badge tone ───────

describe('statusBadgeClass', () => {
  it('maps lifecycle statuses to badge tones', () => {
    expect(statusBadgeClass('submitted')).toBe('badge-positive');
    expect(statusBadgeClass('simulation_failed')).toBe('badge-negative');
    expect(statusBadgeClass('simulating')).toBe('badge-warning');
    expect(statusBadgeClass('draft')).toBe('badge-neutral');
  });
});
