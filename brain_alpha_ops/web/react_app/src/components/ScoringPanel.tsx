/** Scoring visualization — Terminal Precision v2.0 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { cancelResultExperience, requestJobCancel } from "@/api/jobCancel";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { resolveJobEventState } from "@/helpers/runPayload";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import ProgressFeedback from "@/components/ProgressFeedback";
import type {
  AttributionNode, Candidate, FailureItem,
  OfficialGateCheckItem, OfficialGateResult,
  ScoringAttributionResponse, ScoringResult, SSEEvent, UnifiedProgress,
} from "@/types";

const RAW_SCORING_TEXT_PATTERN = /(?:raw\s+backend|raw_backend|RAW_BACKEND|SESSION_INVALID|session_invalid|invalid local session|traceback|exception|stack trace|csrf[_-]?token|session[_-]?id|access[_-]?token|refresh[_-]?token|api[_-]?key|client[_-]?secret|password|passwd|pwd|token=|password=|api_key=|csrf_token=)/i;
const BACKEND_STATUS_CODE_PATTERN = /^[A-Z][A-Z0-9_]{2,}$/;
const SNAKE_STATUS_CODE_PATTERN = /^[a-z]+(?:_[a-z0-9]+)+$/;

const LIFECYCLE_STATUS_LABELS: Record<string, string> = {
  completed: "已完成",
  submission_ready: "待提交复核",
  running_backtest: "回测运行中",
  pending_backtest: "等待回测",
  candidate_pool_retained: "候选池保留",
  local_prefilter_rejected: "本地预筛未通过",
  official_validation_queue: "等待官方验证",
  optimize: "继续优化",
  failed: "未通过",
  blocked: "已阻断",
  running: "运行中",
};

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  candidate: Candidate | null;
}

export default function ScoringPanel({ notify, candidate }: Props) {
  const scoreApi = useApi<{ job_id?: string; task_id?: string }>();
  const attributionApi = useApi<ScoringAttributionResponse>();
  const callScoreApi = scoreApi.call;
  const scoreApiError = scoreApi.error;
  const callAttributionApi = attributionApi.call;
  const resetAttributionApi = attributionApi.reset;
  const attributionData = attributionApi.data;
  const attributionLoading = attributionApi.loading;
  const attributionError = attributionApi.error;
  const [scoring, setScoring] = useState<ScoringResult | null>(null);
  const [scoreTaskId, setScoreTaskId] = useState<string | null>(null);
  const [scoreState, setScoreState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [scoreProgress, setScoreProgress] = useState<UnifiedProgress | null>(null);
  const [scoreError, setScoreError] = useState<string | null>(null);

  const handleScoreEvent = useCallback((event: SSEEvent) => {
    const progress = (event.progress || event.data || {}) as UnifiedProgress;
    setScoreProgress(progress);
    const outcome = resolveJobEventState(event, progress, {
      failed: "评分失败",
      interrupted: "评分已停止，结果未确认完成。",
    });
    if (outcome.kind === "failed") {
      const message = outcome.message;
      setScoreState("error"); setScoreError(message);
      notify(outcome.notifyType, message); setScoreTaskId(null);
      return;
    }
    if (outcome.kind === "interrupted") {
      const message = outcome.message;
      setScoreState("error"); setScoreError(message);
      notify(outcome.notifyType, message); setScoreTaskId(null);
      return;
    }
    if (outcome.kind === "success") {
      const result = event.result as ScoringResult | undefined;
      if (result) setScoring(result);
      setScoreState("success"); setScoreTaskId(null);
      notify(outcome.notifyType, `${candidate?.alpha_id || "候选"} 评分已刷新`);
      return;
    }
    setScoreState("progress");
  }, [candidate?.alpha_id, notify]);

  const handleScoreStreamExhausted = useCallback(() => {
    if (!scoreTaskId) return;
    const cancelledTaskId = scoreTaskId;
    const message = "评分进度暂时不可确认，正在请求后台自动中断；取消确认前请稍后重试评分。";
    setScoreState("error"); setScoreError(message);
    setScoreProgress((c) => ({ ...(c || {}), phase: c?.phase || "scoring", status_message: message, percent_complete: 100 }));
    setScoreTaskId(null);
    void requestJobCancel({ jobId: cancelledTaskId, reason: "sse_exhausted", message }).then((result) => {
      const cancelExperience = cancelResultExperience(result, {
        confirmed: "评分进度暂时不可确认，已确认后台停止。请稍后重试评分。",
        missing: "评分监控对象已找不到，请刷新状态或稍后重试。",
        unconfirmed: "评分进度暂时不可确认，已请求后台自动中断，但取消未确认。请刷新状态或稍后重试。",
      });
      const finalMessage = cancelExperience.message;
      setScoreError(finalMessage);
      setScoreProgress((current) => ({
        ...(current || {}),
        ...cancelExperience.progressPatch,
        phase: current?.phase || "scoring",
        status_message: finalMessage,
        percent_complete: 100,
      }));
      notify(cancelExperience.notifyType, finalMessage);
    });
    notify("warning", message);
  }, [notify, scoreTaskId]);

  useSSE(scoreTaskId ? `/sse?job_id=${encodeURIComponent(scoreTaskId)}` : null, {
    onEvent: handleScoreEvent, onExhausted: handleScoreStreamExhausted,
  });

  const loadScore = useCallback(async () => {
    if (!candidate) return;
    setScoring(null); resetAttributionApi(); setScoreState("loading"); setScoreError(null);
    setScoreProgress({ phase: "scoring", status_message: `正在为 ${candidate.alpha_id || "候选"} 启动评分。` });
    const payload = candidate.alpha_id ? { alpha_id: candidate.alpha_id, candidate } : { candidate };
    const [scoreResult, attributionResult] = await Promise.all([
      callScoreApi("/api/scoring/evaluate", { method: "POST", body: JSON.stringify(payload) }),
      callAttributionApi("/api/scoring/attribution", { method: "POST", body: JSON.stringify(payload) }),
    ]);
    const nextTaskId = String(scoreResult?.task_id || scoreResult?.job_id || "");
    if (scoreResult?.ok && nextTaskId) { setScoreTaskId(nextTaskId); setScoreState("progress"); }
    else if (scoreResult?.error) {
      const message = apiErrorMessage(scoreResult, "启动评分失败");
      setScoreState("error"); setScoreError(message); notify("error", message);
    }
    if (attributionResult && !attributionResult.ok && attributionResult.error) {
      notify("error", apiErrorMessage(attributionResult, "评分归因加载失败"));
    }
  }, [callAttributionApi, callScoreApi, candidate, notify, resetAttributionApi]);

  useEffect(() => { if (candidate) loadScore(); }, [candidate?.alpha_id, loadScore]);

  const attribution = scoring?.attribution_tree || attributionData?.attribution || null;
  const hardGates = nonEmpty(scoring?.hard_gates) || nonEmpty(attributionData?.hard_gates) || [];
  const softGates = nonEmpty(scoring?.soft_gates) || nonEmpty(attributionData?.soft_gates) || [];
  const failures = nonEmpty(scoring?.top_failures) || nonEmpty(attributionData?.top_failures) || [];
  const hints = nonEmpty(scoring?.improvement_hints) || nonEmpty(attributionData?.improvement_hints) || [];
  const m = candidate?.official_metrics;
  const selfCorrelation = metricWithStatus(m?.self_correlation, m?.self_correlation_status, m?.correlation);
  const loading = scoreState === "loading" || scoreState === "progress" || attributionLoading;
  const error = scoreError || scoreApiError || attributionError;
  const lifecycleStatus = lifecycleStatusLabel(candidate?.lifecycle_status);
  const layerScores = useMemo(() => {
    const prior = Number(scoring?.prior?.score ?? candidate?.scorecard?.prior_score ?? 0);
    const empirical = Number(scoring?.empirical?.score ?? candidate?.scorecard?.empirical_score ?? 0);
    const checklist = Number(scoring?.checklist?.score ?? candidate?.scorecard?.checklist_score ?? 0);
    return { prior, empirical, checklist };
  }, [candidate?.scorecard, scoring]);

  const renderAttribution = (node: AttributionNode | null | undefined, depth = 0) => {
    if (!node) return null;
    return (
      <div style={{ marginLeft: depth > 0 ? 16 : 0, paddingLeft: depth > 0 ? 12 : 0 }} className={depth > 0 ? "border-l border-border-subtle" : ""}>
        <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 12 }}>
          <span className="text-text-secondary">{safeScoringText(node.name, "归因项待确认")}</span>
          <span className="tabular text-text-tertiary">{fmtNum(node.score, 1)} x {fmtNum(node.weight, 2)}</span>
        </div>
        {node.explanation && <p className="text-2xs text-text-tertiary pb-1">{safeScoringText(node.explanation, "说明待确认")}</p>}
        {childNodes(node).map((child) => (
          <div key={`${safeScoringText(child.name, "attribution")}-${depth}`}>{renderAttribution(child, depth + 1)}</div>
        ))}
      </div>
    );
  };

  if (!candidate) {
    return (
      <div className="panel">
        <div className="panel-body-padded">
          <h3 className="text-base font-medium text-text-primary mb-2">选择候选</h3>
          <p className="text-sm text-text-tertiary">打开候选管理，选择一个真实候选，然后点击评分。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <h1 className="text-xl font-medium text-text-primary mb-1">科学评分</h1>
      <p className="text-sm text-text-tertiary mb-4">{candidate.alpha_id} · {safeScoringText(candidate.family, "家族待确认")}</p>

      {error && (
        <div className="panel mb-4 bg-negative-subtle border-negative-subtle" role="alert">
          <div className="panel-body-padded" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <p className="text-sm text-negative">加载评分失败: {error}</p>
            <button onClick={loadScore} className="btn btn-secondary btn-sm" disabled={loading}>重试</button>
          </div>
        </div>
      )}

      <ProgressFeedback state={error ? "error" : scoreState} title="评分与验证" progress={scoreProgress} error={error} onRetry={loadScore} compact={scoreState === "idle" || scoreState === "success"} />

      {/* Expression overview + Score Hero */}
      <div className="panel mb-4">
        <div className="panel-header">
          <span>Alpha 表达式</span>
          <button onClick={loadScore} className="btn btn-ghost btn-sm" disabled={loading}>{loading ? "评分中..." : "刷新评分"}</button>
        </div>
        <div className="panel-body-padded">
          <code className="block font-mono text-xs text-text-secondary p-3 rounded-md bg-surface-2 break-all" style={{ lineHeight: 1.6 }}>
            {candidate.expression}
          </code>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", marginTop: 12, fontSize: 12 }}>
            <span className="text-text-tertiary">家族: <span className="text-text-secondary">{safeScoringText(candidate.family, "家族待确认")}</span></span>
            <span className="text-text-tertiary">状态: <span className={`badge ${scoring?.passed_gate || candidate.gate?.passed ? "badge-positive" : "badge-negative"}`}>{lifecycleStatus}</span></span>
            <span className="text-text-tertiary">ID: <span className="font-mono text-text-secondary">{candidate.alpha_id}</span></span>
          </div>
        </div>
      </div>

      {/* Score Scoreboard + Official Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* Scoreboard */}
        <div className="panel">
          <div className="panel-header"><span>评分卡</span></div>
          <div className="panel-body-padded">
            <div style={{ textAlign: "center", marginBottom: 16 }}>
              <span className="font-mono-value text-3xl text-positive" style={{ fontSize: 42, fontWeight: 500 }}>
                {fmtNum(scoring?.total_score ?? candidate.scorecard?.total_score, 1)}
              </span>
              <span className="text-text-tertiary" style={{ fontSize: 20 }}>/100</span>
            </div>
            <ScoreBar label="先验" value={layerScores.prior} max={35} />
            <ScoreBar label="实证" value={layerScores.empirical} max={40} />
            <ScoreBar label="清单" value={layerScores.checklist} max={25} />
            <div className="grid grid-cols-2 gap-2 mt-4 text-xs">
              <InfoPill label="决策" value={scoring?.decision_band || candidate.decision_band || "--"} />
              <InfoPill label="模式" value={scoring?.scoring_schema || "--"} />
              <InfoPill label="门禁" value={scoring?.passed_gate ? "通过" : "失败"} />
              <InfoPill label="API 偏差" value={fmtNum(scoring?.api_output_deviation, 4)} />
            </div>
            {attribution && (
              <div className="mt-4 pt-3 border-t border-border-subtle">
                <p className="text-xs font-medium text-text-secondary mb-2">归因分析</p>
                {renderAttribution(attribution)}
              </div>
            )}
          </div>
        </div>

        {/* Official Metrics */}
        <div className="panel">
          <div className="panel-header"><span>官方指标</span></div>
          <div className="panel-body-padded">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <MetricRow label="夏普比率" value={m?.sharpe} threshold={1.25} />
              <MetricRow label="适应度" value={m?.fitness} threshold={1.0} />
              <MetricRow label="换手率" value={m?.turnover} format="percent" />
              <MetricRow label="收益率" value={m?.returns} format="percent" />
              <MetricRow label="回撤" value={m?.drawdown} format="percent" max={0.25} />
              <MetricRow label="自相关性" value={selfCorrelation} max={0.70} />
              <MetricRow label="集中度" value={m?.weight_concentration} max={0.10} format="percent" />
            </div>
          </div>
        </div>
      </div>

      {/* Gate Checks */}
      <div className="panel mb-4">
        <div className="panel-header"><span>官方门禁检查</span></div>
        <div className="panel-body-padded">
          <GateGroup title="硬门禁" gates={hardGates} />
          <div style={{ marginTop: 16 }}>
            <GateGroup title="软门禁" gates={softGates} />
          </div>
        </div>
      </div>

      {/* Failures & Hints */}
      {(failures.length > 0 || hints.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <InsightList title="主要失败原因" items={failures} />
          <HintList title="改进建议" items={hints} />
        </div>
      )}
    </div>
  );
}

function ScoreBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 12 }}>
        <span className="text-text-tertiary">{label}</span>
        <span className="tabular text-text-tertiary">{value.toFixed(1)}/{max}</span>
      </div>
      <div className="progress-bar" role="progressbar" aria-label={`${label} score`} aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
        <div className="progress-bar-fill positive" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function InfoPill({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="bg-surface-2" style={{ padding: "8px 10px", borderRadius: 4 }}>
      <span className="text-2xs text-text-tertiary block">{label}</span>
      <span className="text-sm font-mono text-text-primary truncate block">{safeScoringText(value, "待确认")}</span>
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
          const checks: OfficialGateCheckItem[] = checkItems.length ? checkItems : [{ name: gate.gate_name, passed: gate.passed }];
          return checks.map((check, i) => (
            <div key={`${safeScoringText(gate.gate_name, "gate")}-${safeScoringText(check.name, "check")}-${i}`}
              className={check.passed ? "bg-positive-subtle border-positive-subtle" : "bg-negative-subtle border-negative-subtle"}
              style={{
                display: "flex", alignItems: "flex-start", gap: 8, padding: "8px 10px",
                borderRadius: 4, fontSize: 12, borderWidth: "0.5px", borderStyle: "solid",
              }}
            >
              <span className={check.passed ? "text-positive" : "text-negative"}>{check.passed ? "\u2713" : "\u2715"}</span>
              <div>
                <span className="font-medium">{safeScoringText(check.name, "检查项待确认")}</span>
                <p className="text-text-tertiary text-2xs">{formatGateDetail(check.actual, check.direction, check.target, check.meaning)}</p>
                <p className="text-text-tertiary text-2xs">{safeScoringText(gate.gate_name, "门禁待确认")}</p>
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
    <div className="panel">
      <div className="panel-header"><span>{title}</span></div>
      <div className="panel-body">
        {items.map((item, i) => (
          <div key={`${item.item || "failure"}-${i}`} className="text-xs px-3.5 py-2 border-b border-border-subtle last:border-0">
            <p className="text-negative font-medium">{safeScoringText(item.item, "评分项待确认")}</p>
            <p className="text-text-tertiary">{safeScoringText(item.reason || item.severity, "原因待确认")}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function HintList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="panel">
      <div className="panel-header"><span>{title}</span></div>
      <div className="panel-body">
        {items.map((item, i) => (
          <p key={`${item}-${i}`} className="text-xs text-text-secondary px-3.5 py-2 border-b border-border-subtle last:border-0">
            {safeScoringText(item, "建议待确认")}
          </p>
        ))}
      </div>
    </div>
  );
}

function formatGateDetail(actual: unknown, direction: unknown, target: unknown, fallback: unknown) {
  const parts = [actual, direction, target]
    .map((value) => safeScoringText(value, ""))
    .filter((value) => value);
  if (parts.length) return parts.join(" ");
  return safeScoringText(fallback, "--");
}

function fmtNum(value: unknown, digits: number) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : "--";
}

function lifecycleStatusLabel(value: unknown) {
  const text = String(value || "").trim();
  if (!text) return "--";
  const normalized = text.toLowerCase();
  if (LIFECYCLE_STATUS_LABELS[normalized]) return LIFECYCLE_STATUS_LABELS[normalized];
  if (isUnsafeScoringText(text) || BACKEND_STATUS_CODE_PATTERN.test(text) || SNAKE_STATUS_CODE_PATTERN.test(text)) {
    return "状态待确认";
  }
  return text;
}

function safeScoringText(value: unknown, fallback: string) {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : fallback;
  if (typeof value === "boolean") return value ? "是" : "否";
  const text = String(value).trim();
  if (!text) return fallback;
  if (isUnsafeScoringText(text)) return fallback;
  return text;
}

function isUnsafeScoringText(text: string) {
  return RAW_SCORING_TEXT_PATTERN.test(text) || BACKEND_STATUS_CODE_PATTERN.test(text);
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

function MetricRow({ label, value, threshold, max, format }: {
  label: string; value?: number | string; threshold?: number; max?: number; format?: "percent";
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
    <div className="bg-surface-2" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 8px", borderRadius: 4 }}>
      <span className="text-text-tertiary">{label}</span>
      <span className={`font-mono-value text-sm ${ok ? "text-positive" : "text-negative"}`}>{formatted}</span>
    </div>
  );
}
