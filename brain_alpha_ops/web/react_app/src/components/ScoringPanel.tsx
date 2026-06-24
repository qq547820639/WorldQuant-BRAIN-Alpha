/** Scoring visualization — Terminal Precision v2.0 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { cancelResultExperience, requestJobCancel } from "@/api/jobCancel";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { resolveJobEventState } from "@/helpers/runPayload";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import ProgressFeedback from "@/components/ProgressFeedback";
import Skeleton from "./Skeleton";
import ErrorCard from "./ErrorCard";
import EmptyState from "./EmptyState";
import type { ScoreHistoryPoint } from "@/components/ScoreBreakdown/ScoreHistory";
import type {
  AttributionNode, Candidate,
  OfficialGateResult,
  ScoringAttributionResponse, ScoringResult, SSEEvent, UnifiedProgress,
} from "@/types";
import ScoringHeader from "./ScoringPanel/Header";
import GateResults from "./ScoringPanel/GateResults";
import ImprovementHints from "./ScoringPanel/ImprovementHints";
import {
  safeScoringText, lifecycleStatusLabel, metricWithStatus, nonEmpty,
} from "./ScoringPanel/utils";

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
  const lifecycleApi = useApi<{ records?: Array<Record<string, unknown>>; items?: Array<Record<string, unknown>> }>();
  const callLifecycleApi = lifecycleApi.call;
  const [scoreHistory, setScoreHistory] = useState<ScoreHistoryPoint[] | null>(null);
  const [scoreHistoryExpanded, setScoreHistoryExpanded] = useState(false);
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
    const scorecard = candidate.scorecard;
    if (scorecard && scorecard.total_score > 0 && scorecard.attribution_tree) {
      const cachedResult: ScoringResult = {
        alpha_id: candidate.alpha_id,
        expression: candidate.expression || "",
        total_score: scorecard.total_score,
        decision_band: scorecard.decision_band || candidate.decision_band || "--",
        passed_gate: candidate.gate?.passed ?? false,
        prior: { score: scorecard.prior?.score ?? scorecard.prior_score ?? 0 },
        empirical: { score: scorecard.empirical?.score ?? scorecard.empirical_score ?? 0 },
        checklist: { score: scorecard.submission_checklist?.score ?? scorecard.checklist_score ?? 0 },
        layer_weights: scorecard.layer_weights,
        hard_gates: (scorecard.hard_gates as unknown as ScoringResult["hard_gates"]) || [],
        soft_gates: [],
        attribution_tree: scorecard.attribution_tree,
        top_failures: scorecard.top_failures || [],
        improvement_hints: scorecard.improvement_hints || [],
        score_basis: scorecard.score_basis,
        scoring_schema: "",
      };
      setScoring(cachedResult);
      setScoreState("success");
      setScoreError(null);
      setScoreProgress(null);
      setScoreTaskId(null);
      return;
    }
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

  const fetchScoreHistory = useCallback(async () => {
    if (!candidate?.alpha_id) { setScoreHistory(null); return; }
    const result = await callLifecycleApi(`/api/alpha_lifecycle?alpha_id=${encodeURIComponent(candidate.alpha_id)}`);
    if (result?.ok) {
      const records = result.records || result.items || [];
      const points: ScoreHistoryPoint[] = records
        .filter((r) => typeof r.timestamp === "string" && typeof r.total_score === "number")
        .map((r) => ({ timestamp: String(r.timestamp), totalScore: Number(r.total_score) }))
        .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
      setScoreHistory(points.length >= 2 ? points : null);
    } else {
      setScoreHistory(null);
    }
  }, [callLifecycleApi, candidate?.alpha_id]);

  useEffect(() => { void fetchScoreHistory(); }, [fetchScoreHistory]);

  const attribution = scoring?.attribution_tree || attributionData?.attribution || null;
  const hardGates = nonEmpty(scoring?.hard_gates) || nonEmpty(attributionData?.hard_gates) || [];
  const softGates = nonEmpty(scoring?.soft_gates) || nonEmpty(attributionData?.soft_gates) || [];
  const failures = nonEmpty(scoring?.top_failures) || nonEmpty(attributionData?.top_failures) || [];
  const hints = nonEmpty(scoring?.improvement_hints) || nonEmpty(attributionData?.improvement_hints) || [];
  const selfCorrelation = metricWithStatus(candidate?.official_metrics?.self_correlation, candidate?.official_metrics?.self_correlation_status, candidate?.official_metrics?.correlation);
  const loading = scoreState === "loading" || scoreState === "progress" || attributionLoading;
  const error = scoreError || scoreApiError || attributionError;
  const lifecycleStatus = lifecycleStatusLabel(candidate?.lifecycle_status);
  const layerScores = useMemo(() => {
    const prior = Number(scoring?.prior?.score ?? candidate?.scorecard?.prior_score ?? 0);
    const empirical = Number(scoring?.empirical?.score ?? candidate?.scorecard?.empirical_score ?? 0);
    const checklist = Number(scoring?.checklist?.score ?? candidate?.scorecard?.checklist_score ?? 0);
    return { prior, empirical, checklist };
  }, [candidate?.scorecard, scoring]);

  if (!candidate) {
    return (
      <div className="panel">
        <div className="panel-body-padded">
          <EmptyState
            title="选择候选"
            description="打开候选管理，选择一个真实候选，然后点击评分。"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <h1 className="text-xl font-medium text-text-primary mb-1">科学评分</h1>
      <p className="text-sm text-text-tertiary mb-4">{candidate.alpha_id} · {safeScoringText(candidate.family, "家族待确认")}</p>

      {error && (
        <div className="mb-4">
          <ErrorCard
            title="加载评分失败"
            details={error}
            severity="error"
            onRetry={loadScore}
          />
        </div>
      )}

      <ProgressFeedback state={error ? "error" : scoreState} title="评分与验证" progress={scoreProgress} error={error} onRetry={loadScore} compact={scoreState === "idle" || scoreState === "success"} />

      <ScoringHeader
        candidate={candidate}
        scoring={scoring}
        layerScores={layerScores}
        loading={loading}
        onRetry={loadScore}
        lifecycleStatus={lifecycleStatus}
        officialMetrics={candidate.official_metrics}
        attribution={attribution}
      />

      {/* P1-5: 评分历史时间线 */}
      {scoreHistory && scoreHistory.length >= 2 && (
        <div className="panel mb-4">
          <button
            type="button"
            className="panel-header"
            style={{ width: "100%", textAlign: "left", cursor: "pointer", border: "none", background: "none", font: "inherit" }}
            onClick={() => setScoreHistoryExpanded(!scoreHistoryExpanded)}
            aria-expanded={scoreHistoryExpanded}
            aria-controls="score-history-content"
            aria-label={`评分历史，共 ${scoreHistory.length} 条记录，点击${scoreHistoryExpanded ? "收起" : "展开"}`}
          >
            <span>评分历史 ({scoreHistory.length})</span>
            <span className="text-text-tertiary" style={{ fontSize: 12 }} aria-hidden="true">
              {scoreHistoryExpanded ? "▾ 收起" : "▸ 展开"}
            </span>
          </button>
          {scoreHistoryExpanded && (
            <div id="score-history-content" className="panel-body-padded" role="region" aria-label="评分历史详情">
              <div className="scorebreakdown-panel" style={{ background: "none", border: "none", padding: 0 }}>
                <div className="scorebreakdown-history" style={{ padding: 0 }}>
                  <div className="scorebreakdown-sparkline-container" style={{ marginTop: 0 }}>
                    <div
                      className="scorebreakdown-sparkline"
                      aria-label={`评分历史趋势，共 ${scoreHistory.length} 个数据点`}
                      style={{ height: 56, borderBottom: "0.5px solid var(--color-border-default)" }}
                    >
                      {(() => {
                        const points = scoreHistory.slice(-10);
                        const scores = points.map((p) => p.totalScore);
                        const minScore = Math.min(...scores);
                        const maxScore = Math.max(...scores);
                        const range = maxScore - minScore || 1;
                        const formatLabel = (ts: string): string => {
                          try {
                            const d = new Date(ts);
                            if (isNaN(d.getTime())) return ts.slice(0, 5);
                            return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
                          } catch { return ts.slice(0, 5); }
                        };
                        return points.map((point, i) => {
                          const heightPct = ((point.totalScore - minScore) / range) * 100;
                          return (
                            <div
                              key={`${point.timestamp}-${i}`}
                              style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", height: "100%" }}
                              title={`${formatLabel(point.timestamp)}: ${point.totalScore.toFixed(1)}`}
                            >
                              <div
                                style={{
                                  width: "100%", maxWidth: 24, height: `${Math.max(4, heightPct)}%`,
                                  minHeight: 2, background: "var(--color-sparkline-bar)",
                                  borderRadius: "1px 1px 0 0",
                                }}
                              />
                              <span style={{ fontSize: "0.5rem", color: "var(--color-text-muted)", marginTop: 2, textAlign: "center", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {formatLabel(point.timestamp)}
                              </span>
                            </div>
                          );
                        });
                      })()}
                    </div>
                    <div style={{ marginTop: 8, paddingTop: 6, borderTop: "0.5px solid var(--color-border-default)" }}>
                      {scoreHistory.slice().reverse().slice(0, 10).map((point, i) => (
                        <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "2px 0", fontSize: "0.625rem" }}>
                          <span style={{ color: "var(--color-text-muted)", fontFamily: "monospace" }}>
                            {(() => {
                              try {
                                const d = new Date(point.timestamp);
                                if (isNaN(d.getTime())) return point.timestamp.slice(0, 10);
                                return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
                              } catch { return point.timestamp.slice(0, 10); }
                            })()}
                          </span>
                          <span style={{ color: "var(--color-score-highlight)", fontFamily: "monospace" }}>{point.totalScore.toFixed(1)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      <GateResults hardGates={hardGates} softGates={softGates} />

      <ImprovementHints failures={failures} hints={hints} />
    </div>
  );
}
