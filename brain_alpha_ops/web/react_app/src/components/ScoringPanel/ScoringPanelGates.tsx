/** Scoring visualization — gate decision strip + gate results + score history.
 *
 *  Merges the previously fragmented `GateDecisionStrip.tsx`, `GateResults.tsx`,
 *  and `ScoreHistory.tsx` into a single file. All three are exported as named
 *  exports so the main ScoringPanel and the barrel index.ts can consume them. */
import Tooltip from '../Tooltip';
import type { ScoreHistoryPoint } from '@/components/ScoreBreakdown/ScoreHistory';
import type {
  GateDecisionActionLiteral,
  GateDecisionPayload,
  GateEvidence,
  OfficialGateCheckItem,
  OfficialGateResult,
  TriggeredRule,
} from '@/types';
import { safeScoringText } from './ScoringPanelHeader';

// ──────────────────────────────────────────────────────────────────────────
// GateDecisionStrip — structured interpreter for the gate decision (D4.1)
// ──────────────────────────────────────────────────────────────────────────

interface GateDecisionStripProps {
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

export function GateDecisionStrip({ decision, loading }: GateDecisionStripProps) {
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
            {decision.next_action_hint && <NextActionCTA hint={decision.next_action_hint} />}
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

// ──────────────────────────────────────────────────────────────────────────
// GateResults — official gate check display
// ──────────────────────────────────────────────────────────────────────────

interface GateResultsProps {
  hardGates: OfficialGateResult[];
  softGates: OfficialGateResult[];
}

export function GateResults({ hardGates, softGates }: GateResultsProps) {
  return (
    <div className="panel mb-4">
      <div className="panel-header">
        <span>官方门禁检查</span>
      </div>
      <div className="panel-body-padded">
        <GateGroup title="硬门禁" gates={hardGates} />
        <div style={{ marginTop: 16 }}>
          <GateGroup title="软门禁" gates={softGates} />
        </div>
      </div>
    </div>
  );
}

function GateGroup({ title, gates }: { title: string; gates: OfficialGateResult[] }) {
  const safeGates = Array.isArray(gates) ? gates : [];
  if (!safeGates.length) return <p className="text-xs text-text-tertiary">{title}: 暂无数据</p>;
  return (
    <div>
      <p className="text-xs font-medium text-text-secondary mb-2">{title}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {safeGates.flatMap((gate) => {
          const checkItems = Array.isArray(gate.check_items) ? gate.check_items : [];
          const checks: OfficialGateCheckItem[] = checkItems.length
            ? checkItems
            : [{ name: gate.gate_name, passed: gate.passed }];
          return checks.map((check, i) => (
            <div
              key={`${safeScoringText(gate.gate_name, 'gate')}-${safeScoringText(check.name, 'check')}-${i}`}
              className={
                check.passed
                  ? 'bg-positive-subtle border-positive-subtle'
                  : 'bg-negative-subtle border-negative-subtle'
              }
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                padding: '8px 10px',
                borderRadius: 4,
                fontSize: 12,
                borderWidth: '0.5px',
                borderStyle: 'solid',
              }}
            >
              <span className={check.passed ? 'text-positive' : 'text-negative'}>
                {check.passed ? '\u2713' : '\u2715'}
              </span>
              <div>
                <span className="font-medium">{safeScoringText(check.name, '检查项待确认')}</span>
                <p className="text-text-tertiary text-2xs">
                  {formatGateDetail(check.actual, check.direction, check.target, check.meaning)}
                </p>
                <p className="text-text-tertiary text-2xs">
                  {safeScoringText(gate.gate_name, '门禁待确认')}
                </p>
              </div>
            </div>
          ));
        })}
      </div>
    </div>
  );
}

function formatGateDetail(actual: unknown, direction: unknown, target: unknown, fallback: unknown) {
  const parts = [actual, direction, target]
    .map((value) => safeScoringText(value, ''))
    .filter((value) => value);
  if (parts.length) return parts.join(' ');
  return safeScoringText(fallback, '--');
}

// ──────────────────────────────────────────────────────────────────────────
// ScoreHistory — score history timeline with sparkline
// ──────────────────────────────────────────────────────────────────────────

interface ScoreHistoryProps {
  scoreHistory: ScoreHistoryPoint[];
  expanded: boolean;
  onToggleExpanded: () => void;
}

function formatLabel(ts: string): string {
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts.slice(0, 5);
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  } catch {
    return ts.slice(0, 5);
  }
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts.slice(0, 10);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch {
    return ts.slice(0, 10);
  }
}

export function ScoreHistory({ scoreHistory, expanded, onToggleExpanded }: ScoreHistoryProps) {
  return (
    <div className="panel mb-4">
      <button
        type="button"
        className="panel-header"
        style={{
          width: '100%',
          textAlign: 'left',
          cursor: 'pointer',
          border: 'none',
          background: 'none',
          font: 'inherit',
        }}
        onClick={onToggleExpanded}
        aria-expanded={expanded}
        aria-controls="score-history-content"
        aria-label={`评分历史，共 ${scoreHistory.length} 条记录，点击${expanded ? '收起' : '展开'}`}
      >
        <span>评分历史 ({scoreHistory.length})</span>
        <span className="text-text-tertiary" style={{ fontSize: 12 }} aria-hidden="true">
          {expanded ? '▾ 收起' : '▸ 展开'}
        </span>
      </button>
      {expanded && (
        <div
          id="score-history-content"
          className="panel-body-padded"
          role="region"
          aria-label="评分历史详情"
        >
          <ScoreHistoryBody scoreHistory={scoreHistory} />
        </div>
      )}
    </div>
  );
}

function ScoreHistoryBody({ scoreHistory }: { scoreHistory: ScoreHistoryPoint[] }) {
  return (
    <div
      className="scorebreakdown-panel"
      style={{ background: 'none', border: 'none', padding: 0 }}
    >
      <div className="scorebreakdown-history" style={{ padding: 0 }}>
        <div className="scorebreakdown-sparkline-container" style={{ marginTop: 0 }}>
          <ScoreHistorySparkline scoreHistory={scoreHistory} />
          <ScoreHistoryList scoreHistory={scoreHistory} />
        </div>
      </div>
    </div>
  );
}

function ScoreHistorySparkline({ scoreHistory }: { scoreHistory: ScoreHistoryPoint[] }) {
  const points = scoreHistory.slice(-10);
  const scores = points.map((p) => p.totalScore);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);
  const range = maxScore - minScore || 1;
  return (
    <div
      className="scorebreakdown-sparkline"
      aria-label={`评分历史趋势，共 ${scoreHistory.length} 个数据点`}
      style={{
        height: 56,
        borderBottom: '0.5px solid var(--color-border-default)',
      }}
    >
      {points.map((point, i) => {
        const heightPct = ((point.totalScore - minScore) / range) * 100;
        return (
          <div
            key={`${point.timestamp}-${i}`}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              height: '100%',
            }}
            title={`${formatLabel(point.timestamp)}: ${point.totalScore.toFixed(1)}`}
          >
            <div
              style={{
                width: '100%',
                maxWidth: 24,
                height: `${Math.max(4, heightPct)}%`,
                minHeight: 2,
                background: 'var(--color-sparkline-bar)',
                borderRadius: '1px 1px 0 0',
              }}
            />
            <span
              style={{
                fontSize: '0.5rem',
                color: 'var(--color-text-muted)',
                marginTop: 2,
                textAlign: 'center',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {formatLabel(point.timestamp)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ScoreHistoryList({ scoreHistory }: { scoreHistory: ScoreHistoryPoint[] }) {
  return (
    <div
      style={{
        marginTop: 8,
        paddingTop: 6,
        borderTop: '0.5px solid var(--color-border-default)',
      }}
    >
      {scoreHistory
        .slice()
        .reverse()
        .slice(0, 10)
        .map((point, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '2px 0',
              fontSize: '0.625rem',
            }}
          >
            <span style={{ color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>
              {formatTimestamp(point.timestamp)}
            </span>
            <span
              style={{
                color: 'var(--color-score-highlight)',
                fontFamily: 'monospace',
              }}
            >
              {point.totalScore.toFixed(1)}
            </span>
          </div>
        ))}
    </div>
  );
}
