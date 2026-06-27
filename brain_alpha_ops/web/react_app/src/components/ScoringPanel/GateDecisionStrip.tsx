/** GateDecisionStrip — structured interpreter for the gate decision (D4.1).
 *
 * Renders the structured GateDecisionPayload from /api/scoring/gate_decision:
 *   - Reason badge (color-coded by action)
 *   - Reason text
 *   - Next-action CTA (the next_action_hint)
 *   - Triggered rules list (each with a tooltip explaining source/reason)
 *   - Compact evidence summary (release status, anti-overfit recommendation)
 *
 * Additive-only: the parent panel mounts this strip alongside the existing
 * GateResults / ImprovementHints components; it does not replace them.
 */
import Tooltip from '../Tooltip';
import type {
  GateDecisionActionLiteral,
  GateDecisionPayload,
  GateEvidence,
  TriggeredRule,
} from '@/types';
import { safeScoringText } from './utils';

interface Props {
  decision: GateDecisionPayload | null;
  loading?: boolean;
}

const ACTION_LABELS: Record<GateDecisionActionLiteral, string> = {
  enter_official_simulation_queue: '进入官方模拟队列',
  continue_optimization: '继续优化',
  discard_archive: '丢弃归档',
  enter_human_confirmation: '需要人工确认',
};

interface ActionTone {
  bg: string;
  text: string;
  border: string;
}

const ACTION_TONES: Record<GateDecisionActionLiteral, ActionTone> = {
  enter_official_simulation_queue: {
    bg: 'var(--color-status-complete-bg)',
    text: 'var(--color-status-complete-text)',
    border: 'var(--color-status-complete-border)',
  },
  continue_optimization: {
    bg: 'var(--color-warning-bg)',
    text: 'var(--color-warning-border)',
    border: 'var(--color-warning-border-subtle)',
  },
  discard_archive: {
    bg: 'var(--color-status-blocked-bg)',
    text: 'var(--color-status-blocked-text)',
    border: 'var(--color-status-blocked-border)',
  },
  enter_human_confirmation: {
    bg: 'var(--color-info-bg)',
    text: 'var(--color-info-text)',
    border: 'var(--color-info-border)',
  },
};

export default function GateDecisionStrip({ decision, loading }: Props) {
  if (loading && !decision) {
    return (
      <div className="panel mb-4">
        <div className="panel-header">
          <span>门禁判定</span>
        </div>
        <div className="panel-body-padded">
          <p className="text-xs text-text-tertiary">正在加载门禁判定数据…</p>
        </div>
      </div>
    );
  }
  if (!decision || !decision.ok) {
    return null;
  }
  const action = decision.action;
  const tone = ACTION_TONES[action] || ACTION_TONES.enter_human_confirmation;
  const label = ACTION_LABELS[action] || safeScoringText(action, '门禁判定待确认');
  const rules = Array.isArray(decision.triggered_rules) ? decision.triggered_rules : [];
  const evidence = decision.gate_evidence || {};
  return (
    <div className="panel mb-4">
      <div className="panel-header">
        <span>门禁判定</span>
        <span className="text-2xs text-text-tertiary">
          {safeScoringText(decision.schema_version, 'gate_decision.v1')}
        </span>
      </div>
      <div className="panel-body-padded">
        <div className="flex items-start gap-3" style={{ flexWrap: 'wrap' }}>
          <ReasonBadge label={label} tone={tone} />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-text-primary break-words">
              {safeScoringText(decision.reason, '门禁原因待确认')}
            </p>
            {decision.next_action_hint && (
              <NextActionCTA hint={decision.next_action_hint} />
            )}
          </div>
        </div>
        <EvidenceSummary evidence={evidence} targetState={decision.target_state} />
        {rules.length > 0 && <TriggeredRulesList rules={rules} />}
      </div>
    </div>
  );
}

function ReasonBadge({ label, tone }: { label: string; tone: ActionTone }) {
  return (
    <span
      className="badge text-xs"
      style={{
        background: tone.bg,
        color: tone.text,
        border: `0.5px solid ${tone.border}`,
        padding: '4px 10px',
        borderRadius: 4,
        fontWeight: 600,
        flexShrink: 0,
      }}
    >
      {label}
    </span>
  );
}

function NextActionCTA({ hint }: { hint: string }) {
  const text = safeScoringText(hint, '下一步动作待确认');
  return (
    <div
      className="mt-2 flex items-start gap-2"
      style={{
        padding: '6px 10px',
        borderRadius: 4,
        border: '0.5px solid var(--color-border-subtle)',
        background: 'var(--color-surface-2)',
        fontSize: 12,
      }}
    >
      <span className="text-text-tertiary" style={{ flexShrink: 0 }}>
        下一步 →
      </span>
      <span className="text-text-secondary break-words">{text}</span>
    </div>
  );
}

function EvidenceSummary({
  evidence,
  targetState,
}: {
  evidence: GateEvidence;
  targetState: string;
}) {
  const items: Array<{ label: string; value: string }> = [];
  if (targetState) items.push({ label: '目标状态', value: targetState });
  const releaseStatus = evidence.release_status;
  if (releaseStatus) items.push({ label: '发布门禁', value: String(releaseStatus) });
  const aoRec = evidence.anti_overfit_recommendation;
  if (aoRec) items.push({ label: '反过拟合', value: String(aoRec) });
  const hasMetrics = evidence.has_official_metrics;
  if (typeof hasMetrics === 'boolean') {
    items.push({ label: '官方指标', value: hasMetrics ? '已校验' : '缺失' });
  }
  const hardFailed = evidence.hard_gate_failed;
  if (Array.isArray(hardFailed) && hardFailed.length) {
    items.push({ label: '硬门禁失败', value: hardFailed.join(', ') });
  }
  if (!items.length) return null;
  return (
    <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
      {items.map((item, i) => (
        <div
          key={`${item.label}-${i}`}
          className="bg-surface-2"
          style={{ padding: '6px 8px', borderRadius: 4 }}
        >
          <span className="text-2xs text-text-tertiary block">{item.label}</span>
          <span className="text-sm text-text-primary break-words">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function TriggeredRulesList({ rules }: { rules: TriggeredRule[] }) {
  return (
    <div className="mt-3">
      <p className="text-xs font-medium text-text-secondary mb-2">触发规则</p>
      <ul className="space-y-1">
        {rules.map((rule, i) => {
          const source = safeScoringText(rule.source, 'rule');
          const name = safeScoringText(rule.rule, 'rule_name');
          const reason = safeScoringText(rule.reason, '');
          const tooltip = [source, name, reason].filter(Boolean).join(' · ');
          return (
            <li
              key={`${source}-${name}-${i}`}
              className="text-xs text-text-secondary"
              style={{ padding: '2px 0' }}
            >
              <Tooltip content={tooltip} placement="top">
                <span
                  className="cursor-help"
                  style={{ borderBottom: '1px dotted var(--color-border-subtle)' }}
                >
                  {name}
                </span>
              </Tooltip>
              {reason && <span className="text-text-tertiary"> — {reason}</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
