import type { AttributionNode, Candidate, ScoringResult } from '@/types';
import { safeScoringText, fmtNum, isLocalPrefilterStatus } from './utils';
import AttributionTree from './AttributionTree';
import Skeleton from '../Skeleton';
import Tooltip from '../Tooltip';

interface Props {
  candidate: Candidate;
  scoring: ScoringResult | null;
  layerScores: { prior: number; empirical: number; checklist: number };
  loading: boolean;
  onRetry: () => void;
  lifecycleStatus: string;
  officialMetrics: Candidate['official_metrics'];
  attribution: AttributionNode | null;
}

/**
 * 获取分数颜色编码（使用设计令牌语义类）
 * 优秀（≥0.8）：positive
 * 良好（0.6-0.8）：info
 * 一般（0.4-0.6）：warning
 * 差（<0.4）：negative
 */
function getScoreColorClass(score: number | undefined): string {
  if (score == null) return 'text-text-tertiary';
  if (score >= 0.8) return 'text-positive';
  if (score >= 0.6) return 'text-info';
  if (score >= 0.4) return 'text-warning';
  return 'text-negative';
}

export default function ScoringHeader({
  candidate,
  scoring,
  layerScores,
  loading,
  onRetry,
  lifecycleStatus,
  officialMetrics,
  attribution,
}: Props) {
  const m = officialMetrics;
  const totalScore = scoring?.total_score ?? candidate.scorecard?.total_score;
  const normalizedScore = totalScore != null ? totalScore / 100 : undefined;

  return (
    <>
      {/* Expression overview + Score Hero */}
      <div className="panel mb-4">
        <div className="panel-header">
          <span>Alpha 表达式</span>
          <button onClick={onRetry} className="btn btn-ghost btn-sm" disabled={loading}>
            {loading ? '评分中...' : '刷新评分'}
          </button>
        </div>
        <div className="panel-body-padded">
          {loading && !scoring ? (
            <div className="space-y-3">
              <Skeleton variant="text" className="h-16 w-full" />
              <Skeleton variant="text" className="h-4 w-3/4" />
            </div>
          ) : (
            <code
              className="block font-mono text-xs text-text-secondary p-3 rounded-md bg-surface-2 break-all"
              style={{ lineHeight: 1.6 }}
            >
              {candidate.expression}
            </code>
          )}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '8px 16px',
              marginTop: 12,
              fontSize: 12,
            }}
          >
            <span className="text-text-tertiary">
              家族:{' '}
              <span className="text-text-secondary">
                {safeScoringText(candidate.family, '家族待确认')}
              </span>
            </span>
            <span className="text-text-tertiary">
              状态:{' '}
              <span
                className={`badge ${scoring?.passed_gate || candidate.gate?.passed ? 'badge-positive' : 'badge-negative'}`}
              >
                {lifecycleStatus}
              </span>
            </span>
            <span className="text-text-tertiary">
              ID: <span className="font-mono text-text-secondary">{candidate.alpha_id}</span>
            </span>
          </div>
          {isLocalPrefilterStatus(candidate.lifecycle_status) && (
            <div
              style={{
                marginTop: 12,
                padding: '10px 14px',
                borderRadius: 6,
                border: '1px solid var(--color-warning-border-subtle)',
                backgroundColor: 'var(--color-warning-bg)',
                fontSize: 12,
                lineHeight: 1.6,
              }}
              role="note"
              aria-label="本地预筛边界警告"
            >
              <p style={{ fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: 4 }}>
                本地预筛边界提示
              </p>
              <p style={{ color: 'var(--color-text-secondary)' }}>
                本地预筛使用合成数据（synthetic data）进行快速评估，而非真实历史回测数据。
                本地预筛结果仅作为初筛参考，不代表该 Alpha 在真实市场中的实际表现。 请以官方 BRAIN
                模拟回测结果为准。
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Score Scoreboard + Official Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* Scoreboard */}
        <div className="panel">
          <div className="panel-header">
            <span>评分卡</span>
          </div>
          <div className="panel-body-padded">
            {loading && !scoring ? (
              <div className="space-y-4">
                <div className="text-center">
                  <Skeleton variant="card" className="w-32 h-16 mx-auto mb-4" />
                </div>
                <Skeleton variant="text" className="h-8 w-full" />
                <Skeleton variant="text" className="h-8 w-full" />
                <Skeleton variant="text" className="h-8 w-full" />
              </div>
            ) : (
              <>
                <div style={{ textAlign: 'center', marginBottom: 16 }}>
                  <span
                    className={`font-mono-value font-bold ${getScoreColorClass(normalizedScore)}`}
                    style={{ fontSize: 48, lineHeight: 1.2 }}
                  >
                    {fmtNum(totalScore, 1)}
                  </span>
                  <span className="text-text-tertiary text-xl">/100</span>
                  {normalizedScore != null && (
                    <div
                      className={`text-sm font-medium ${getScoreColorClass(normalizedScore)} mt-1`}
                    >
                      {normalizedScore >= 0.8
                        ? '优秀'
                        : normalizedScore >= 0.6
                          ? '良好'
                          : normalizedScore >= 0.4
                            ? '一般'
                            : '差'}
                    </div>
                  )}
                </div>
                <ScoreBar label="先验" value={layerScores.prior} max={35} />
                <ScoreBar label="实证" value={layerScores.empirical} max={40} />
                <ScoreBar label="清单" value={layerScores.checklist} max={25} />
                <div className="grid grid-cols-2 gap-2 mt-4 text-xs">
                  <InfoPill
                    label="决策"
                    value={scoring?.decision_band || candidate.decision_band || '--'}
                  />
                  <InfoPill label="模式" value={scoring?.scoring_schema || '--'} />
                  <InfoPill label="门禁" value={scoring?.passed_gate ? '通过' : '失败'} />
                  <InfoPill label="API 偏差" value={fmtNum(scoring?.api_output_deviation, 4)} />
                </div>
              </>
            )}
            {attribution && !loading && (
              <div className="mt-4 pt-3 border-t border-border-subtle">
                <p className="text-xs font-medium text-text-secondary mb-2">归因分析</p>
                <AttributionTree attribution={attribution} />
              </div>
            )}
            {loading && !attribution && (
              <div className="mt-4 pt-3 border-t border-border-subtle">
                <Skeleton variant="text" className="h-4 w-24 mb-2" />
                <Skeleton variant="text" className="h-6 w-full mb-1" />
                <Skeleton variant="text" className="h-6 w-4/5" />
              </div>
            )}
          </div>
        </div>

        {/* Official Metrics */}
        <div className="panel">
          <div className="panel-header">
            <span>官方指标</span>
          </div>
          <div className="panel-body-padded">
            {loading && !officialMetrics ? (
              <div className="space-y-2">
                {[...Array(7)].map((_, i) => (
                  <Skeleton key={i} variant="table-row" className="h-10 w-full" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 text-xs">
                <MetricRow label="夏普比率" value={m?.sharpe} threshold={1.25} />
                <MetricRow label="适应度" value={m?.fitness} threshold={1.0} />
                <MetricRow label="换手率" value={m?.turnover} format="percent" />
                <MetricRow label="收益率" value={m?.returns} format="percent" />
                <MetricRow label="回撤" value={m?.drawdown} format="percent" max={0.25} />
                <MetricRow label="自相关性" value={m?.self_correlation} max={0.7} />
                <MetricRow
                  label="集中度"
                  value={m?.weight_concentration}
                  max={0.1}
                  format="percent"
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function ScoreBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div style={{ marginBottom: 10 }}>
      <div
        style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12 }}
      >
        <span className="text-text-tertiary">{label}</span>
        <span className="tabular text-text-tertiary">
          {value.toFixed(1)}/{max}
        </span>
      </div>
      <div
        className="progress-bar"
        role="progressbar"
        aria-label={`${label} score`}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
      >
        <div className="progress-bar-fill positive" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function InfoPill({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="bg-surface-2" style={{ padding: '8px 10px', borderRadius: 4 }}>
      <span className="text-2xs text-text-tertiary block">{label}</span>
      <span className="text-sm font-mono text-text-primary truncate block">
        {safeScoringText(value, '待确认')}
      </span>
    </div>
  );
}

const METRIC_TOOLTIPS: Record<string, string> = {
  夏普比率: '风险调整后收益指标，衡量每单位风险所获得的超额收益。阈值 ≥ 1.25',
  适应度: '综合评估策略质量的多维度指标，考虑收益、风险、稳定性等因素。阈值 ≥ 1.0',
  换手率: '策略在一定时间内买卖资产的频率。过高的换手率会增加交易成本',
  收益率: '策略在回测期间的总回报率',
  回撤: '策略从峰值到谷底的最大跌幅，衡量下行风险。阈值 ≤ 25%',
  自相关性: '策略收益的自相关程度，过高可能表示过拟合。阈值 ≤ 0.70',
  集中度: '持仓权重的集中程度，衡量分散化水平。阈值 ≤ 10%',
};

function MetricRow({
  label,
  value,
  threshold,
  max,
  format,
}: {
  label: string;
  value?: number | string;
  threshold?: number;
  max?: number;
  format?: 'percent';
}) {
  if (value == null) return null;
  const numericValue = Number(value);
  const isNumeric = Number.isFinite(numericValue);
  const formatted = isNumeric
    ? format === 'percent'
      ? `${(numericValue * 100).toFixed(1)}%`
      : numericValue.toFixed(2)
    : String(value);
  const ok = isNumeric
    ? threshold != null
      ? numericValue >= threshold
      : max != null
        ? numericValue <= max
        : true
    : true;
  const tooltipContent = METRIC_TOOLTIPS[label] || label;
  return (
    <Tooltip content={tooltipContent} placement="top">
      <div
        className="bg-surface-2"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 8px',
          borderRadius: 4,
          cursor: 'help',
        }}
      >
        <span className="text-text-tertiary">{label}</span>
        <span className={`font-mono-value text-sm ${ok ? 'text-positive' : 'text-negative'}`}>
          {formatted}
        </span>
      </div>
    </Tooltip>
  );
}
