/** Job monitor using SSE for real-time status updates. */

import { useState, useEffect, useCallback } from "react";
import { useSSE } from "@/hooks/useSSE";
import { useApi } from "@/hooks/useApi";
import type { BrainCredentials, JobStatus, SSEEvent } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials?: BrainCredentials;
  onNeedCredentials?: () => void;
}

export default function JobMonitor({ notify, credentials, onNeedCredentials }: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<string[]>([]);
  const [progressError, setProgressError] = useState<string | null>(null);
  const api = useApi();

  const handleSSEEvent = useCallback((event: SSEEvent) => {
    if (event.type === "progress") {
      setStatus((prev) => ({
        ...(prev || { job_id: event.job_id || event.task_id || "", status: "running" }),
        job_id: event.job_id || event.task_id || prev?.job_id || "",
        task_id: event.task_id || event.job_id || prev?.task_id,
        status: "running",
        phase: event.phase || event.progress?.phase || prev?.phase,
        percent_complete: event.percent_complete,
        eta_seconds: event.eta_seconds,
        status_message: event.status_message,
        progress: event.progress || (event.data as JobStatus["progress"]),
      }));
    } else if (event.type === "complete") {
      setRunning(false);
      notify("success", "任务已完成");
      setEvents((prev) => [...prev, "任务完成"]);
      setStatus((prev) => prev ? { ...prev, status: "completed", result: event.result, progress: event.progress || prev.progress } : prev);
    } else if (event.type === "error") {
      setRunning(false);
      setProgressError(String(event.error || event.data?.error || "任务错误"));
      notify("error", String(event.error || event.data?.error || "任务错误"));
      setEvents((prev) => [...prev, `错误: ${event.error || event.data?.error || "任务错误"}`]);
    } else if (event.type === "candidate") {
      setEvents((prev) => {
        const msg = `候选 ${(event.data as Record<string, unknown>)?.alpha_id || "?"} 得分 ${(event.data as Record<string, unknown>)?.score || 0}`;
        return [...prev.slice(-50), msg];
      });
    } else if (event.type === "submission") {
      notify("warning", `检测到提交事件: ${(event.data as Record<string, unknown>)?.alpha_id || "未知"}`);
      setEvents((prev) => [...prev.slice(-50), `提交事件 ${(event.data as Record<string, unknown>)?.alpha_id || "?"}`]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notify]);

  const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;
  const handleStreamExhausted = useCallback(() => {
    notify("warning", "实时状态流已断开，已保留轮询刷新。");
    setEvents((prev) => [...prev.slice(-50), "实时状态流断开，已切换轮询"]);
  }, [notify]);

  const { connected } = useSSE(sseUrl, { onEvent: handleSSEEvent, onExhausted: handleStreamExhausted });

  const startJob = useCallback(async (resume = false) => {
    if (!hasCredentials(credentials)) {
      notify("info", "未填写页面凭证，将使用服务端环境变量启动非提交验证。");
    }
    setRunning(true);
    setProgressError(null);
    setStatus({
      job_id: "",
      task_id: "",
      status: "running",
      phase: "queued",
      progress: { phase: "queued", status_message: "正在启动非提交流水线验证。", percent_complete: 0 },
    });
    const result = await api.call<{ job_id: string }>("/api/run", {
      method: "POST",
      body: JSON.stringify(runPayload(resume, credentials)),
    });
    const jid = String((result as unknown as { job_id?: string; task_id?: string } | null)?.job_id || (result as unknown as { task_id?: string } | null)?.task_id || "");
    if (result?.ok && jid) {
      setJobId(jid);
      setRunning(true);
      setProgressError(null);
      setStatus({
        job_id: jid,
        task_id: jid,
        status: "running",
        phase: "queued",
        progress: { phase: "queued", status_message: "非提交流水线已排队。", percent_complete: 0 },
      });
      notify("info", `${resume ? "非提交续跑" : "非提交任务"}已启动: ${jid}`);
    } else {
      setRunning(false);
      const message = result?.error || "启动任务失败";
      setProgressError(message);
      setStatus((prev) => prev ? { ...prev, status: "failed", error: message, progress: { ...(prev.progress || {}), phase: "failed", status_message: message, percent_complete: 100 } } : prev);
      notify("error", message);
    }
  }, [api, credentials, notify]);

  const stopJob = useCallback(async () => {
    if (!jobId) return;
    const stoppedJobId = jobId;
    const result = await api.call("/api/stop", { method: "POST", body: JSON.stringify({ job_id: stoppedJobId }) });
    setRunning(false);
    const message = result?.ok === false ? (result.error || "停止请求失败") : "停止请求已发送";
    setStatus((prev) => ({
      ...(prev || { job_id: stoppedJobId, task_id: stoppedJobId, status: "stopped" }),
      job_id: stoppedJobId,
      task_id: stoppedJobId,
      status: result?.ok === false ? "failed" : "stopped",
      phase: result?.ok === false ? "failed" : "stopped",
      error: result?.ok === false ? message : prev?.error,
      progress: {
        ...(prev?.progress || {}),
        phase: result?.ok === false ? "failed" : "stopped",
        status_message: result?.ok === false ? message : "任务已停止，非提交证据已保留。",
        percent_complete: result?.ok === false ? 100 : prev?.progress?.percent_complete,
      },
    }));
    setProgressError(result?.ok === false ? message : null);
    setEvents((prev) => [...prev.slice(-50), result?.ok === false ? `停止失败: ${message}` : "停止请求已发送"]);
    notify(result?.ok === false ? "error" : "info", result?.ok === false ? message : "任务已停止");
  }, [api, jobId, notify]);

  useEffect(() => {
    if (!running || !jobId) return;
    const interval = setInterval(async () => {
      const result = await api.call<JobStatus>(`/api/status?job_id=${encodeURIComponent(jobId)}`);
      if (result?.ok) {
        setStatus(result as unknown as JobStatus);
      } else if (result) {
        const message = result.error || result.error_code || "状态刷新失败";
        setProgressError(`状态刷新失败: ${message}`);
        setEvents((prev) => [...prev.slice(-50), `状态刷新失败: ${message}`]);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [running, jobId, api]);

  const cycleProgress = status?.cycle && status?.max_cycles
    ? Math.round((status.cycle / status.max_cycles) * 100)
    : 0;
  const progress = status?.progress || {
    phase: status?.phase,
    percent_complete: status?.percent_complete ?? cycleProgress,
    eta_seconds: status?.eta_seconds,
    status_message: status?.status_message,
  };
  const summary = productionSummary(status);
  const hasEvidence = Boolean(status?.job_id || jobId);
  const credentialSource = hasCredentials(credentials) ? "页面凭证" : "服务端环境变量";

  return (
    <div className="workflow-panel min-w-0 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="badge badge-info">Step 2</span>
            <span className="badge badge-neutral">autoSubmit=false</span>
            <span className="badge badge-neutral">{credentialSource}</span>
          </div>
          <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">非提交生产验证</h3>
          <p className="mt-2 text-base leading-7 text-slate-700">
            启动真实生产链路的本地任务，但请求体和后端队列都会强制关闭自动提交。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-success" : "bg-danger"}`} aria-hidden="true" />
          <span className={`badge ${running ? "badge-success" : "badge-neutral"}`} role="status" aria-label={`流水线${running ? "运行中" : "空闲"}`}>
            {running ? "运行中" : "空闲"}
          </span>
        </div>
      </div>

      <div className="workflow-note min-w-0">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold text-slate-950">运行证明</span>
          <span className="rounded border border-slate-200 bg-white px-2 py-1 font-mono text-xs text-slate-600">{status?.job_id || jobId || "尚未启动"}</span>
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <ProofMetric label="官方验证" value={hasEvidence ? `${summary.officialValidationPassed}/${summary.officialValidationAttempted}` : "-"} />
          <ProofMetric label="官方回测" value={hasEvidence ? String(summary.officiallySimulated || summary.backtestsSubmitted) : "-"} />
          <ProofMetric label="本轮提交" value={hasEvidence ? String(summary.submittedThisRun) : "-"} tone={summary.submittedThisRun > 0 ? "danger" : "success"} />
          <ProofMetric label="自动提交" value={hasEvidence ? String(summary.autoSubmitted) : "0"} tone={summary.autoSubmitted > 0 ? "danger" : "success"} />
        </dl>
        {status?.progress?.status_message && (
          <p className="mt-3 text-sm leading-6 text-slate-700" role="status" aria-live="polite">
            {status.progress.status_message}
          </p>
        )}
        <ul className="mt-3 grid gap-2 text-sm leading-6 text-slate-700 sm:grid-cols-2">
          <li>请求强制携带 autoSubmit=false 与 auto_submit=false</li>
          <li>账号、密码和 token 不进入 job 元数据</li>
          <li>提交计数必须保持 0 才算非提交证明通过</li>
          <li>运行完成后用 job_id 回看状态与历史证据</li>
        </ul>
      </div>

      {(running || api.loading) && (
        <div className="space-y-3">
          <ProgressFeedback
            state={progressError ? "error" : "progress"}
            title="流水线进度"
            progress={progress}
            error={progressError}
            compact
          />
          <div className="grid grid-cols-1 gap-3 text-xs text-muted sm:grid-cols-2">
            <span>轮次: {status?.cycle ?? 0}/{status?.max_cycles ?? 0}</span>
            <span>阶段: {status?.phase ?? "-"}</span>
            <span>候选数: {status?.progress?.candidates_generated ?? 0}</span>
            <span>回测数: {status?.progress?.backtests_completed ?? 0}</span>
          </div>
        </div>
      )}

      {!running && progressError && (
        <ProgressFeedback
          state="error"
          title="流水线进度"
          progress={status?.progress}
          error={progressError}
          onRetry={() => startJob(false)}
          compact
        />
      )}

      {!hasCredentials(credentials) && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900" role="status" aria-live="polite">
          页面凭证为空。可以先填写并测试 BRAIN 账户，也可以继续使用服务端环境变量运行。
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {onNeedCredentials && !hasCredentials(credentials) && (
          <button type="button" onClick={onNeedCredentials} disabled={running} className="btn-secondary text-sm">
            填写 BRAIN 凭证
          </button>
        )}
        <button onClick={() => startJob(false)} disabled={running} className="btn-primary text-sm">
          <PlayIcon /> 运行非提交验证
        </button>
        <button onClick={() => startJob(true)} disabled={running} className="btn-secondary text-sm">
          <ResumeIcon /> 续跑非提交断点
        </button>
        <button onClick={stopJob} disabled={!running} className="btn-secondary text-sm">
          <StopIcon /> 停止
        </button>
      </div>

      {events.length > 0 && (
        <div className="max-h-40 min-w-0 overflow-y-auto rounded-lg border border-slate-200 bg-white p-3 font-mono text-sm leading-6 text-slate-700" role="log" aria-live="polite" aria-label="流水线事件日志">
          {events.map((e, i) => (
            <div key={i}>{e}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function hasCredentials(credentials?: BrainCredentials) {
  return Boolean(credentials?.username.trim() || credentials?.password || credentials?.token.trim());
}

function runPayload(resume: boolean, credentials?: BrainCredentials) {
  const payload: Record<string, string | boolean> = resume
    ? { resume: true, autoSubmit: false, auto_submit: false }
    : { autoSubmit: false, auto_submit: false };
  const username = credentials?.username.trim() || "";
  const password = credentials?.password || "";
  const token = credentials?.token.trim() || "";
  if (username) payload.username = username;
  if (password) payload.password = password;
  if (token) payload.token = token;
  return payload;
}

function ProofMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "success" | "danger" }) {
  const color = tone === "success" ? "text-emerald-700" : tone === "danger" ? "text-danger" : "text-slate-950";
  return (
    <div className="min-w-0 rounded-lg border border-slate-200 bg-white p-3">
      <dt className="text-xs leading-5 text-slate-600">{label}</dt>
      <dd className={`mt-1 break-words text-lg font-semibold tabular-nums ${color}`}>{value}</dd>
    </div>
  );
}

function productionSummary(status: JobStatus | null) {
  const result = asRecord(status?.result);
  const resultSummary = asRecord(result?.summary);
  const progressData = asRecord(status?.progress?.data);
  return {
    officialValidationAttempted: firstNumber(resultSummary?.official_validation_attempted, progressData?.official_validation_attempted),
    officialValidationPassed: firstNumber(resultSummary?.official_validation_passed, progressData?.official_validation_passed),
    officiallySimulated: firstNumber(resultSummary?.officially_simulated, progressData?.officially_simulated),
    backtestsSubmitted: firstNumber(resultSummary?.backtests_submitted, progressData?.backtests_submitted),
    submittedThisRun: firstNumber(resultSummary?.submitted_this_run, progressData?.submitted_this_run),
    autoSubmitted: firstNumber(resultSummary?.auto_submitted, progressData?.auto_submitted),
  };
}

function firstNumber(...values: unknown[]) {
  for (const value of values) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function PlayIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" className="shrink-0">
      <path d="M8 5v14l11-7L8 5Z" fill="currentColor" />
    </svg>
  );
}

function ResumeIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 3v6h6" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" className="shrink-0">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}
