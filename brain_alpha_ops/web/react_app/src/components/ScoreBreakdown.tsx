/**
 * ScoreBreakdown — 鼠标悬停时显示三层评分拆解 + 门禁状态。
 *
 * Reads from candidate.scorecard.attribution_tree for the three-layer tree,
 * and from candidate.scorecard.empirical.items for hard-gate pass/fail status.
 *
 * P1-5: Accept optional scoreHistory to render a mini sparkline at the bottom.
 */

import { useState } from "react";
import type { AttributionNode, Scorecard, ScoreLayerItem } from "@/types";

/** A single historical score data point for the mini sparkline. */
export interface ScoreHistoryPoint {
  timestamp: string;
  totalScore: number;
}

interface ScoreBreakdownProps {
  scorecard: Scorecard;
  /** P1-5: Optional score history for mini sparkline display. */
  scoreHistory?: ScoreHistoryPoint[];
}

/** Human-readable Chinese labels for known dimension names. */
const DIM_LABELS: Record<string, string> = {
  total_score: "总分",
  prior_score: "先验评分",
  empirical_score: "实证评分",
  submission_checklist: "提交清单",
  economic_logic: "经济逻辑",
  structure: "结构复杂度",
  field_operator_support: "字段与算子",
  data_compliance: "数据合规",
  horizon_turnover_proxy: "窗口/换手代理",
  risk_control_proxy: "风控代理",
  diversity: "多样性",
  explainability: "可解释性",
  economic_concepts: "经济概念",
  sharpe: "Sharpe",
  fitness: "Fitness",
  turnover_min: "最低换手率",
  turnover_platform: "平台换手上限",
  turnover_quality: "换手质量目标",
  returns: "收益",
  drawdown: "回撤",
  self_correlation: "自相关",
  prod_correlation: "生产相关性",
  weight_concentration: "权重集中度",
  sub_universe_sharpe: "子宇宙Sharpe",
  is_oos_ratio: "IS/OOS比率",
  fitness_crosscheck: "Fitness交叉验证",
  margin_bps: "保证金(bps)",
  official_metrics_present: "官方指标存在",
  official_pass: "官方通过",
  economic_logic_check: "经济逻辑检查",
  data_delay_conservative: "保守延迟设置",
  local_quality: "本地质量预筛",
  self_correlation_proxy: "自相关代理",
};

/** User-friendly layer names. */
const LAYER_NAMES: Record<string, string> = {
  prior_score: "先验评分",
  empirical_score: "实证评分",
  submission_checklist: "提交清单",
};

/** Layer accent colors for visual distinction. */
const LAYER_COLORS: Record<string, string> = {
  prior_score: "var(--color-layer-color-info)",
  empirical_score: "var(--color-layer-color-success)",
  submission_checklist: "var(--color-layer-color-warning)",
};

function labelFor(name: string): string {
  return DIM_LABELS[name] || name.replace(/_/g, " ");
}

function formatScore(value: number): string {
  return value.toFixed(1);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

/** Extract hard gates from the empirical layer items. */
function extractHardGates(
  scorecard: Scorecard,
): { name: string; passed: boolean; explanation: string }[] {
  const items: ScoreLayerItem[] =
    (scorecard.empirical as { items?: ScoreLayerItem[] } | undefined)?.items ??
    [];
  return items
    .filter((item) => item.is_hard_gate)
    .map((item) => {
      const actual = item.actual != null ? String(item.actual) : "—";
      const target = item.target != null ? String(item.target) : "—";
      const explanation =
        item.passed
          ? `通过: ${actual} ${item.direction ?? ""} ${target}`
          : `失败: ${actual} ${item.direction ?? ""} ${target}`;
      return {
        name: item.name ?? "未知",
        passed: Boolean(item.passed),
        explanation,
      };
    });
}

/** Render a single node row with optional children. */
function AttributionRow({
  node,
  depth,
  maxScore,
}: {
  node: AttributionNode;
  depth: number;
  maxScore: number;
}) {
  const hasChildren = node.children && node.children.length > 0;
  const indent = depth * 12;
  const isLayer = depth === 1;
  const isLeaf = !hasChildren && depth > 0;
  const color = depth === 1 ? LAYER_COLORS[node.name] ?? undefined : undefined;

  return (
    <>
      <div
        className="scorebreakdown-row"
        style={{
          paddingLeft: 8 + indent,
          borderLeft: depth === 1 ? `2px solid ${color ?? "transparent"}` : undefined,
          marginBottom: isLayer ? 4 : 0,
        }}
      >
        {/* Label + score bar */}
        <div
          className="scorebreakdown-label"
          style={{ fontWeight: isLayer ? 600 : 400 }}
        >
          <span style={{ color: color }}>
            {isLayer ? LAYER_NAMES[node.name] ?? labelFor(node.name) : labelFor(node.name)}
          </span>
          {isLayer && (
            <span className="scorebreakdown-weight">
              × {formatPercent(node.weight)}
            </span>
          )}
        </div>

        <div className="scorebreakdown-values">
          {/* Score bar visualization */}
          {isLayer || isLeaf ? (
            <>
              <span
                className="scorebreakdown-score"
                style={{ color: color }}
              >
                {formatScore(node.score)}
              </span>
              {isLayer && (
                <>
                  <span className="scorebreakdown-contrib-label">→</span>
                  <span
                    className="scorebreakdown-contrib"
                    style={{ color }}
                  >
                    {formatScore(node.contribution ?? node.score * node.weight)}
                  </span>
                </>
              )}
              {isLeaf && depth === 2 && node.name !== "total_score" && (
                <>
                  <span className="scorebreakdown-contrib-label">×</span>
                  <span className="scorebreakdown-contrib-minor">
                    {formatPercent(node.weight)}
                  </span>
                  <span className="scorebreakdown-contrib-label">→</span>
                  <span className="scorebreakdown-contrib-minor">
                    {formatScore(node.contribution ?? 0)}
                  </span>
                </>
              )}
            </>
          ) : null}

          {/* Progress bar for layers */}
          {isLayer && (
            <div className="scorebreakdown-bar-track">
              <div
                className="scorebreakdown-bar-fill"
                style={{
                  width: `${Math.min(100, (node.score / Math.max(maxScore, 1)) * 100)}%`,
                  backgroundColor: color,
                }}
              />
            </div>
          )}
        </div>

        {/* Explanation */}
        {node.explanation && depth <= 2 && (
          <div className="scorebreakdown-explanation">{node.explanation}</div>
        )}
      </div>

      {/* Children */}
      {hasChildren &&
        node.children!.map((child) => (
          <AttributionRow
            key={child.name}
            node={child}
            depth={depth + 1}
            maxScore={100}
          />
        ))}
    </>
  );
}

export default function ScoreBreakdown({ scorecard, scoreHistory }: ScoreBreakdownProps) {
  const tree = scorecard.attribution_tree;
  const layers = tree?.children;
  const hardGates = extractHardGates(scorecard);
  const hasHardGates = hardGates.length > 0;

  // Compute max score for each layer from its children for progress bar reference
  const layerMaxScores: Record<string, number> = {};
  if (layers) {
    for (const layer of layers) {
      const children = layer.children;
      if (children && children.length > 0) {
        // For prior: sum of dim_scores; for empirical/checklist: sum of points
        layerMaxScores[layer.name] = children.reduce(
          (acc, c) => acc + (c.weight > 0 ? c.score / (c.contribution > 0 ? c.weight : 1) : c.score),
          0,
        );
      } else {
        layerMaxScores[layer.name] = 100;
      }
    }
  }

  return (
    <div className="scorebreakdown-panel">
      {/* Header: total score + decision band */}
      <div className="scorebreakdown-header">
        <span className="scorebreakdown-total-label">总分</span>
        <span className="scorebreakdown-total-value">
          {formatScore(scorecard.total_score)}
        </span>
        <span
          className={`badge ${
            scorecard.decision_band === "submit_candidate"
              ? "badge-positive"
              : scorecard.decision_band === "hard_gate_blocked"
                ? "badge-negative"
                : scorecard.decision_band === "optimize_before_submit"
                  ? "badge-warning"
                  : scorecard.decision_band === "research_only"
                    ? "badge-info"
                    : "badge-neutral"
          }`}
          style={{ marginLeft: 8, fontSize: "0.625rem" }}
        >
          {decisionBandLabel(scorecard.decision_band)}
        </span>
        {scorecard.score_basis === "local_prior" && (
          <span
            className="badge badge-neutral"
            style={{ marginLeft: 4, fontSize: "0.625rem" }}
            title="基于本地先验评分，尚未获得官方实证数据"
          >
            本地预估
          </span>
        )}
      </div>

      {/* Divider */}
      <div className="scorebreakdown-divider" />

      {/* Three-layer breakdown */}
      <div className="scorebreakdown-body">
        {layers && layers.length > 0 ? (
          layers.map((layer) => (
            <AttributionRow
              key={layer.name}
              node={layer}
              depth={1}
              maxScore={layerMaxScores[layer.name] ?? 100}
            />
          ))
        ) : (
          <FallbackBreakdown scorecard={scorecard} />
        )}
      </div>

      {/* Hard gates section */}
      {hasHardGates && (
        <>
          <div className="scorebreakdown-divider" />
          <div className="scorebreakdown-gates">
            <div className="scorebreakdown-gates-title">
              门禁状态
              <span className="scorebreakdown-gates-summary">
                {hardGates.filter((g) => g.passed).length}/{hardGates.length} 通过
              </span>
            </div>
            <div className="scorebreakdown-gates-list">
              {hardGates.map((gate) => (
                <div
                  key={gate.name}
                  className={`scorebreakdown-gate-item ${
                    gate.passed ? "gate-passed" : "gate-failed"
                  }`}
                  title={gate.explanation}
                >
                  <span className="scorebreakdown-gate-icon">
                    {gate.passed ? "✓" : "✗"}
                  </span>
                  <span className="scorebreakdown-gate-name">
                    {labelFor(gate.name)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Top failures hints */}
      {scorecard.top_failures && scorecard.top_failures.length > 0 && (
        <>
          <div className="scorebreakdown-divider" />
          <div className="scorebreakdown-failures">
            <div className="scorebreakdown-failures-title">主要短板</div>
            {scorecard.top_failures.slice(0, 3).map((f, i) => (
              <div key={i} className="scorebreakdown-failure-item">
                {f.item || f.reason || ""}
              </div>
            ))}
          </div>
        </>
      )}

      {/* P1-5: Scoring history mini sparkline */}
      <ScoreHistorySparkline history={scoreHistory} />
    </div>
  );
}

/** P1-5: Mini CSS-only sparkline showing the last 5–10 scoring history points. */
function ScoreHistorySparkline({ history }: { history?: ScoreHistoryPoint[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!history || history.length < 2) return null;

  // Take the last 10 points for display
  const points = history.slice(-10);
  const scores = points.map((p) => p.totalScore);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);
  const range = maxScore - minScore || 1;

  // Short date labels (MM-DD)
  const formatLabel = (ts: string): string => {
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return ts.slice(0, 5);
      return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    } catch {
      return ts.slice(0, 5);
    }
  };

  const trend = scores[scores.length - 1] - scores[0];
  const trendIcon = trend > 0 ? "▲" : trend < 0 ? "▼" : "─";
  const trendColor = trend > 0 ? "text-positive" : trend < 0 ? "text-negative" : "text-text-tertiary";

  return (
    <>
      <div className="scorebreakdown-divider" />
      <div className="scorebreakdown-history">
        {/* Header row with toggle */}
        <button
          type="button"
          className="scorebreakdown-history-toggle"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
        >
          <span className="scorebreakdown-history-title">
            评分历史
            <span className={`ml-1.5 text-xs ${trendColor}`}>
              {trendIcon} {Math.abs(trend).toFixed(1)}
            </span>
          </span>
          <span className="scorebreakdown-history-chevron" aria-hidden="true">
            {expanded ? "▾" : "▸"}
          </span>
        </button>

        {expanded && (
          <div className="scorebreakdown-sparkline-container">
            {/* Mini sparkline */}
            <div className="scorebreakdown-sparkline" aria-label={`评分历史趋势，共 ${points.length} 个数据点`}>
              {points.map((point, i) => {
                const heightPct = ((point.totalScore - minScore) / range) * 100;
                return (
                  <div
                    key={`${point.timestamp}-${i}`}
                    className="scorebreakdown-sparkline-bar-wrapper"
                    title={`${formatLabel(point.timestamp)}: ${point.totalScore.toFixed(1)}`}
                  >
                    <div
                      className="scorebreakdown-sparkline-bar"
                      style={{ height: `${Math.max(4, heightPct)}%` }}
                    />
                    <span className="scorebreakdown-sparkline-label">
                      {formatLabel(point.timestamp)}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Score list */}
            <div className="scorebreakdown-history-list">
              {points.slice().reverse().map((point, i) => (
                <div key={i} className="scorebreakdown-history-row">
                  <span className="scorebreakdown-history-time">{formatLabel(point.timestamp)}</span>
                  <span className="scorebreakdown-history-score">
                    {point.totalScore.toFixed(1)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Inline mini sparkline when collapsed */}
        {!expanded && (
          <div className="scorebreakdown-sparkline-inline" aria-hidden="true">
            {points.map((point, i) => {
              const heightPct = ((point.totalScore - minScore) / range) * 100;
              return (
                <div
                  key={i}
                  className="scorebreakdown-sparkline-dot"
                  style={{ height: `${Math.max(3, heightPct)}%` }}
                />
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

/** Fallback when attribution_tree is not available — build from raw layers. */
function FallbackBreakdown({ scorecard }: { scorecard: Scorecard }) {
  const lw = scorecard.layer_weights ?? { prior: 0.3, empirical: 0.45, checklist: 0.25 };

  const layers = [
    {
      name: "prior_score",
      label: "先验评分",
      color: LAYER_COLORS.prior_score,
      score: scorecard.prior?.score ?? scorecard.prior_score ?? 0,
      weight: lw.prior ?? 0.3,
      contribution:
        (scorecard.prior?.score ?? scorecard.prior_score ?? 0) * (lw.prior ?? 0.3),
      source: scorecard.prior?.source ?? "",
    },
    {
      name: "empirical_score",
      label: "实证评分",
      color: LAYER_COLORS.empirical_score,
      score: scorecard.empirical?.score ?? scorecard.empirical_score ?? 0,
      weight: lw.empirical ?? 0.45,
      contribution:
        (scorecard.empirical?.score ?? scorecard.empirical_score ?? 0) *
        (lw.empirical ?? 0.45),
      status: scorecard.empirical?.status ?? "",
    },
    {
      name: "submission_checklist",
      label: "提交清单",
      color: LAYER_COLORS.submission_checklist,
      score:
        scorecard.submission_checklist?.score ?? scorecard.checklist_score ?? 0,
      weight: lw.checklist ?? 0.25,
      contribution:
        (scorecard.submission_checklist?.score ?? scorecard.checklist_score ?? 0) *
        (lw.checklist ?? 0.25),
    },
  ];

  return (
    <>
      {layers.map((layer) => (
        <div
          key={layer.name}
          className="scorebreakdown-row"
          style={{
            borderLeft: `2px solid ${layer.color}`,
            marginBottom: 4,
            paddingLeft: 8,
          }}
        >
          <div className="scorebreakdown-label" style={{ fontWeight: 600 }}>
            <span style={{ color: layer.color }}>{layer.label}</span>
            <span className="scorebreakdown-weight">
              × {formatPercent(layer.weight)}
            </span>
          </div>
          <div className="scorebreakdown-values">
            <span className="scorebreakdown-score" style={{ color: layer.color }}>
              {formatScore(layer.score)}
            </span>
            <span className="scorebreakdown-contrib-label">→</span>
            <span className="scorebreakdown-contrib" style={{ color: layer.color }}>
              {formatScore(layer.contribution)}
            </span>
          </div>
          {(layer.source || layer.status) && (
            <div className="scorebreakdown-explanation">
              {[layer.source, layer.status].filter(Boolean).join(" · ")}
            </div>
          )}
        </div>
      ))}
    </>
  );
}

function decisionBandLabel(band: string): string {
  switch (band) {
    case "submit_candidate":
      return "可提交";
    case "optimize_before_submit":
      return "需优化";
    case "research_only":
      return "仅研究";
    case "hard_gate_blocked":
      return "门禁阻断";
    case "abandon_or_rebuild":
      return "建议放弃";
    default:
      return band || "未知";
  }
}
