/** Job monitor with SSE — Terminal Precision v2.0 */
import { useState, useEffect, useCallback, useRef } from "react";
import { requestJobCancel, type CancelReason } from "@/api/jobCancel";
import { useSSE } from "@/hooks/useSSE";
import { useApi } from "@/hooks/useApi";
import { buildRunPayload, hasCredentials, isTerminalStatus, shortValidationId } from "@/helpers/runPayload";
import type { BrainCredentials, JobStatus, SSEEvent, UnifiedProgress } from "@/types";
import type { JobState } from "@/hooks/useJobState";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials?: BrainCredentials;
  onNeedCredentials?: () => void;
  jobState?: JobState;
}

// ── Shared view props ───────────────────────────────────────────────────────

interface ViewProps {
  credentialSource: string;
  validationId: string | null;
  running: boolean;
  connected: boolean;
  progress: UnifiedProgress | null;
  error: string | null;
  status: JobStatus | null;
  events: string[];
  loading?: boolean;
  showCredentialWarning: boolean;
  reconnectAttempts?: number;
  onStart: () => void;
  onResume: () => void;
  onStop: () => void;
  onCredentialClick?: () => void;
  onRetry?: () => void;
}

/** Single view component — shared between controlled and standalone modes */
function JobMonitorView({
  credentialSource, validationId, running, connected, progress, error, status, events,
  loading, showCredentialWarning, reconnectAttempts = 0,
  onStart, onResume, onStop, onCredentialClick, onRetry,
}: ViewProps) {
  const summary = productionSummary(status);
  const hasEvidence = Boolean(status?.job_id || validationId);

  return (
    <div className="panel mb-4">
      <div className="panel-header">
        <span>非提交生产验证</span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="badge badge-neutral">非提交</span>
          <span className="badge badge-neutral">{credentialSource}</span>
          <span className={`status-dot ${connected ? "status-dot-active" : "status-dot-error"}`} />
          <span className={`badge ${running ? "badge-positive" : "badge-neutral"}`}>
            {running ? "运行中" : "空闲"}
          </span>
        </div>
      </div>
      <div className="panel-body-padded">
        {/* SSE disconnect warning banner */}
        {running && !connected && (
          <div className="mb-3" style={{
            padding: "8px 12px", borderRadius: 6,
            border: "1px solid", borderColor: "oklch(0.58 0.10 65 / 0.30)",
            background: "oklch(0.58 0.06 65 / 0.10)",
            display: "flex", alignItems: "center", gap: 8,
            fontSize: 13, color: "oklch(0.68 0.12 65)",
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ flexShrink: 0 }}>
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <span>
              实时连接已断开{reconnectAttempts > 0 ? `（第 ${reconnectAttempts} 次重连中…）` : "，正在重连…"}后台任务继续运行。
            </span>
          </div>
        )}
        <p className="text-sm text-text-secondary mb-4">
          生产配置下的非提交验证流程，系统会强制关闭自动提交并保留可回看的进度证据。
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <ProofMetric label="官方验证" value={hasEvidence ? `${summary.officialValidationPassed}/${summary.officialValidationAttempted}` : "--"} />
          <ProofMetric label="官方回测" value={hasEvidence ? String(summary.officiallySimulated) : "--"} />
          <ProofMetric label="本轮真实提交（应为 0）" value={hasEvidence ? String(summary.submittedThisRun) : "--"} tone={summary.submittedThisRun > 0 ? "danger" : "success"} />
          <ProofMetric label="自动提交" value={hasEvidence ? String(summary.autoSubmitted) : "0"} tone={summary.autoSubmitted > 0 ? "danger" : "success"} />
        </div>

        {validationId && (
          <div className="flex items-center gap-2 mb-4 text-xs">
            <span className="text-text-tertiary">验证编号</span>
            <span className="font-mono-value px-2 py-0.5 rounded-sm bg-surface-2 text-text-secondary">{shortValidationId(validationId)}</span>
          </div>
        )}

        {(running || loading) && (
          <div className="mb-4">
            <ProgressFeedback state={error ? "error" : "progress"} title="流水线进度" progress={progress} error={error} compact />
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-text-tertiary mt-2">
              <span>轮次: {status?.cycle ?? 0}/{status?.max_cycles ?? 0}</span>
              <span>阶段: {status?.phase ?? "--"}</span>
              <span>候选数: {status?.progress?.candidates_generated ?? 0}</span>
              <span>回测数: {status?.progress?.backtests_completed ?? 0}</span>
            </div>
          </div>
        )}

        {!running && error && onRetry && (
          <div className="mb-4">
            <ProgressFeedback state="error" title="流水线进度" progress={status?.progress} error={error} onRetry={onRetry} compact />
          </div>
        )}

        {showCredentialWarning && (
          <div className="mb-4 px-3 py-2 text-sm rounded-md bg-warning-subtle text-warning">
            页面凭证为空。可以先填写并测试 BRAIN 账户，也可以继续使用维护者配置的托管凭证运行。
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {onCredentialClick && showCredentialWarning && (
            <button type="button" onClick={onCredentialClick} disabled={running} className="btn btn-secondary btn-sm">填写凭证</button>
          )}
          <button onClick={onStart} disabled={running} className="btn btn-primary btn-sm">
            <PlayIcon /> 运行非提交验证
          </button>
          <button onClick={onResume} disabled={running} className="btn btn-secondary btn-sm">
            <ResumeIcon /> 继续上次验证
          </button>
          <button onClick={onStop} disabled={!running} className="btn btn-secondary btn-sm">
            <StopIcon /> 停止
          </button>
        </div>

        {events.length > 0 && (
          <div className="mt-3 panel" style={{ maxHeight: 160, overflow: "auto" }}>
            <div className="panel-body-padded p-2">
              {events.map((e, i) => (
                <div key={i} className="flex gap-2 text-sm py-1 border-b border-border-subtle last:border-0 text-text-secondary">
                  <span className="status-dot status-dot-active mt-1.5 shrink-0" />
                  <span className="min-w-0 break-words">{e}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────────────────

export default function JobMonitor({ notify, credentials, onNeedCredentials, jobState: external }: Props) {
  // Controlled mode: delegate to external state
  if (external) {
    return (
      <JobMonitorView
        credentialSource={hasCredentials(credentials) ? "页面凭证" : "托管凭证"}
        validationId={external.jobId}
        running={external.running}
        connected={external.connected}
        progress={external.progress}
        error={external.error}
        status={external.status}
        events={external.events}
        showCredentialWarning={!hasCredentials(credentials)}
        onStart={() => external.startJob(false)}
        onResume={() => external.startJob(true)}
        onStop={external.stopJob}
        onCredentialClick={onNeedCredentials}
        onRetry={external.error ? () => external.startJob(false) : undefined}
        reconnectAttempts={external.reconnectAttempts}
      />
    );
  }

  // ── Standalone mode (backward compat) ──
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<string[]>([]);
  const [progressError, setProgressError] = useState<string | null>(null);
  const [pollFailures, setPollFailures] = useState(0);
  const autoCancelRequests = useRef<Set<string>>(new Set());
  const api = useApi();

  const failMonitor = useCallback((message: string, phase = "watchdog_failed") => {
    setRunning(false);
    setProgressError(message);
    setStatus((prev) => prev ? {
      ...prev, status: "failed", phase, error: message,
      progress: { ...(prev.progress || {}), phase, status_message: message, percent_complete: 100 },
    } : prev);
    setEvents((prev) => [...prev.slice(-50), message]);
  }, []);

  const cancelAmbiguousJob = useCallback(async (reason: CancelReason, message: string, targetJobId?: string | null) => {
    const id = targetJobId || jobId || status?.job_id;
    if (!id) return null;
    const key = `${id}:${reason}`;
    if (autoCancelRequests.current.has(key)) return null;
    autoCancelRequests.current.add(key);
    const result = await requestJobCancel({ jobId: id, reason, message });
    setEvents((prev) => [...prev.slice(-50), result?.ok === false ? "自动中断请求未确认" : "已安全停止状态不明确的流程。"]);
    return result;
  }, [jobId, status?.job_id]);

  const handleSSEEvent = useCallback((event: SSEEvent) => {
    if (event.type === "progress") {
      setPollFailures(0);
      setStatus((prev) => ({
        ...(prev || { job_id: event.job_id || event.task_id || "", status: "running" }),
        job_id: event.job_id || event.task_id || prev?.job_id || "",
        task_id: event.task_id || event.job_id || prev?.task_id,
        status: "running", phase: event.phase || event.progress?.phase || prev?.phase,
        percent_complete: event.percent_complete, eta_seconds: event.eta_seconds,
        status_message: event.status_message,
        progress: event.progress || (event.data as JobStatus["progress"]),
      }));
    } else if (event.type === "complete") {
      setRunning(false); setPollFailures(0);
      notify("success", "验证流程已完成");
      setEvents((prev) => [...prev, "验证流程完成"]);
      setStatus((prev) => prev ? { ...prev, status: "completed", result: event.result, progress: event.progress || prev.progress } : prev);
    } else if (event.type === "error") {
      setRunning(false); setPollFailures(0);
      setProgressError(String(event.error || event.data?.error || "验证流程错误"));
      notify("error", String(event.error || event.data?.error || "验证流程错误"));
      setEvents((prev) => [...prev, `错误: ${event.error || event.data?.error || "验证流程错误"}`]);
    } else if (event.type === "candidate") {
      setEvents((prev) => [...prev.slice(-50), `候选 ${(event.data as Record<string, unknown>)?.alpha_id || "?"} 得分 ${(event.data as Record<string, unknown>)?.score || 0}`]);
    } else if (event.type === "submission") {
      notify("warning", `检测到真实提交安全事件: ${(event.data as Record<string, unknown>)?.alpha_id || "未知"}`);
      setEvents((prev) => [...prev.slice(-50), `真实提交安全事件 ${(event.data as Record<string, unknown>)?.alpha_id || "?"}`]);
    }
  }, [notify]);

  const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;
  const handleStreamExhausted = useCallback(() => {
    const msg = "页面暂时收不到最新进度，系统已安全停止本次验证。";
    notify("warning", msg);
    failMonitor(msg);
    void cancelAmbiguousJob("sse_exhausted", msg);
  }, [cancelAmbiguousJob, failMonitor, notify]);

  const { connected, reconnectAttempts } = useSSE(sseUrl, { onEvent: handleSSEEvent, onExhausted: handleStreamExhausted });

  const startJob = useCallback(async (resume = false) => {
    if (!hasCredentials(credentials)) notify("info", "未填写页面凭证，将使用维护者配置的托管凭证启动非提交验证。");
    setRunning(true); autoCancelRequests.current.clear(); setPollFailures(0); setProgressError(null);
    setStatus({ job_id: "", task_id: "", status: "running", phase: "queued", progress: { phase: "queued", status_message: "正在启动非提交流水线验证。", percent_complete: 0 } });
    const result = await api.call<{ job_id: string }>("/api/run", { method: "POST", body: JSON.stringify(buildRunPayload(resume, credentials)) });
    const jid = String(result?.job_id || "");
    if (result?.ok && jid) {
      setJobId(jid); setRunning(true); setPollFailures(0); setProgressError(null);
      setStatus({ job_id: jid, task_id: jid, status: "running", phase: "queued", progress: { phase: "queued", status_message: "非提交流水线已排队。", percent_complete: 0 } });
      notify("info", `${resume ? "非提交续跑" : "非提交验证"}已启动`);
    } else {
      setRunning(false); setPollFailures(0);
      const message = result?.error || (!result ? "网络错误，请检查连接后重试" : "启动验证流程失败");
      setProgressError(message);
      setStatus((prev) => prev ? { ...prev, status: "failed", error: message, progress: { ...(prev.progress || {}), phase: "failed", status_message: message, percent_complete: 100 } } : prev);
      notify("error", message);
      setJobId(null);
    }
  }, [api, credentials, notify]);

  const stopJob = useCallback(async () => {
    if (!jobId) return;
    const stoppedJobId = jobId;
    const result = await api.call("/api/production-validation/stop", { method: "POST", body: JSON.stringify({ job_id: stoppedJobId }) });
    setRunning(false);
    const message = result?.ok === false ? (result.error || "停止请求失败") : "停止请求已发送";
    setStatus((prev) => ({
      ...(prev || {}), job_id: stoppedJobId,
      status: result?.ok === false ? "failed" : "stopped",
      progress: { ...(prev?.progress || {}), phase: "stopped", status_message: "验证流程已停止", percent_complete: prev?.progress?.percent_complete },
    }));
    setProgressError(result?.ok === false ? message : null);
    setEvents((prev) => [...prev.slice(-50), result?.ok === false ? `停止失败: ${message}` : "停止请求已发送"]);
    notify(result?.ok === false ? "error" : "info", result?.ok === false ? message : "验证流程已停止");
  }, [api, jobId, notify]);

  const recordStatusRefreshFailure = useCallback((message: string) => {
    setPollFailures((previous) => {
      const next = previous + 1;
      if (next >= 3) {
        const failure = `状态连续刷新失败，系统已安全停止本次验证: ${message}`;
        failMonitor(failure);
        void cancelAmbiguousJob("status_failed", failure);
        notify("error", failure);
      } else {
        setProgressError(`状态刷新失败: ${message}`);
        setEvents((prev) => [...prev.slice(-50), `状态刷新失败: ${message}`]);
      }
      return next;
    });
  }, [cancelAmbiguousJob, failMonitor, notify]);

  useEffect(() => {
    if (!running || !jobId) return;
    const interval = setInterval(async () => {
      const result = await api.call<JobStatus>(`/api/production-validation/status?job_id=${encodeURIComponent(jobId)}`);
      if (result?.status && isTerminalStatus(result.status)) {
        setStatus(result); setPollFailures(0); setRunning(false);
        if (result.status === "failed") {
          const msg = result.error || result.progress?.status_message || "验证流程失败。";
          setProgressError(msg); setEvents((prev) => [...prev.slice(-50), `验证流程失败: ${msg}`]);
          if (result.phase === "watchdog_failed" || result.progress?.phase === "watchdog_failed") void cancelAmbiguousJob("watchdog_failed", msg, result.job_id || jobId);
          notify("error", msg);
        }
        setJobId(null);
      } else if (result?.ok) {
        setStatus(result); setPollFailures(0);
      } else if (result) {
        recordStatusRefreshFailure(result.error || result.error_code || "状态刷新失败");
      } else {
        recordStatusRefreshFailure("状态刷新失败或网络中断");
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [running, jobId, api, cancelAmbiguousJob, failMonitor, notify, recordStatusRefreshFailure]);

  const cycleProgress = status?.cycle && status?.max_cycles ? Math.round((status.cycle / status.max_cycles) * 100) : 0;
  const progress = status?.progress || { phase: status?.phase, percent_complete: status?.percent_complete ?? cycleProgress, eta_seconds: status?.eta_seconds, status_message: status?.status_message };

  return (
    <JobMonitorView
      credentialSource={hasCredentials(credentials) ? "页面凭证" : "托管凭证"}
      validationId={status?.job_id || jobId}
      running={running}
      connected={connected}
      progress={progress}
      error={progressError}
      status={status}
      events={events}
      loading={api.loading}
      showCredentialWarning={!hasCredentials(credentials)}
      onStart={() => startJob(false)}
      onResume={() => startJob(true)}
      onStop={stopJob}
      onCredentialClick={onNeedCredentials}
      onRetry={progressError ? () => startJob(false) : undefined}
      reconnectAttempts={reconnectAttempts}
    />
  );
}

// ── Shared helpers ──────────────────────────────────────────────────────────

function ProofMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "success" | "danger" }) {
  const colorClass = tone === "success" ? "text-positive" : tone === "danger" ? "text-negative" : "text-text-primary";
  return <div className="kpi-card"><p className="kpi-card-label">{label}</p><p className={`font-mono-value text-lg font-medium ${colorClass}`}>{value}</p></div>;
}

function productionSummary(status: JobStatus | null) {
  const result = asRecord(status?.result);
  const rs = asRecord(result?.summary);
  const pd = asRecord(status?.progress?.data);
  return {
    officialValidationAttempted: firstNum(rs?.official_validation_attempted, pd?.official_validation_attempted),
    officialValidationPassed: firstNum(rs?.official_validation_passed, pd?.official_validation_passed),
    officiallySimulated: firstNum(rs?.officially_simulated, pd?.officially_simulated),
    backtestsSubmitted: firstNum(rs?.backtests_submitted, pd?.backtests_submitted),
    submittedThisRun: firstNum(rs?.submitted_this_run, pd?.submitted_this_run),
    autoSubmitted: firstNum(rs?.auto_submitted, pd?.auto_submitted),
  };
}

function firstNum(...values: unknown[]) {
  for (const v of values) { const n = Number(v); if (Number.isFinite(n)) return n; }
  return 0;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function PlayIcon() { return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7L8 5Z"/></svg>; }
function ResumeIcon() { return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v6h6"/></svg>; }
function StopIcon() { return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>; }
