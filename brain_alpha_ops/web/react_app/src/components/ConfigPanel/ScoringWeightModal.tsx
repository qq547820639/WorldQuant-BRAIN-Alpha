/** P2-4: Scoring weight transparency modal — read-only display from /api/config_schema. */

import type { ConfigSchema } from "./utils";

interface WeightDimension {
  name: string;
  weight: number;
  children?: WeightDimension[];
}

function extractScoringWeights(
  schema: ConfigSchema | undefined,
  scoring: Record<string, unknown> | undefined,
): { layers: WeightDimension[] } {
  const layers: WeightDimension[] = [];

  const schemaScoring = (schema as Record<string, unknown> | undefined)?.scoring as Record<string, unknown> | undefined;
  const schemaWeights = (schema as Record<string, unknown> | undefined)?.scoring_weights as Record<string, unknown> | undefined;

  const priorWeight = Number(scoring?.prior_layer_weight ?? 0.35);
  const priorChildren = extractLayerChildren(schemaScoring, "prior", schemaWeights);
  layers.push({ name: "先验评分", weight: priorWeight, children: priorChildren });

  const empiricalWeight = Number(scoring?.empirical_layer_weight ?? 0.40);
  const empiricalChildren = extractLayerChildren(schemaScoring, "empirical", schemaWeights);
  layers.push({ name: "实证评分", weight: empiricalWeight, children: empiricalChildren });

  const checklistWeight = Number(scoring?.checklist_layer_weight ?? 0.25);
  const checklistChildren = extractLayerChildren(schemaScoring, "checklist", schemaWeights);
  layers.push({ name: "提交清单", weight: checklistWeight, children: checklistChildren });

  return { layers };
}

function extractLayerChildren(
  schemaScoring: Record<string, unknown> | undefined,
  layer: string,
  schemaWeights: Record<string, unknown> | undefined,
): WeightDimension[] {
  const children: WeightDimension[] = [];

  const layerData = schemaScoring?.[layer] as Record<string, unknown> | undefined;
  const layerWeights = schemaWeights?.[layer] as Record<string, unknown> | undefined;
  const dims = (layerData?.dimensions ?? layerData?.sub_dimensions ?? layerWeights ?? {}) as Record<string, unknown>;

  if (dims && typeof dims === "object") {
    for (const [key, value] of Object.entries(dims)) {
      if (typeof value === "number") {
        children.push({ name: formatDimName(key), weight: value });
      } else if (typeof value === "object" && value !== null) {
        const v = value as Record<string, unknown>;
        const weight = typeof v.weight === "number" ? v.weight : 0;
        const subChildren = extractLayerChildren(
          { [key]: v } as unknown as Record<string, unknown>,
          key,
          undefined,
        );
        children.push({ name: formatDimName(String(v.name ?? v.label ?? key)), weight, children: subChildren.length ? subChildren : undefined });
      }
    }
  }

  return children;
}

function formatDimName(key: string): string {
  const labels: Record<string, string> = {
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
    turnover: "换手率",
    returns: "收益率",
    drawdown: "回撤",
    self_correlation: "自相关",
    prod_correlation: "生产相关性",
    weight_concentration: "权重集中度",
    sub_universe_sharpe: "子宇宙Sharpe",
    is_oos_ratio: "IS/OOS比率",
    margin_bps: "保证金(bps)",
    official_metrics_present: "官方指标存在",
    official_pass: "官方通过",
    economic_logic_check: "经济逻辑检查",
    data_delay_conservative: "保守延迟设置",
    local_quality: "本地质量预筛",
    self_correlation_proxy: "自相关代理",
  };
  return labels[key] ?? key.replace(/_/g, " ");
}

export default function ScoringWeightModal({
  schema,
  scoring,
  onClose,
}: {
  schema: ConfigSchema | undefined;
  scoring: Record<string, unknown> | undefined;
  onClose: () => void;
}) {
  const { layers } = extractScoringWeights(schema, scoring);

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "oklch(0 0 0 / 0.55)", backdropFilter: "blur(3px)",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="评分配置详细权重"
    >
      <div
        style={{
          background: "oklch(0.115 0.007 45)", borderRadius: 8,
          border: "0.5px solid oklch(0.22 0.007 45)",
          maxWidth: 560, width: "calc(100% - 32px)", maxHeight: "80vh",
          overflow: "auto", padding: "24px 20px 20px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
          <div>
            <h3 className="text-base font-semibold text-text-primary">评分配置详细权重</h3>
            <p className="text-xs text-text-tertiary mt-1">
              来自 /api/config_schema 的只读展示，各层及其子维度权重分配。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-ghost btn-sm"
            aria-label="关闭"
            style={{ padding: "2px 6px", fontSize: 18, lineHeight: 1 }}
          >
            ✕
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {layers.map((layer, i) => (
            <div key={i} style={{
              border: "0.5px solid oklch(0.22 0.007 45)",
              borderRadius: 6,
              overflow: "hidden",
            }}>
              <div style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "10px 14px",
                background: "oklch(0.10 0.005 45 / 0.50)",
                borderBottom: layer.children && layer.children.length > 0 ? "0.5px solid oklch(0.22 0.007 45)" : "none",
              }}>
                <span className="text-sm font-medium text-text-primary">{layer.name}</span>
                <span className="text-sm font-mono-value text-accent">
                  {(layer.weight * 100).toFixed(0)}%
                </span>
              </div>

              {layer.children && layer.children.length > 0 && (
                <div style={{ padding: "8px 14px" }}>
                  {layer.children.map((dim, j) => (
                    <div
                      key={j}
                      style={{
                        display: "flex", justifyContent: "space-between", alignItems: "center",
                        padding: "6px 0",
                        borderBottom: j < layer.children!.length - 1 ? "0.5px solid oklch(0.18 0.005 45)" : "none",
                      }}
                    >
                      <span className="text-xs text-text-secondary">{dim.name}</span>
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <div className="progress-bar" style={{ width: 60, height: 4 }} role="progressbar" aria-valuemin={0} aria-valuemax={1} aria-valuenow={dim.weight}>
                          <div className="progress-bar-fill positive" style={{ width: `${Math.min(100, dim.weight * 100)}%`, height: 4 }} />
                        </div>
                        <span className="text-xs font-mono-value text-text-tertiary" style={{ minWidth: 42, textAlign: "right" }}>
                          {(dim.weight * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  ))}
                  {layer.children.length === 0 && (
                    <p className="text-xs text-text-tertiary py-2">暂无子维度数据</p>
                  )}
                </div>
              )}

              {(!layer.children || layer.children.length === 0) && (
                <div style={{ padding: "10px 14px" }}>
                  <p className="text-xs text-text-tertiary">该层无子维度权重数据</p>
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={{ marginTop: 20, display: "flex", justifyContent: "flex-end" }}>
          <button type="button" onClick={onClose} className="btn btn-secondary btn-sm">
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
