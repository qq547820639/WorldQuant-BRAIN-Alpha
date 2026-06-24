/** Detailed score breakdown — header, layers, hard gates, and top failures. */

import { memo } from "react";
import type { Scorecard, ScoreLayerItem } from "@/types";
import ScoreBar, { formatScore, labelFor } from "./ScoreBar";
import { LAYER_COLORS } from "./ScoreBar";

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
      const explanation = item.passed
        ? `通过: ${actual} ${item.direction ?? ""} ${target}`
        : `失败: ${actual} ${item.direction ?? ""} ${target}`;
      return {
        name: item.name ?? "未知",
        passed: Boolean(item.passed),
        explanation,
      };
    });
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

interface FallbackProps {
  scorecard: Scorecard;
}

const FallbackBreakdown = memo(function FallbackBreakdown({ scorecard }: FallbackProps) {
  const lw = scorecard.layer_weights ?? {
    prior: 0.3,
    empirical: 0.45,
    checklist: 0.25,
  };

  const layers = [
    {
      name: "prior_score",
      label: "先验评分",
      color: LAYER_COLORS.prior_score,
      score: scorecard.prior?.score ?? scorecard.prior_score ?? 0,
      weight: lw.prior ?? 0.3,
      contribution:
        (scorecard.prior?.score ?? scorecard.prior_score ?? 0) *
        (lw.prior ?? 0.3),
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
              × {`${(layer.weight * 100).toFixed(0)}%`}
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
});

interface Props {
  scorecard: Scorecard;
}

export default memo(function ScoreDetails({ scorecard }: Props) {
  const tree = scorecard.attribution_tree;
  const layers = tree?.children;
  const hardGates = extractHardGates(scorecard);
  const hasHardGates = hardGates.length > 0;

  const layerMaxScores: Record<string, number> = {};
  if (layers) {
    for (const layer of layers) {
      const children = layer.children;
      if (children && children.length > 0) {
        layerMaxScores[layer.name] = children.reduce(
          (acc, c) =>
            acc + (c.weight > 0 ? c.score / ((c.contribution ?? 0) > 0 ? c.weight : 1) : c.score),
          0,
        );
      } else {
        layerMaxScores[layer.name] = 100;
      }
    }
  }

  return (
    <>
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

      <div className="scorebreakdown-divider" />

      <div className="scorebreakdown-body">
        {layers && layers.length > 0 ? (
          layers.map((layer) => (
            <ScoreBar
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
    </>
  );
});
