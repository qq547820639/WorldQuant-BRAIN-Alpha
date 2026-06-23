/** Individual score bar display — renders a single attribution node row. */

import type { AttributionNode } from "@/types";

const LAYER_NAMES: Record<string, string> = {
  prior_score: "先验评分",
  empirical_score: "实证评分",
  submission_checklist: "提交清单",
};

const LAYER_COLORS: Record<string, string> = {
  prior_score: "var(--color-layer-color-info)",
  empirical_score: "var(--color-layer-color-success)",
  submission_checklist: "var(--color-layer-color-warning)",
};

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

export function labelFor(name: string): string {
  return DIM_LABELS[name] || name.replace(/_/g, " ");
}

export function formatScore(value: number): string {
  return value.toFixed(1);
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

export { LAYER_COLORS, LAYER_NAMES };

interface Props {
  node: AttributionNode;
  depth: number;
  maxScore: number;
}

export default function ScoreBar({ node, depth, maxScore }: Props) {
  const hasChildren = node.children && node.children.length > 0;
  const indent = depth * 12;
  const isLayer = depth === 1;
  const isLeaf = !hasChildren && depth > 0;
  const color =
    depth === 1 ? LAYER_COLORS[node.name] ?? undefined : undefined;

  return (
    <>
      <div
        className="scorebreakdown-row"
        style={{
          paddingLeft: 8 + indent,
          borderLeft:
            depth === 1
              ? `2px solid ${color ?? "transparent"}`
              : undefined,
          marginBottom: isLayer ? 4 : 0,
        }}
      >
        <div
          className="scorebreakdown-label"
          style={{ fontWeight: isLayer ? 600 : 400 }}
        >
          <span style={{ color }}>
            {isLayer
              ? LAYER_NAMES[node.name] ?? labelFor(node.name)
              : labelFor(node.name)}
          </span>
          {isLayer && (
            <span className="scorebreakdown-weight">
              × {formatPercent(node.weight)}
            </span>
          )}
        </div>

        <div className="scorebreakdown-values">
          {isLayer || isLeaf ? (
            <>
              <span
                className="scorebreakdown-score"
                style={{ color }}
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
                    {formatScore(
                      node.contribution ?? node.score * node.weight,
                    )}
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

        {node.explanation && depth <= 2 && (
          <div className="scorebreakdown-explanation">
            {node.explanation}
          </div>
        )}
      </div>

      {hasChildren &&
        node.children!.map((child) => (
          <ScoreBar
            key={child.name}
            node={child}
            depth={depth + 1}
            maxScore={100}
          />
        ))}
    </>
  );
}
