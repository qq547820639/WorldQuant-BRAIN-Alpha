/** Scoring visualization with attribution tree and gate status. */

import { useState, useCallback, useMemo } from "react";
import type { Candidate, ScoreAttribution } from "@/types";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

// Mock sample data for demo — real data comes from /api/candidates
const SAMPLE_CANDIDATE: Candidate = {
  alpha_id: "alpha_demo_001",
  expression: "rank(ts_zscore(close, 20)) * rank(ts_delta(volume, 5))",
  family: "momentum_breakout",
  hypothesis: "Short-term momentum combined with volume surge signals",
  lifecycle_status: "gated:submit_candidate",
  scorecard: {
    total_score: 82.5,
    prior_score: 26.4,
    empirical_score: 38.1,
    checklist_score: 18.0,
    decision_band: "submit_candidate",
    attribution: [
      { dimension: "Economic Logic", score: 8.2, weight: 0.10, sub_items: [
        { dimension: "Momentum concept", score: 9.0, weight: 0.4 },
        { dimension: "Volume confirmation", score: 7.5, weight: 0.3 },
        { dimension: "Cross-sectional logic", score: 8.0, weight: 0.3 },
      ]},
      { dimension: "Structure Quality", score: 7.8, weight: 0.08, sub_items: [
        { dimension: "Nesting depth", score: 8.0, weight: 0.5 },
        { dimension: "Field-operator match", score: 7.5, weight: 0.5 },
      ]},
      { dimension: "Field/Operator Support", score: 9.0, weight: 0.07 },
      { dimension: "Data Compliance", score: 10.0, weight: 0.05 },
    ],
  },
  official_metrics: {
    sharpe: 1.65,
    fitness: 1.32,
    turnover: 0.28,
    returns: 0.15,
    drawdown: 0.08,
    correlation: 0.12,
    weight_concentration: 0.05,
    pass_fail: "PASS",
  },
  gate: {
    passed: true,
    status: "PASSED",
    failed_reasons: [],
    failed_checks: [
      { name: "LOW_SHARPE", passed: true, detail: "Sharpe 1.65 >= 1.25", severity: "ERROR" },
      { name: "LOW_FITNESS", passed: true, detail: "Fitness 1.32 >= 1.0", severity: "ERROR" },
      { name: "LOW_TURNOVER", passed: true, detail: "Turnover 0.28 >= 0.01", severity: "ERROR" },
      { name: "HIGH_TURNOVER", passed: true, detail: "Turnover 0.28 <= 0.70", severity: "ERROR" },
      { name: "SELF_CORRELATION", passed: true, detail: "Correlation 0.12 < 0.70", severity: "ERROR" },
      { name: "CONCENTRATED_WEIGHT", passed: true, detail: "Concentration 0.05 <= 0.10", severity: "ERROR" },
    ],
  },
  decision_band: "submit_candidate",
};

export default function ScoringPanel({ notify }: Props) {
  const [candidate] = useState<Candidate>(SAMPLE_CANDIDATE);
  const sc = candidate.scorecard;
  const m = candidate.official_metrics;
  const gate = candidate.gate;

  const renderAttribution = (items: ScoreAttribution[] | undefined, depth = 0) => {
    if (!items) return null;
    return (
      <div className={`space-y-1 ${depth > 0 ? "ml-4 pl-3 border-l border-gray-700" : ""}`}>
        {items.map((item, i) => (
          <div key={i} className="text-xs">
            <div className="flex justify-between py-1">
              <span className="text-gray-300">{item.dimension}</span>
              <span className="text-muted font-mono">{item.score.toFixed(1)}</span>
            </div>
            {item.sub_items && renderAttribution(item.sub_items, depth + 1)}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Expression overview */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-200 mb-2">Alpha Expression</h3>
        <code className="block bg-gray-950 rounded-lg p-3 text-xs text-brand-300 font-mono break-all">
          {candidate.expression}
        </code>
        <div className="flex gap-3 mt-3 text-xs text-muted">
          <span>Family: <span className="text-gray-300">{candidate.family}</span></span>
          <span>Status: <span className={`badge ${candidate.gate?.passed ? "badge-success" : "badge-danger"}`}>{candidate.lifecycle_status}</span></span>
        </div>
      </div>

      {/* Scorecard */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">Scorecard</h3>
          <div className="text-center mb-4">
            <span className="text-4xl font-bold text-brand-400">{sc?.total_score?.toFixed(1)}</span>
            <span className="text-muted text-lg">/100</span>
          </div>
          <div className="space-y-2">
            <ScoreBar label="Prior" value={sc?.prior_score ?? 0} max={30} color="bg-blue-500" />
            <ScoreBar label="Empirical" value={sc?.empirical_score ?? 0} max={45} color="bg-green-500" />
            <ScoreBar label="Checklist" value={sc?.checklist_score ?? 0} max={25} color="bg-yellow-500" />
          </div>
          {sc?.attribution && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-gray-300 mb-2">Attribution</p>
              {renderAttribution(sc.attribution)}
            </div>
          )}
        </div>

        {/* Official Metrics */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">Official Metrics</h3>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <MetricRow label="Sharpe" value={m?.sharpe} threshold={1.25} />
            <MetricRow label="Fitness" value={m?.fitness} threshold={1.0} />
            <MetricRow label="Turnover" value={m?.turnover} threshold={0.01} format="percent" />
            <MetricRow label="Returns" value={m?.returns} format="percent" />
            <MetricRow label="Drawdown" value={m?.drawdown} format="percent" max={0.25} />
            <MetricRow label="Correlation" value={m?.correlation} max={0.70} />
            <MetricRow label="Concentration" value={m?.weight_concentration} max={0.10} format="percent" />
          </div>
        </div>
      </div>

      {/* Gate Checks */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-200 mb-3">Quality Gate</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {gate?.failed_checks?.map((check, i) => (
            <div key={i} className={`flex items-center gap-2 p-2 rounded-lg text-xs ${check.passed ? "bg-success/10 border border-success/20" : "bg-danger/10 border border-danger/20"}`}>
              <span className={check.passed ? "text-success" : "text-danger"}>{check.passed ? "✓" : "✕"}</span>
              <div>
                <span className="font-medium">{check.name}</span>
                <p className="text-muted">{check.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Score progress bar */
function ScoreBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-400">{label}</span>
        <span className="text-muted font-mono">{value.toFixed(1)}/{max}</span>
      </div>
      <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
        <div className={`${color} h-1.5 rounded-full transition-all duration-300`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** Metric row with threshold indication */
function MetricRow({ label, value, threshold, max, format }: {
  label: string;
  value?: number;
  threshold?: number;
  max?: number;
  format?: "percent";
}) {
  if (value == null) return null;
  const formatted = format === "percent" ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
  const ok = threshold != null ? value >= threshold : max != null ? value <= max : true;
  return (
    <div className="flex justify-between items-center p-2 bg-gray-800/50 rounded-lg">
      <span className="text-gray-400">{label}</span>
      <span className={`font-mono ${threshold != null || max != null ? (ok ? "text-success" : "text-danger") : "text-gray-200"}`}>
        {formatted}
      </span>
    </div>
  );
}
