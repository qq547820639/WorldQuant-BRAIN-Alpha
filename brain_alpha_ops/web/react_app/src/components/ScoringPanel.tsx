/** Scoring visualization with attribution tree and gate status. */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import ProgressFeedback from "@/components/ProgressFeedback";
import type {
  AttributionNode,
  Candidate,
  FailureItem,
  OfficialGateCheckItem,
  OfficialGateResult,
  ScoringAttributionResponse,
  ScoringResult,
  SSEEvent,
  UnifiedProgress,
} from "@/types";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  candidate: Candidate | null;
}

export default function ScoringPanel({ notify, candidate }: Props) {
  const scoreApi = useApi<{ job_id?: string; task_id?: string }>();
  const attributionApi = useApi<ScoringAttributionResponse>();
  const [scoring, setScoring] = useState<ScoringResult | null>(null);
  const [scoreTaskId, setScoreTaskId] = useState<string | null>(null);
  const [scoreState, setScoreState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [scoreProgress, setScoreProgress] = useState<UnifiedProgress | null>(null);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const callScoreApi = scoreApi.call;
  const callAttributionApi = attributionApi.call;
  const resetAttributionApi = attributionApi.reset;

  const handleScoreEvent = useCallback((event: SSEEvent) => {
    const progress = (event.progress || event.data || {}) as UnifiedProgress;
    setScoreProgress(progress);
    if (event.type === "error" || event.ok === false || event.status === "failed") {
      const message = event.error || event.status_message || "评分失败";
      setScoreState("error");
      setScoreError(message);
      notify("error", message);
      setScoreTaskId(null);
      return;
    }
    if (event.type === "complete") {
      const result = event.result as ScoringResult | undefined;
      if (result) setScoring(result);
      setScoreState("success");
      setScoreTaskId(null);
      notify("success", `${candidate?.alpha_id || "候选"} 评分已刷新`);
      return;
    }
    setScoreState("progress");
  }, [candidate?.alpha_id, notify]);

  const handleScoreStreamExhausted = useCallback(() => {
    const message = "评分实时流已断开，请重试以确认最新评分。";
    setScoreState("error");
    setScoreError(message);
    notify("warning", message);
  }, [notify]);

  useSSE(scoreTaskId ? `/sse?job_id=${encodeURIComponent(scoreTaskId)}` : null, {
    onEvent: handleScoreEvent,
    onExhausted: handleScoreStreamExhausted,
  });

  const loadScore = useCallback(async () => {
    if (!candidate) return;
    setScoring(null);
    resetAttributionApi();
    setScoreState("loading");
    setScoreError(null);
    setScoreProgress({ phase: "scoring", status_message: `正在为 ${candidate.alpha_id || "候选"} 启动评分。` });
    const payload = candidate.alpha_id
      ? { alpha_id: candidate.alpha_id, candidate }
      : { candidate };
    const [scoreResult, attributionResult] = await Promise.all([
      callScoreApi("/api/scoring/evaluate", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
      callAttributionApi("/api/scoring/attribution", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    ]);
    const nextTaskId = String((scoreResult as unknown as { task_id?: string; job_id?: string } | null)?.task_id || (scoreResult as unknown as { job_id?: string } | null)?.job_id || "");
    if (scoreResult?.ok && nextTaskId) {
      setScoreTaskId(nextTaskId);
      setScoreState("progress");
    } else if (scoreResult?.error) {
      setScoreState("error");
      setScoreError(scoreResult.error);
      notify("error", scoreResult.error);
    }
    if (attributionResult && !attributionResult.ok && attributionResult.error) {
      notify("error", attributionResult.error);
    }
  }, [callAttributionApi, callScoreApi, candidate, notify, resetAttributionApi]);

  useEffect(() => {
    if (candidate) loadScore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidate?.alpha_id]);

  const attribution = scoring?.attribution_tree || attributionApi.data?.attribution || null;
  const hardGates = nonEmpty(scoring?.hard_gates) || nonEmpty(attributionApi.data?.hard_gates) || [];
  const softGates = nonEmpty(scoring?.soft_gates) || nonEmpty(attributionApi.data?.soft_gates) || [];
  const failures = nonEmpty(scoring?.top_failures) || nonEmpty(attributionApi.data?.top_failures) || [];
  const hints = nonEmpty(scoring?.improvement_hints) || nonEmpty(attributionApi.data?.improvement_hints) || [];
  const m = candidate?.official_metrics;
  const selfCorrelation = metricWithStatus(m?.self_correlation, m?.self_correlation_status, m?.correlation);
  const loading = scoreState === "loading" || scoreState === "progress" || attributionApi.loading;
  const error = scoreError || scoreApi.error || attributionApi.error;
  const lifecycleStatus = String(candidate?.lifecycle_status || "-");
  const layerScores = useMemo(() => {
    const prior = Number(scoring?.prior?.score ?? candidate?.scorecard?.prior_score ?? 0);
    const empirical = Number(scoring?.empirical?.score ?? candidate?.scorecard?.empirical_score ?? 0);
    const checklist = Number(scoring?.checklist?.score ?? candidate?.scorecard?.checklist_score ?? 0);
    return { prior, empirical, checklist };
  }, [candidate?.scorecard, scoring]);

  const renderAttribution = (node: AttributionNode | null | undefined, depth = 0) => {
    if (!node) return null;
    return (
      <div className={`space-y-1 ${depth > 0 ? "ml-4 pl-3 border-l border-gray-700" : ""}`}>
        <div className="text-xs">
          <div className="flex justify-between gap-3 py-1">
            <span className="text-gray-300">{node.name}</span>
            <span className="text-muted font-mono whitespace-nowrap">
              {formatNumber(node.score, 1)} × {formatNumber(node.weight, 2)}
            </span>
          </div>
          {node.explanation && <p className="text-[11px] text-muted pb-1">{node.explanation}</p>}
          {childNodes(node).map((child) => (
            <div key={`${child.name}-${depth}`}>{renderAttribution(child, depth + 1)}</div>
          ))}
        </div>
      </div>
    );
  };

  if (!candidate) {
    return (
      <div className="card w-full max-w-2xl min-w-0">
        <h3 className="text-sm font-semibold text-gray-200 mb-2">选择候选</h3>
        <p className="text-sm text-muted">
          打开候选管理，选择一个真实候选，然后点击评分以通过 /api/scoring/evaluate 和 /api/scoring/attribution 进行评估。
        </p>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-6 animate-fade-in">
      {error && (
        <div className="card border-danger/40 bg-danger/10" role="alert" aria-live="assertive">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-danger text-sm">加载官方评分失败: {error}</p>
            <button onClick={loadScore} className="btn-secondary text-sm" disabled={loading}>
              重试
            </button>
          </div>
        </div>
      )}

      <ProgressFeedback
        state={error ? "error" : scoreState}
        title="评分与验证"
        progress={scoreProgress}
        error={error}
        onRetry={loadScore}
        compact={scoreState === "idle" || scoreState === "success"}
      />

      {/* Expression overview */}
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
          <h3 className="text-sm font-semibold text-gray-200">Alpha表达式</h3>
          <button onClick={loadScore} className="btn-secondary text-xs" disabled={loading}>
            {loading ? "评分中..." : "刷新评分"}
          </button>
        </div>
        <code className="block bg-gray-950 rounded-lg p-3 text-xs text-brand-300 font-mono break-all">
          {candidate.expression}
        </code>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-3 text-xs text-muted">
          <span>家族: <span className="text-gray-300">{candidate.family}</span></span>
          <span>状态: <span className={`badge ${scoring?.passed_gate || candidate.gate?.passed ? "badge-success" : "badge-danger"}`}>{lifecycleStatus}</span></span>
          <span>ID: <span className="text-gray-300 font-mono">{candidate.alpha_id}</span></span>
        </div>
      </div>

      {/* Scorecard */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">评分卡</h3>
          <div className="text-center mb-4">
            <span className="text-4xl font-bold text-brand-400">
              {formatNumber(scoring?.total_score ?? candidate.scorecard?.total_score, 1)}
            </span>
            <span className="text-muted text-lg">/100</span>
          </div>
          <div className="space-y-2">
            <ScoreBar label="先验" value={layerScores.prior} max={30} color="bg-blue-500" />
            <ScoreBar label="经验" value={layerScores.empirical} max={45} color="bg-green-500" />
            <ScoreBar label="检查清单" value={layerScores.checklist} max={25} color="bg-yellow-500" />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
            <InfoPill label="决策" value={scoring?.decision_band || candidate.decision_band || "-"} />
            <InfoPill label="模式" value={scoring?.scoring_schema || "-"} />
            <InfoPill label="门禁" value={scoring?.passed_gate ? "通过" : "失败"} />
            <InfoPill label="API偏差" value={formatNumber(scoring?.api_output_deviation, 4)} />
          </div>
          {attribution && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-gray-300 mb-2">归因分析</p>
              {renderAttribution(attribution)}
            </div>
          )}
        </div>

        {/* Official Metrics */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">官方指标</h3>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <MetricRow label="夏普比率" value={m?.sharpe} threshold={1.25} />
            <MetricRow label="适应度" value={m?.fitness} threshold={1.0} />
            <MetricRow label="换手率" value={m?.turnover} threshold={0.01} format="percent" />
            <MetricRow label="收益率" value={m?.returns} format="percent" />
            <MetricRow label="回撤" value={m?.drawdown} format="percent" max={0.25} />
            <MetricRow label="自相关性" value={selfCorrelation} max={0.70} />
            <MetricRow label="集中度" value={m?.weight_concentration} max={0.10} format="percent" />
          </div>
        </div>
      </div>

      {/* Gate Checks */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-200 mb-3">官方门禁检查</h3>
        <div className="space-y-4">
          <GateGroup title="硬门禁" gates={hardGates} />
          <GateGroup title="软门禁" gates={softGates} />
        </div>
      </div>

      {(failures.length > 0 || hints.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <InsightList title="主要失败原因" items={failures} />
          <HintList title="改进建议" items={hints} />
        </div>
      )}
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
      <div
        className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden"
        role="progressbar"
        aria-label={`${label} score`}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={Math.max(0, Math.min(max, value))}
      >
        <div className={`${color} h-1.5 rounded-full transition-all duration-300`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function InfoPill({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0 bg-gray-800/50 rounded-lg p-2">
      <span className="block text-gray-400">{label}</span>
      <span className="block text-gray-200 font-mono truncate">{String(value ?? "-")}</span>
    </div>
  );
}

function GateGroup({ title, gates }: { title: string; gates: OfficialGateResult[] }) {
  const safeGates = Array.isArray(gates) ? gates : [];
  if (!safeGates.length) return <p className="text-xs text-muted">{title}: 暂无数据</p>;
  return (
    <div>
      <p className="text-xs font-semibold text-gray-300 mb-2">{title}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {safeGates.flatMap((gate) => {
          const checkItems = Array.isArray(gate.check_items) ? gate.check_items : [];
          const checks: OfficialGateCheckItem[] = checkItems.length
            ? checkItems
            : [{ name: gate.gate_name, passed: gate.passed }];
          return checks.map((check, i) => (
              <div
                key={`${gate.gate_name}-${check.name}-${i}`}
                className={`flex items-start gap-2 p-2 rounded-lg text-xs ${
                  check.passed ? "bg-success/10 border border-success/20" : "bg-danger/10 border border-danger/20"
                }`}
              >
                <span className={check.passed ? "text-success" : "text-danger"} aria-hidden="true">{check.passed ? "✓" : "✕"}</span>
                <div>
                  <span className="font-medium">{check.name}</span>
                  <p className="text-muted">
                    {formatGateDetail(check.actual, check.direction, check.target, check.meaning)}
                  </p>
                  <p className="text-[11px] text-muted">{gate.gate_name}</p>
                </div>
              </div>
            ));
        })}
      </div>
    </div>
  );
}

function InsightList({ title, items }: { title: string; items: FailureItem[] }) {
  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-200 mb-3">{title}</h3>
      <div className="space-y-2">
        {items.map((item, i) => (
          <div key={`${item.item || "failure"}-${i}`} className="text-xs border-b border-gray-800/50 pb-2 last:border-0">
            <p className="text-danger/90 font-medium">{item.item || "失败"}</p>
            <p className="text-muted">{item.reason || item.severity || "-"}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function HintList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-200 mb-3">{title}</h3>
      <div className="space-y-2">
        {items.map((item, i) => (
          <p key={`${item}-${i}`} className="text-xs text-gray-300 border-b border-gray-800/50 pb-2 last:border-0">
            {item}
          </p>
        ))}
      </div>
    </div>
  );
}

function formatGateDetail(actual: unknown, direction: unknown, target: unknown, fallback: unknown) {
  const parts = [actual, direction, target].filter((item) => item !== undefined && item !== null && item !== "");
  if (parts.length) return parts.join(" ");
  return String(fallback || "-");
}

function formatNumber(value: unknown, digits: number) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : "-";
}

function metricWithStatus(primary: unknown, status: unknown, fallback: unknown): string | number | undefined {
  return metricValue(primary) ?? metricValue(status) ?? metricValue(fallback);
}

function metricValue(value: unknown): string | number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  return typeof value === "number" || typeof value === "string" ? value : undefined;
}

function nonEmpty<T>(items?: T[] | null): T[] | null {
  return Array.isArray(items) && items.length ? items : null;
}

function childNodes(node: AttributionNode): AttributionNode[] {
  return Array.isArray(node.children) ? node.children : [];
}

/** Metric row with threshold indication */
function MetricRow({ label, value, threshold, max, format }: {
  label: string;
  value?: number | string;
  threshold?: number;
  max?: number;
  format?: "percent";
}) {
  if (value == null) return null;
  const numericValue = Number(value);
  const isNumeric = Number.isFinite(numericValue);
  const formatted = isNumeric
    ? format === "percent" ? `${(numericValue * 100).toFixed(1)}%` : numericValue.toFixed(2)
    : String(value);
  const ok = isNumeric
    ? threshold != null ? numericValue >= threshold : max != null ? numericValue <= max : true
    : true;
  return (
    <div className="flex min-w-0 justify-between items-center gap-3 p-2 bg-gray-800/50 rounded-lg">
      <span className="text-gray-400">{label}</span>
      <span className={`min-w-0 truncate font-mono ${threshold != null || max != null ? (ok ? "text-success" : "text-danger") : "text-gray-200"}`}>
        {formatted}
      </span>
    </div>
  );
}
