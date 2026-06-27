/**
 * Workstream F2.3 — Scoring attribution display behavior tests.
 *
 * Behavior under test:
 *  - GateDecisionStrip renders the reason badge with action-specific tone
 *    (green/orange/red/blue for the 4 action literals).
 *  - GateDecisionStrip renders the next-action CTA from next_action_hint.
 *  - GateDecisionStrip renders triggered rules + evidence summary.
 *  - GateDecisionStrip renders null when decision is null/!ok, and a loading
 *    state when loading=true && !decision.
 *  - AttributionTree renders nested attribution nodes recursively.
 *  - AttributionTooltip wraps the dimension label and reveals tooltip content
 *    on focus (a11y).
 *
 * Mounts ScoringPanel subcomponents directly with mocked props to avoid
 * pulling useApi / useSSE / useGlobalData providers.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import GateDecisionStrip from '@/components/ScoringPanel/GateDecisionStrip';
import AttributionTree from '@/components/ScoringPanel/AttributionTree';
import AttributionTooltip from '@/components/ScoringPanel/AttributionTooltip';
import type {
  AttributionNode,
  GateDecisionPayload,
  GateDecisionActionLiteral,
  TriggeredRule,
} from '@/types';

const makeDecision = (
  action: GateDecisionActionLiteral,
  overrides: Partial<GateDecisionPayload> = {}
): GateDecisionPayload => ({
  ok: true,
  action,
  reason: `${action}-reason`,
  target_state: `${action}-target`,
  next_action_hint: `${action}-cta`,
  ...overrides,
});

// ── GateDecisionStrip — null / loading states ──────────────

describe('GateDecisionStrip — null / loading states', () => {
  it('renders null when decision is null or decision.ok is false', () => {
    const { container: c1 } = render(<GateDecisionStrip decision={null} />);
    expect(c1.firstChild).toBeNull();
    const { container: c2 } = render(
      <GateDecisionStrip
        decision={{
          ok: false,
          action: 'continue_optimization',
          reason: 'some error',
          target_state: 'needs_optimization',
          error: 'gate error',
        }}
      />
    );
    expect(c2.firstChild).toBeNull();
  });

  it('renders loading placeholder when loading=true and no decision', () => {
    render(<GateDecisionStrip decision={null} loading={true} />);
    expect(screen.getByText('门禁判定')).toBeDefined();
    expect(screen.getByText('正在加载门禁判定数据…')).toBeDefined();
  });

  it('renders the decision panel once decision is present (even if still loading)', () => {
    render(
      <GateDecisionStrip
        decision={{
          ok: true,
          action: 'continue_optimization',
          reason: '需要继续优化',
          target_state: 'needs_optimization',
        }}
        loading={true}
      />
    );
    expect(screen.getByText('继续优化')).toBeDefined();
    expect(screen.getByText('需要继续优化')).toBeDefined();
  });
});

// ── GateDecisionStrip — action tones & CTA ─────────────────

describe('GateDecisionStrip — action tones and CTA', () => {
  const cases: Array<{ action: GateDecisionActionLiteral; label: string; cssVar: string }> = [
    {
      action: 'enter_official_simulation_queue',
      label: '进入官方模拟队列',
      cssVar: '--color-status-complete-bg',
    },
    { action: 'continue_optimization', label: '继续优化', cssVar: '--color-warning-bg' },
    { action: 'discard_archive', label: '丢弃归档', cssVar: '--color-status-blocked-bg' },
    { action: 'enter_human_confirmation', label: '需要人工确认', cssVar: '--color-info-bg' },
  ];

  it.each(cases)(
    'renders $label badge with $cssVar tone for action=$action',
    ({ action, label, cssVar }) => {
      const { container } = render(<GateDecisionStrip decision={makeDecision(action)} />);
      const badge = container.querySelector('.badge');
      expect(badge).not.toBeNull();
      expect(badge?.textContent).toBe(label);
      expect(badge?.getAttribute('style')).toContain(cssVar);
    }
  );

  it('renders the next-action CTA from next_action_hint; omits CTA when missing', () => {
    const { rerender } = render(
      <GateDecisionStrip
        decision={makeDecision('continue_optimization', {
          next_action_hint: '调整 decay 与 neutralization 后重新评分',
        })}
      />
    );
    expect(screen.getByText(/调整 decay 与 neutralization 后重新评分/)).toBeDefined();
    expect(screen.getByText('下一步 →')).toBeDefined();

    rerender(
      <GateDecisionStrip
        decision={{
          ok: true,
          action: 'continue_optimization',
          reason: 'no hint',
          target_state: 'needs_optimization',
        }}
      />
    );
    expect(screen.queryByText('下一步 →')).toBeNull();
  });

  it('renders the reason text; falls back to "门禁原因待确认" when reason is empty', () => {
    const { rerender } = render(
      <GateDecisionStrip
        decision={makeDecision('discard_archive', { reason: '高度相似表达式已被收录' })}
      />
    );
    expect(screen.getByText('高度相似表达式已被收录')).toBeDefined();

    rerender(
      <GateDecisionStrip
        decision={{
          ok: true,
          action: 'discard_archive',
          reason: '',
          target_state: 'archived',
        }}
      />
    );
    expect(screen.getByText('门禁原因待确认')).toBeDefined();
  });
});

// ── GateDecisionStrip — triggered rules & evidence ─────────

describe('GateDecisionStrip — triggered rules and evidence summary', () => {
  it('renders the triggered rules list with tooltips; omits section when empty', () => {
    const rules: TriggeredRule[] = [
      { source: 'release_score_gate', rule: 'sharpe_min', reason: 'sharpe < 1.25' },
      { source: 'anti_overfit', rule: 'ic_stability', reason: 'IC 不稳定' },
    ];
    const { rerender } = render(
      <GateDecisionStrip
        decision={makeDecision('continue_optimization', { triggered_rules: rules })}
      />
    );
    expect(screen.getByText('触发规则')).toBeDefined();
    expect(screen.getByText('sharpe_min')).toBeDefined();
    expect(screen.getByText('ic_stability')).toBeDefined();
    expect(screen.getByText(/sharpe < 1.25/)).toBeDefined();
    expect(screen.getByText(/IC 不稳定/)).toBeDefined();

    rerender(
      <GateDecisionStrip
        decision={makeDecision('continue_optimization', { triggered_rules: [] })}
      />
    );
    expect(screen.queryByText('触发规则')).toBeNull();
  });

  it('renders the evidence summary with target_state, release_status, anti_overfit_recommendation', () => {
    render(
      <GateDecisionStrip
        decision={makeDecision('discard_archive', {
          target_state: 'archived',
          gate_evidence: {
            release_status: 'blocked',
            anti_overfit_recommendation: 'discard',
            has_official_metrics: true,
            hard_gate_failed: ['sharpe_min', 'fitness_min'],
          },
        })}
      />
    );
    expect(screen.getByText('目标状态')).toBeDefined();
    expect(screen.getByText('archived')).toBeDefined();
    expect(screen.getByText('发布门禁')).toBeDefined();
    expect(screen.getByText('blocked')).toBeDefined();
    expect(screen.getByText('反过拟合')).toBeDefined();
    expect(screen.getByText('discard')).toBeDefined();
    expect(screen.getByText('官方指标')).toBeDefined();
    expect(screen.getByText('已校验')).toBeDefined();
    expect(screen.getByText('硬门禁失败')).toBeDefined();
    expect(screen.getByText('sharpe_min, fitness_min')).toBeDefined();
  });

  it('omits evidence summary when no evidence fields are present; shows "缺失" when has_official_metrics=false', () => {
    const { rerender } = render(
      <GateDecisionStrip
        decision={{ ok: true, action: 'continue_optimization', reason: 'reason', target_state: '' }}
      />
    );
    expect(screen.queryByText('目标状态')).toBeNull();
    expect(screen.queryByText('发布门禁')).toBeNull();
    expect(screen.queryByText('反过拟合')).toBeNull();

    rerender(
      <GateDecisionStrip
        decision={makeDecision('continue_optimization', {
          gate_evidence: { has_official_metrics: false },
        })}
      />
    );
    expect(screen.getByText('缺失')).toBeDefined();
  });

  it('renders schema_version label with fallback "gate_decision.v1" when missing', () => {
    const { rerender } = render(
      <GateDecisionStrip
        decision={makeDecision('continue_optimization', { schema_version: 'gate_decision.v2' })}
      />
    );
    expect(screen.getByText('gate_decision.v2')).toBeDefined();

    rerender(<GateDecisionStrip decision={makeDecision('continue_optimization')} />);
    expect(screen.getByText('gate_decision.v1')).toBeDefined();
  });
});

// ── AttributionTree — nested rendering ─────────────────────

describe('AttributionTree — nested rendering', () => {
  it('renders null when attribution is null', () => {
    const { container } = render(<AttributionTree attribution={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the root node name and score x weight', () => {
    const tree: AttributionNode = { name: '总评分', score: 7.5, weight: 1.0, contribution: 7.5 };
    render(<AttributionTree attribution={tree} />);
    expect(screen.getByText('总评分')).toBeDefined();
    // fmtNum(7.5, 1) = "7.5" ; fmtNum(1.0, 2) = "1.00"
    expect(screen.getByText('7.5 x 1.00')).toBeDefined();
  });

  it('renders child nodes recursively with indentation', () => {
    const tree: AttributionNode = {
      name: '总评分',
      score: 7.5,
      weight: 1.0,
      children: [
        { name: '先验层', score: 8.0, weight: 0.4, contribution: 3.2, explanation: '历史先验' },
        { name: '实证层', score: 7.0, weight: 0.4, contribution: 2.8 },
      ],
    };
    render(<AttributionTree attribution={tree} />);
    expect(screen.getByText('总评分')).toBeDefined();
    expect(screen.getByText('先验层')).toBeDefined();
    expect(screen.getByText('实证层')).toBeDefined();
    expect(screen.getByText('8.0 x 0.40')).toBeDefined();
    expect(screen.getByText('7.0 x 0.40')).toBeDefined();
    expect(screen.getByText('历史先验')).toBeDefined();
  });

  it('renders deeply nested grandchildren', () => {
    const tree: AttributionNode = {
      name: 'root',
      score: 1,
      weight: 1,
      children: [
        {
          name: 'child',
          score: 2,
          weight: 0.5,
          children: [{ name: 'grandchild', score: 3, weight: 0.25 }],
        },
      ],
    };
    render(<AttributionTree attribution={tree} />);
    expect(screen.getByText('root')).toBeDefined();
    expect(screen.getByText('child')).toBeDefined();
    expect(screen.getByText('grandchild')).toBeDefined();
  });

  it('renders explanation with fallback when missing', () => {
    const tree: AttributionNode = { name: 'node', score: 1, weight: 1, explanation: '' };
    // empty explanation is not rendered (only truthy values are)
    const { container } = render(<AttributionTree attribution={tree} />);
    expect(container.querySelectorAll('p.text-2xs').length).toBe(0);
  });
});

// ── AttributionTooltip — label & tooltip behavior ─────────

describe('AttributionTooltip — label and tooltip behavior', () => {
  it('renders the dimension name as the visible label; uses fallback when name is empty', () => {
    const { rerender } = render(
      <AttributionTooltip name="Sharpe 稳定性" score={1.8} weight={0.3} contribution={0.54} />
    );
    expect(screen.getByText('Sharpe 稳定性')).toBeDefined();

    rerender(<AttributionTooltip name="" fallback="归因项待确认" />);
    expect(screen.getByText('归因项待确认')).toBeDefined();
  });

  it('exposes tooltip content via role=tooltip after focus (a11y)', () => {
    vi.useFakeTimers();
    try {
      render(
        <AttributionTooltip
          name="Sharpe"
          score={1.8}
          weight={0.3}
          contribution={0.54}
          explanation="近 60 日 IC 稳定性"
        />
      );
      expect(screen.queryByRole('tooltip')).toBeNull();

      const label = screen.getByText('Sharpe');
      const wrapper = label.parentElement;
      act(() => {
        wrapper.focus();
      });
      // Advance past the 300ms default delay + the 10ms mount delay
      act(() => {
        vi.advanceTimersByTime(350);
      });

      const tooltip = screen.getByRole('tooltip');
      expect(tooltip.textContent).toContain('分数: 1.8');
      expect(tooltip.textContent).toContain('权重: 0.30');
      expect(tooltip.textContent).toContain('贡献: 0.54');
      expect(tooltip.textContent).toContain('近 60 日 IC 稳定性');
    } finally {
      vi.useRealTimers();
    }
  });

  it('hides the tooltip on blur; uses label as content when no metrics provided', () => {
    vi.useFakeTimers();
    try {
      const { rerender } = render(<AttributionTooltip name="Sharpe" score={1.8} weight={0.3} />);
      const label = screen.getByText('Sharpe');
      const wrapper = label.parentElement;
      act(() => {
        wrapper.focus();
      });
      act(() => {
        vi.advanceTimersByTime(350);
      });
      expect(screen.getByRole('tooltip')).toBeDefined();

      act(() => {
        wrapper.blur();
      });
      act(() => {
        vi.advanceTimersByTime(200);
      });
      expect(screen.queryByRole('tooltip')).toBeNull();

      // Re-render with no metrics — tooltip content falls back to label.
      rerender(<AttributionTooltip name="裸维度" />);
      const label2 = screen.getByText('裸维度');
      const wrapper2 = label2.parentElement;
      act(() => {
        wrapper2.focus();
      });
      act(() => {
        vi.advanceTimersByTime(350);
      });
      expect(screen.getByRole('tooltip').textContent).toContain('裸维度');
    } finally {
      vi.useRealTimers();
    }
  });
});
