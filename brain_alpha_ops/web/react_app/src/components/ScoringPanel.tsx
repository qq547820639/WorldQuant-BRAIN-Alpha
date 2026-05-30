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

  const handleScoreEvent = useCallback((event: SSEEvent) => {
    const progress = (event.progress || event.data || {}) as UnifiedProgress;
    setScoreProgress(progress);
    if (event.type === "error" || event.ok === false || event.status === "failed") {
      const message = event.error || event.status_message || "Scoring failed";
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
      notify("success", `Scoring refreshed for ${candidate?.alpha_id || "candidate"}`);
      return;
    }
    setScoreState("progress");
  }, [candidate?.alpha_id, notify]);

  useSSE(scoreTaskId ? `/sse?job_id=${encodeURIComponent(scoreTaskId)}` : null, { onEvent: handleScoreEvent });

  const loadScore = useCallback(async () => {
    if (!candidate) return;
    setScoring(null);
    setScoreState("loading");
    setScoreError(null);
    setScoreProgress({ phase: "scoring", status_message: `Starting scoring for ${candidate.alpha_id || "candidate"}.` });
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
  }, [callAttributionApi, callScoreApi, candidate, notify]);

  useEffect(() => {
    if (candidate) loadScore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidate?.alpha_id]);

  const attribution = attributionApi.data?.attribution || scoring?.attribution_tree || null;
  const hardGates = attributionApi.data?.hard_gates || scoring?.hard_gates || [];
  const softGates = attributionApi.data?.soft_gates || scoring?.soft_gates || [];
  const failures = attributionApi.data?.top_failures || scoring?.top_failures || [];
  const hints = attributionApi.data?.improvement_hints || scoring?.improvement_hints || [];
  const m = candidate?.official_metrics;
  const selfCorrelation = metricWithStatus(m?.self_correlation, m?.self_correlation_status, m?.correlation);
  const loading = scoreState === "loading" || scoreState === "progress" || attributionApi.loading;
  const error = scoreError || scoreApi.error || attributionApi.error;
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
          {node.children?.map((child) => (
            <div key={`${child.name}-${depth}`}>{renderAttribution(child, depth + 1)}</div>
          ))}
        </div>
      </div>
    );
  };

  if (!candidate) {
    return (
      <div className="card w-full max-w-2xl min-w-0">
        <h3 className="text-sm font-semibold text-gray-200 mb-2">Select a Candidate</h3>
        <p className="text-sm text-muted">
          Open Candidates, choose a real candidate, then click Score to evaluate it through
          /api/scoring/evaluate and /api/scoring/attribution.
        </p>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-6 animate-fade-in">
      {error && (
        <div className="card border-danger/40 bg-danger/10" role="alert" aria-live="assertive">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-danger text-sm">Failed to load official scoring: {error}</p>
            <button onClick={loadScore} className="btn-secondary text-sm" disabled={loading}>
              Retry
            </button>
          </div>
        </div>
      )}

      <ProgressFeedback
        state={error ? "error" : scoreState}
        title="Scoring and validation"
        progress={scoreProgress}
        error={error}
        onRetry={loadScore}
        compact={scoreState === "idle" || scoreState === "success"}
      />

      {/* Expression overview */}
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
          <h3 className="text-sm font-semibold text-gray-200">Alpha Expression</h3>
          <button onClick={loadScore} className="btn-secondary text-xs" disabled={loading}>
            {loading ? "Scoring..." : "Refresh Score"}
          </button>
        </div>
        <code className="block bg-gray-950 rounded-lg p-3 text-xs text-brand-300 font-mono break-all">
          {candidate.expression}
        </code>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-3 text-xs text-muted">
          <span>Family: <span className="text-gray-300">{candidate.family}</span></span>
          <span>Status: <span className={`badge ${scoring?.passed_gate || candidate.gate?.passed ? "badge-success" : "badge-danger"}`}>{candidate.lifecycle_status}</span></span>
          <span>ID: <span className="text-gray-300 font-mono">{candidate.alpha_id}</span></span>
        </div>
      </div>

      {/* Scorecard */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">Scorecard</h3>
          <div className="text-center mb-4">
            <span className="text-4xl font-bold text-brand-400">
              {formatNumber(scoring?.total_score ?? candidate.scorecard?.total_score, 1)}
            </span>
            <span className="text-muted text-lg">/100</span>
          </div>
          <div className="space-y-2">
            <ScoreBar label="Prior" value={layerScores.prior} max={30} color="bg-blue-500" />
            <ScoreBar label="Empirical" value={layerScores.empirical} max={45} color="bg-green-500" />
            <ScoreBar label="Checklist" value={layerScores.checklist} max={25} color="bg-yellow-500" />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
            <InfoPill label="Decision" value={scoring?.decision_band || candidate.decision_band || "-"} />
            <InfoPill label="Schema" value={scoring?.scoring_schema || "-"} />
            <InfoPill label="Gate" value={scoring?.passed_gate ? "PASS" : "FAIL"} />
            <InfoPill label="API Dev." value={formatNumber(scoring?.api_output_deviation, 4)} />
          </div>
          {attribution && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-gray-300 mb-2">Attribution</p>
              {renderAttribution(attribution)}
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
            <MetricRow label="Self Correlation" value={selfCorrelation} max={0.70} />
            <MetricRow label="Concentration" value={m?.weight_concentration} max={0.10} format="percent" />
          </div>
        </div>
      </div>

      {/* Gate Checks */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-200 mb-3">Official Gate Checks</h3>
        <div className="space-y-4">
          <GateGroup title="Hard Gates" gates={hardGates} />
          <GateGroup title="Soft Gates" gates={softGates} />
        </div>
      </div>

      {(failures.length > 0 || hints.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <InsightList title="Top Failures" items={failures} />
          <HintList title="Improvement Hints" items={hints} />
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
  if (!gates.length) return <p className="text-xs text-muted">{title}: No data</p>;
  return (
    <div>
      <p className="text-xs font-semibold text-gray-300 mb-2">{title}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {gates.flatMap((gate) => {
          const checks: OfficialGateCheckItem[] = gate.check_items?.length
            ? gate.check_items
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
            <p className="text-danger/90 font-medium">{item.item || "Failure"}</p>
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
