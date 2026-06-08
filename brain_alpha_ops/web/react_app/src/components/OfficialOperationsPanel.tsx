/** Button-driven official operations panel for browser-only user workflows. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useApi } from "@/hooks/useApi";
import type { BrainCredentials, JobStatus, SubmitReadinessResponse, UnifiedProgress } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials?: BrainCredentials;
}

interface CheckResultsResponse {
  items?: Array<Record<string, unknown>>;
  checks?: Array<Record<string, unknown>>;
  count?: number;
  ok?: boolean;
  data?: CheckResultsResponse;
}

interface OperationLogEntry {
  time: string;
  tone: "info" | "success" | "warning" | "error";
  message: string;
}

type OperationMode = "idle" | "context_refresh" | "readiness" | "checks";
type OverviewTone = "success" | "warning" | "neutral";

const POLL_INTERVAL_MS = 2000;
const SYNC_STATUS_FAILURE_LIMIT = 3;
const OPERATION_REQUEST_TIMEOUT_MS = 10000;
const MAX_LOG_ROWS = 80;

export default function OfficialOperationsPanel({ notify, credentials }: Props) {
  const [mode, setMode] = useState<OperationMode>("idle");
  const [syncJobId, setSyncJobId] = useState("");
  const [syncStatus, setSyncStatus] = useState<JobStatus | null>(null);
  const [syncRunning, setSyncRunning] = useState(false);
  const syncPollInFlightRef = useRef(false);
  const syncPollFailureCountRef = useRef(0);
  const [logs, setLogs] = useState<OperationLogEntry[]>([
    {
      time: formatClock(),
      tone: "info",
      message: "官方操作已就绪。请选择要执行的操作。",
    },
  ]);

  const syncStartApi = useApi<{ job_id?: string; task_id?: string; status_url?: string }>();
  const syncStatusApi = useApi<JobStatus>();
  const syncCancelApi = useApi();
  const readinessApi = useApi<SubmitReadinessResponse>();
  const checkResultsApi = useApi<CheckResultsResponse>();
  const callSyncStart = syncStartApi.call;
  const callSyncStatus = syncStatusApi.call;
  const callSyncCancel = syncCancelApi.call;
  const callReadiness = readinessApi.call;
  const callCheckResults = checkResultsApi.call;

  const appendLog = useCallback((tone: OperationLogEntry["tone"], message: string) => {
    setLogs((previous) => [...previous.slice(-(MAX_LOG_ROWS - 1)), { time: formatClock(), tone, message }]);
  }, []);

  const loadReadiness = useCallback(async () => {
    setMode("readiness");
    appendLog("info", "正在读取提交前阻断复核证据。");
    const deadline = requestDeadline();
    try {
      const result = await callReadiness<SubmitReadinessResponse>("/api/submit_readiness", { signal: deadline.signal });
      if (!result?.ok) {
        const message = operationFailureMessage(result?.error || result?.error_code, "提交前阻断复核证据读取失败。请重试；若连续失败，请重新打开页面或联系维护者。");
        appendLog("error", message);
        notify("error", message);
        return;
      }
      const ready = Boolean((result as SubmitReadinessResponse).ready_to_submit);
      appendLog(ready ? "success" : "warning", ready ? "已检测到可进入人工复核的候选证据。" : "当前仍未达到提交前阻断复核通过标准。");
      notify(ready ? "success" : "warning", ready ? "阻断复核通过" : "阻断复核仍未通过");
    } finally {
      deadline.clear();
    }
  }, [appendLog, callReadiness, notify]);

  const loadChecks = useCallback(async () => {
    setMode("checks");
    appendLog("info", "正在读取质量检查结果。");
    const deadline = requestDeadline();
    try {
      const result = await callCheckResults<CheckResultsResponse>("/api/check_results", { signal: deadline.signal });
      if (!result?.ok) {
        const message = operationFailureMessage(result?.error || result?.error_code, "质量检查结果读取失败。请重试；若连续失败，请重新打开页面或联系维护者。");
        appendLog("error", message);
        notify("error", message);
        return;
      }
      appendLog("success", `质量检查结果已加载: ${checkResultCount(result)} 条。`);
      notify("success", "质量检查结果已加载");
    } finally {
      deadline.clear();
    }
  }, [appendLog, callCheckResults, notify]);

  const startOfficialContextRefresh = useCallback(async () => {
    setMode("context_refresh");
    setSyncRunning(true);
    syncPollFailureCountRef.current = 0;
    setSyncStatus({
      job_id: "",
      task_id: "",
      status: "queued",
      phase: "queued",
      progress: {
        phase: "queued",
        phase_label: "等待启动",
        status_message: "官方上下文刷新正在排队。",
        percent_complete: 0,
      },
    });
    appendLog("info", "已发送官方上下文刷新请求。");
    const result = await callSyncStart<{ job_id?: string; task_id?: string; status_url?: string }>("/api/sync_alphas", {
      method: "POST",
      body: JSON.stringify({
        syncRange: "3d",
        refreshOfficialContext: true,
        userFacingOperation: "official_operations_context_refresh",
        ...credentialsPayload(credentials),
      }),
    });
    const jobId = String(result?.job_id || result?.task_id || "");
    if (!result?.ok || !jobId) {
      const message = operationFailureMessage(result?.error || result?.error_code, "官方上下文刷新启动失败。请重试；若连续失败，请重新打开页面或联系维护者。");
      setSyncRunning(false);
      setSyncStatus((previous) => ({
        ...(previous || { job_id: "", status: "failed" }),
        status: "failed",
        phase: "failed",
        error: message,
        progress: {
          ...(previous?.progress || {}),
          phase: "failed",
          status_message: message,
          percent_complete: 100,
        },
      }));
      appendLog("error", message);
      notify("error", message);
      return;
    }
    setSyncJobId(jobId);
    setSyncStatus({
      job_id: jobId,
      task_id: jobId,
      status: "queued",
      phase: "queued",
      progress: {
        job_id: jobId,
        task_id: jobId,
        phase: "queued",
        phase_label: "已排队",
        status_message: "官方上下文刷新已排队，正在等待页面进度更新。",
        percent_complete: 0,
      },
    });
    appendLog("success", `刷新流程已启动: ${shortOperationId(jobId)}`);
    notify("info", "官方上下文刷新已启动");
  }, [appendLog, callSyncStart, credentials, notify]);

  const interruptOfficialContextRefresh = useCallback(async (message: string) => {
    if (!syncJobId) return;
    setSyncRunning(false);
    setSyncStatus((previous) => ({
      ...(previous || { job_id: syncJobId, task_id: syncJobId, status: "stopped" }),
      job_id: previous?.job_id || syncJobId,
      task_id: previous?.task_id || syncJobId,
      status: "stopped",
      phase: "stopped",
      error: message,
      progress: {
        ...(previous?.progress || {}),
        job_id: previous?.progress?.job_id || syncJobId,
        task_id: previous?.progress?.task_id || syncJobId,
        phase: "stopped",
        phase_label: "已自动停止",
        status_message: message,
        percent_complete: 100,
      },
    }));
    const result = await callSyncCancel("/api/sync_cancel", {
      method: "POST",
      body: JSON.stringify({ job_id: syncJobId }),
    });
    if (!result?.ok) {
      const cancelMessage = operationFailureMessage(result?.error || result?.error_code, "停止请求暂未确认。请稍后重新读取状态。");
      appendLog("error", cancelMessage);
      notify("error", cancelMessage);
      return;
    }
    appendLog("warning", message);
    notify("warning", message);
  }, [appendLog, callSyncCancel, notify, syncJobId]);

  const pollSyncStatus = useCallback(async () => {
    if (!syncJobId) return;
    if (syncPollInFlightRef.current) return;
    syncPollInFlightRef.current = true;
    try {
      const result = await callSyncStatus<JobStatus>(`/api/sync_status?job_id=${encodeURIComponent(syncJobId)}&compact=1`);
      if (!result?.ok) {
        const message = operationFailureMessage(result?.error || result?.error_code, "刷新状态读取失败。");
        const failures = syncPollFailureCountRef.current + 1;
        syncPollFailureCountRef.current = failures;
        appendLog("warning", `刷新状态读取失败 (${failures}/${SYNC_STATUS_FAILURE_LIMIT}): ${message}`);
        if (failures >= SYNC_STATUS_FAILURE_LIMIT) {
          await interruptOfficialContextRefresh("连续读取刷新状态失败，已自动停止本次刷新。请检查网络或稍后重试。");
        }
        return;
      }
      syncPollFailureCountRef.current = 0;
      setSyncStatus(result);
      const statusText = String(result?.status || "");
      if (["completed", "completed_with_warnings"].includes(statusText)) {
        setSyncRunning(false);
        syncPollFailureCountRef.current = 0;
        appendLog(statusText === "completed" ? "success" : "warning", operationStatusMessage(result));
        notify(statusText === "completed" ? "success" : "warning", "官方上下文刷新完成");
      } else if (["failed", "cancelled", "stopped"].includes(statusText)) {
        setSyncRunning(false);
        syncPollFailureCountRef.current = 0;
        appendLog(statusText === "failed" ? "error" : "warning", operationStatusMessage(result));
        notify(statusText === "failed" ? "error" : "warning", operationStatusMessage(result));
      }
    } finally {
      syncPollInFlightRef.current = false;
    }
  }, [appendLog, callSyncStatus, interruptOfficialContextRefresh, notify, syncJobId]);

  useEffect(() => {
    if (!syncRunning || !syncJobId) return;
    const timer = window.setInterval(() => {
      void pollSyncStatus();
    }, POLL_INTERVAL_MS);
    void pollSyncStatus();
    return () => window.clearInterval(timer);
  }, [pollSyncStatus, syncJobId, syncRunning]);

  const stopOfficialContextRefresh = useCallback(async () => {
    if (!syncJobId) return;
    const result = await callSyncCancel("/api/sync_cancel", {
      method: "POST",
      body: JSON.stringify({ job_id: syncJobId }),
    });
    if (!result?.ok) {
      const message = operationFailureMessage(result?.error || result?.error_code, "停止请求失败。请稍后重试。");
      appendLog("error", message);
      notify("error", message);
      return;
    }
    setSyncRunning(false);
    syncPollFailureCountRef.current = 0;
    appendLog("warning", "已发送停止请求，系统会在当前官方接口返回后结束。");
    notify("info", "停止请求已发送");
  }, [appendLog, callSyncCancel, notify, syncJobId]);

  const currentProgress = operationProgress(mode, syncStatus, readinessApi.data, checkResultsApi.data);
  const currentError = currentModeError(mode, syncStatus, {
    syncStart: syncStartApi.error,
    syncStatus: syncStatusApi.error,
    readiness: readinessApi.error,
    checks: checkResultsApi.error,
  });
  const currentState = progressState(mode, syncRunning, syncStatus, readinessApi.loading, checkResultsApi.loading, currentError);
  const readiness = readinessApi.data;
  const checkRows = checkResultsApi.data?.items || checkResultsApi.data?.checks || [];
  const readinessBlockers = (readiness?.top_blocking_reasons || []).slice(0, 3);
  const familyBlockers = (readiness?.top_family_blocking_reasons || []).slice(0, 3);
  const productionGaps = (readiness?.production_gaps || readiness?.findings || []).slice(0, 4);
  const nextSteps = (readiness?.required_next_steps || []).slice(0, 3);
  const bestCandidate = readiness?.best_candidate || {};
  const bestCandidateReasons = (bestCandidate.blocking_reasons || []).slice(0, 4);
  const hasBestCandidateEvidence = Boolean(
    bestCandidate.alpha_id ||
    bestCandidate.official_alpha_id ||
    bestCandidate.decision_band ||
    bestCandidateReasons.length,
  );
  const summaryCounts = readiness?.summary_counts || {};
  const syncOverview = syncDataOverview(syncStatus, syncRunning);

  return (
    <div className="min-w-0 space-y-5 animate-fade-in">
      <section className="panel min-w-0 space-y-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="badge badge-info">官方操作入口</span>
              <span className="badge badge-neutral">按钮驱动</span>
              <span className="badge badge-neutral">非提交</span>
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-text-primary">官方同步与阻断复核</h2>
            <p className="mt-2 max-w-4xl text-base leading-7 text-text-secondary">
              这里把官方上下文刷新、提交前阻断复核和质量结果放在同一个页面里：点击按钮、看进度、读记录、处理阻断。系统会自动处理请求，用户只需留在浏览器里查看进度和结果。
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4 lg:min-w-[420px]">
            <OperationMetric label="官方上下文" value={syncContextStatus(syncStatus)} tone={syncRunning ? "warning" : syncStatus?.status === "completed" ? "success" : "neutral"} />
            <OperationMetric label="复核候选" value={String(readiness?.eligible_count ?? "-")} tone={readiness?.ready_to_submit ? "success" : "warning"} />
            <OperationMetric label="检查记录" value={String(checkRows.length || "-")} />
            <OperationMetric label="真实提交" value="关闭" tone="success" />
          </div>
        </div>

        <section className="grid gap-3 md:grid-cols-3" aria-label="官方同步数据总览">
          <OverviewCard
            label="同步状态"
            value={syncOverview.statusValue}
            detail={syncOverview.statusDetail}
            tone={syncOverview.statusTone}
          />
          <OverviewCard
            label="更新时间"
            value={syncOverview.updatedAtValue}
            detail={syncOverview.updatedAtDetail}
          />
          <OverviewCard
            label="官方报告总量"
            value={syncOverview.totalValue}
            detail={syncOverview.totalDetail}
            tone={syncOverview.totalTone}
          />
        </section>

        <div className="grid gap-3 lg:grid-cols-3">
          <ActionPanel
            title="刷新官方能力集"
            description="同步云端 Alpha 快照，并刷新官方字段、算子与 Dataset 上下文。"
            status={syncRunning ? "运行中" : syncJobId ? syncContextStatus(syncStatus) : "待启动"}
            primaryLabel={syncRunning ? "刷新中..." : "开始刷新"}
            disabled={syncRunning || syncStartApi.loading}
            onPrimary={startOfficialContextRefresh}
            secondaryLabel="停止"
            secondaryDisabled={!syncRunning || !syncJobId}
            onSecondary={stopOfficialContextRefresh}
          />
          <ActionPanel
            title="检查阻断复核"
            description="读取本地提交前阻断复核门禁，不调用真实提交。"
            status={readiness?.ready_to_submit ? "有候选" : readiness ? "仍阻断" : "待检查"}
            primaryLabel={readinessApi.loading ? "检查中..." : "读取复核"}
            disabled={readinessApi.loading}
            onPrimary={loadReadiness}
          />
          <ActionPanel
            title="回看检查结果"
            description="读取质量检查结果和阻断原因，方便继续迭代候选。"
            status={checkRows.length ? `${checkRows.length} 条记录` : "待读取"}
            primaryLabel={checkResultsApi.loading ? "加载中..." : "查看结果"}
            disabled={checkResultsApi.loading}
            onPrimary={loadChecks}
          />
        </div>

        <ProgressFeedback
          state={currentState}
          title="操作进度"
          progress={currentProgress}
          error={currentError}
          onRetry={mode === "context_refresh" ? startOfficialContextRefresh : mode === "readiness" ? loadReadiness : mode === "checks" ? loadChecks : undefined}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)]">
        <div className="min-w-0 rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-text-primary">操作事件</h3>
              <p className="text-xs text-text-tertiary">系统动作会写成可读事件，不展示命令或路径。</p>
            </div>
            <button type="button" className="btn btn-secondary text-sm" onClick={() => setLogs([])}>
              清空
            </button>
          </div>
          <div className="max-h-80 min-w-0 overflow-y-auto rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-3 text-sm leading-6 text-text-secondary" role="status" aria-live="polite" aria-label="官方操作时间线">
            {logs.length ? logs.map((entry, index) => (
              <div key={`${entry.time}_${index}`} className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-l border-border-subtle pb-3 pl-3 last:pb-0">
                <span className={`mt-1 ${logDotTone(entry.tone)}`} aria-hidden="true" />
                <div className="min-w-0">
                  <p className="text-xs text-text-tertiary">{entry.time}</p>
                  <p className={`break-words ${logTone(entry.tone)}`}>{entry.message}</p>
                </div>
              </div>
            )) : (
              <div className="text-text-tertiary">事件已清空。</div>
            )}
          </div>
        </div>

        <div className="min-w-0 space-y-4">
          <section className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-4">
            <h3 className="text-sm font-semibold text-text-primary">阻断复核摘要</h3>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <SummaryMetric label="复核通过" value={readiness?.ready_to_submit ? "是" : "否"} />
              <SummaryMetric label="复核候选" value={String(readiness?.eligible_count ?? 0)} />
              <SummaryMetric label="候选总数" value={String(readiness?.candidate_count ?? 0)} />
              <SummaryMetric label="最近验证" value={readiness?.latest_job_id ? shortOperationId(readiness.latest_job_id) : "-"} title={readiness?.latest_job_id} mono />
            </dl>
            <div className="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
              <BlockerList title="当前阻断" rows={readinessBlockers.map(reasonCountText)} empty="暂无就绪数据" />
              <BlockerList title="候选族阻断" rows={familyBlockers.map(reasonCountText)} empty="暂无候选族阻断" />
              <BlockerList title="下一步" rows={nextSteps.map(actionStepLabel)} empty="先读取阻断复核证据" />
            </div>
          </section>

          <section className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-4">
            <h3 className="text-sm font-semibold text-text-primary">收敛诊断</h3>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <SummaryMetric label="官方验证" value={String(summaryCounts.official_validation_passed ?? 0)} />
              <SummaryMetric label="官方仿真" value={String(summaryCounts.officially_simulated ?? 0)} />
              <SummaryMetric label="复核带" value={String(summaryCounts.submission_ready ?? 0)} />
              <SummaryMetric label="候选族" value={String(readiness?.job_family_candidate_count ?? 0)} />
            </dl>
            <div className="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
              <BlockerList title="生产缺口" rows={productionGaps.map(findingText)} empty="先读取阻断复核证据" />
              <BlockerList title="最佳候选阻断" rows={bestCandidateReasons.map(readinessReasonLabel)} empty="暂无最佳候选阻断" />
            </div>
            <div className="mt-3 rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-3 text-sm leading-6 text-text-secondary">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">最佳候选证据</p>
              <dl className="mt-2 grid grid-cols-2 gap-3">
                <SummaryMetric label="Alpha" value={hasBestCandidateEvidence ? bestCandidate.alpha_id || "-" : "-"} mono />
                <SummaryMetric label="分数" value={hasBestCandidateEvidence ? formatOptionalNumber(bestCandidate.score) : "-"} />
                <SummaryMetric label="决策" value={hasBestCandidateEvidence ? readinessReasonLabel(bestCandidate.decision_band || "") : "-"} />
                <SummaryMetric label="相似度" value={hasBestCandidateEvidence ? formatOptionalNumber(bestCandidate.max_similarity) : "-"} />
                <SummaryMetric label="本地回测" value={formatLocalBacktestStatus(bestCandidate.local_backtest_passed, hasBestCandidateEvidence)} />
                <SummaryMetric label="风险" value={hasBestCandidateEvidence ? riskLevelLabel(bestCandidate.risk_level || "") : "-"} />
              </dl>
            </div>
          </section>

          <section className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-4">
            <h3 className="text-sm font-semibold text-text-primary">官方上下文摘要</h3>
            <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
              <SummaryMetric label="字段" value={fieldFromProgress(syncStatus, "fields_count")} />
              <SummaryMetric label="算子" value={fieldFromProgress(syncStatus, "operators_count")} />
              <SummaryMetric label="数据集" value={fieldFromProgress(syncStatus, "datasets_count")} />
            </dl>
            <p className="mt-3 text-sm leading-6 text-text-secondary">
              {syncStatus?.progress?.status_message || syncStatus?.status_message || "尚未启动官方上下文刷新。"}
            </p>
          </section>
        </div>
      </section>
    </div>
  );
}

function ActionPanel({
  title,
  description,
  status,
  primaryLabel,
  disabled,
  onPrimary,
  secondaryLabel,
  secondaryDisabled,
  onSecondary,
}: {
  title: string;
  description: string;
  status: string;
  primaryLabel: string;
  disabled?: boolean;
  onPrimary: () => void;
  secondaryLabel?: string;
  secondaryDisabled?: boolean;
  onSecondary?: () => void;
}) {
  return (
    <article className="min-w-0 rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
          <p className="mt-1 text-sm leading-6 text-text-secondary">{description}</p>
        </div>
        <span className="badge badge-neutral shrink-0 text-xs">{status}</span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className="btn btn-primary text-sm" disabled={disabled} onClick={onPrimary}>
          {primaryLabel}
        </button>
        {secondaryLabel && onSecondary && (
          <button type="button" className="btn btn-secondary text-sm" disabled={secondaryDisabled} onClick={onSecondary}>
            {secondaryLabel}
          </button>
        )}
      </div>
    </article>
  );
}

function OperationMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "success" | "warning" | "neutral" }) {
  return (
    <div className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] px-3 py-2">
      <p className="text-xs text-text-tertiary">{label}</p>
      <p className={`mt-1 truncate text-sm font-semibold ${tone === "success" ? "text-positive" : tone === "warning" ? "text-warning" : "text-text-primary"}`}>{value}</p>
    </div>
  );
}

function OverviewCard({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: OverviewTone;
}) {
  const toneClass = tone === "success"
    ? "border-border-subtle bg-positive-subtle text-positive"
    : tone === "warning"
      ? "border-[oklch(0.65_0.06_85/0.25)] bg-warning-subtle text-warning"
      : "border-border-subtle bg-[oklch(0.115_0.007_45)] text-text-primary";
  return (
    <article className={`min-w-0 rounded-md border p-4 ${toneClass}`}>
      <p className="text-xs font-semibold uppercase tracking-wide opacity-70">{label}</p>
      <p className="mt-2 truncate text-xl font-semibold tracking-tight" title={value}>{value}</p>
      <p className="mt-1 min-h-10 break-words text-sm leading-5 opacity-80">{detail}</p>
    </article>
  );
}

function SummaryMetric({ label, value, title, mono = false }: { label: string; value: string; title?: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-text-tertiary">{label}</dt>
      <dd className={`mt-1 truncate text-sm font-semibold text-text-primary ${mono ? "font-mono-value" : ""}`} title={title || value}>{value}</dd>
    </div>
  );
}

function BlockerList({ title, rows, empty }: { title: string; rows: string[]; empty: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">{title}</p>
      <ul className="mt-1 space-y-1">
        {(rows.length ? rows : [empty]).map((row, index) => (
          <li key={`${title}_${index}`} className="break-words">{row}</li>
        ))}
      </ul>
    </div>
  );
}

function reasonCountText(row: { reason: string; count: number }) {
  return `${readinessReasonLabel(row.reason)} (${row.count})`;
}

function findingText(row: { code?: string; message?: string }) {
  const code = readinessReasonLabel(row.code || "");
  const message = readableBackendText(row.message || "");
  if (message && message !== code) return `${code}: ${message}`;
  return code;
}

function readinessReasonLabel(reason: string) {
  const labels: Record<string, string> = {
    candidate_family_missing_official_alpha_id: "候选族缺少官方 Alpha ID",
    candidate_family_missing_official_metrics: "候选族缺少官方仿真指标",
    candidate_family_not_submit_band: "候选族尚未进入复核带",
    decision_band_not_submit_candidate: "评分决策仍非提交候选",
    optimize: "需要继续优化",
    research_only: "仅限研究",
    submit_candidate: "提交前复核候选",
    high_cloud_similarity: "云端相似度过高",
    high_turnover_generation_risk: "生成表达式存在高换手风险",
    local_backtest_failed: "本地回测未通过",
    missing_cloud_similarity: "缺少云端相似度证据",
    missing_official_alpha_id: "缺少官方 Alpha ID",
    missing_official_metrics: "缺少官方仿真指标",
    no_submit_ready_candidate: "没有提交前复核候选",
    not_submission_ready: "尚未达到阻断复核通过标准",
    official_validation_without_simulation: "有官方验证但缺少官方仿真指标",
  };
  return labels[reason] || reason || "-";
}

function riskLevelLabel(level: string) {
  const labels: Record<string, string> = {
    high: "高",
    medium: "中",
    low: "低",
  };
  return labels[level] || level || "-";
}

function actionStepLabel(step: string) {
  const labels: Record<string, string> = {
    "review final submission intent before any real submit": "真实提交前先人工复核最终提交意图",
    "resolve local blockers before submit review": "先修复本地阻断，再进入提交复核",
    "run official simulation/check in a trusted environment": "在可信环境运行官方仿真/检查",
  };
  return labels[step] || readableBackendText(step) || step;
}

function operationFailureMessage(raw: unknown, fallback: string) {
  const message = readableBackendText(raw);
  return message || fallback;
}

function readableBackendText(raw: unknown) {
  const value = String(raw || "").trim();
  const fieldRefreshMatch = value.match(/^Updating official fields cache:\s*(.+)$/);
  if (fieldRefreshMatch) return `正在刷新官方字段缓存: ${fieldRefreshMatch[1]}`;
  const labels: Record<string, string> = {
    "Official context refreshed.": "官方上下文已刷新。",
    "candidate family lacks official simulation metrics": "候选族缺少官方仿真指标",
    "official context timeout": "官方上下文刷新超时，请稍后重试。",
    "unknown sync job": "找不到本次同步任务，请重新启动刷新。",
    "unknown job": "找不到本次任务，请重新启动流程。",
    JOB_NOT_FOUND: "找不到本次任务，请重新启动流程。",
    OFFICIAL_CONTEXT_REFRESH_TIMEOUT: "官方上下文刷新超时，请稍后重试。",
  };
  return labels[value] || value;
}

function formatOptionalNumber(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(3);
}

function formatLocalBacktestStatus(value: unknown, hasEvidence: boolean) {
  if (!hasEvidence) return "-";
  if (value === true) return "通过";
  if (value === false) return "未通过";
  return "-";
}

function requestDeadline() {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), OPERATION_REQUEST_TIMEOUT_MS);
  return {
    signal: controller.signal,
    clear: () => window.clearTimeout(timer),
  };
}

function syncDataOverview(syncStatus: JobStatus | null, syncRunning: boolean) {
  const statusValue = syncRunning ? "同步中" : syncContextStatus(syncStatus);
  const statusDetail = syncStatus
    ? `${phaseLabel(syncStatus)}: ${operationStatusMessage(syncStatus)}`
    : "等待启动云端 Alpha 同步。";
  let statusTone: OverviewTone = "neutral";
  if (syncRunning) statusTone = "warning";
  else if (syncStatus?.status === "completed" || syncStatus?.status === "completed_with_warnings") statusTone = "success";
  else if (syncStatus?.status === "failed") statusTone = "warning";
  const updatedAt = syncStatusUpdatedAt(syncStatus);
  const total = syncDataTotal(syncStatus);
  return {
    statusValue,
    statusDetail,
    statusTone,
    updatedAtValue: updatedAt ? formatClock(updatedAt) : "-",
    updatedAtDetail: updatedAt ? "来自本次同步进度。" : "暂无同步更新时间。",
    ...total,
  };
}

function syncDataTotal(syncStatus: JobStatus | null) {
  const terminal = isTerminalSyncStatus(syncStatus);
  const scanned = firstPositiveNumber(
    numberField(syncStatus?.progress, "scanned"),
    resultNumberField(syncStatus, "scanned"),
    resultNumberField(syncStatus, "count"),
  );
  const reportedTotal = firstPositiveNumber(
    numberField(syncStatus?.progress, "total"),
    resultNumberField(syncStatus, "total"),
  );
  const completedCount = firstPositiveNumber(
    resultNumberField(syncStatus, "count"),
    resultNumberField(syncStatus, "scanned"),
    numberField(syncStatus?.progress, "scanned"),
  );
  if (terminal && completedCount > 0) {
      const detail = reportedTotal > 0 && reportedTotal !== completedCount
        ? `实际完成；官方当前报告总量 ${formatCount(reportedTotal)}。`
        : "实际完成数量；不是同步上限。";
    return {
      totalValue: formatCount(completedCount),
      totalDetail: detail,
      totalTone: "success" as const,
    };
  }
  if (scanned > 0) {
    return {
      totalValue: `已扫描 ${formatCount(scanned)}`,
      totalDetail: reportedTotal > 0
        ? `官方当前报告总量 ${formatCount(reportedTotal)}；这不是同步上限，仍会继续读取后续页面。`
        : "官方报告总量仍在确认。",
      totalTone: "warning" as const,
    };
  }
  if (reportedTotal > 0) {
    return {
      totalValue: `报告 ${formatCount(reportedTotal)}`,
      totalDetail: "官方当前报告总量；尚未完成实际同步确认，也不是同步上限。",
      totalTone: "neutral" as const,
    };
  }
  return {
    totalValue: "-",
    totalDetail: "等待云端 Alpha 同步；不会使用固定同步上限。",
    totalTone: "neutral" as const,
  };
}

function operationProgress(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  readiness: SubmitReadinessResponse | null,
  checks: CheckResultsResponse | null,
): UnifiedProgress {
  if (mode === "context_refresh") {
    const scanStillRunning = isRunningScanStatus(syncStatus);
    return {
      phase: syncStatus?.phase || syncStatus?.progress?.phase || "context_refresh",
      phase_label: phaseLabel(syncStatus),
      status_message: operationStatusMessage(syncStatus),
      percent_complete: scanStillRunning ? null : normalizedProgressPercent(syncStatus),
      eta_seconds: syncStatus?.eta_seconds ?? syncStatus?.progress?.eta_seconds,
      scanned: numberField(syncStatus?.progress, "scanned"),
      total: scanStillRunning ? undefined : numberField(syncStatus?.progress, "total"),
      job_id: syncStatus?.job_id,
      task_id: syncStatus?.task_id,
    };
  }
  if (mode === "readiness") {
    return {
      phase: "submit_readiness",
      phase_label: "阻断复核",
      status_message: readiness ? `阻断复核 ${readiness.eligible_count ?? 0} / 候选 ${readiness.candidate_count ?? 0}` : "正在读取提交前阻断复核证据。",
      percent_complete: readiness ? 100 : 35,
      checked: readiness?.candidate_count ?? 0,
      total: readiness?.candidate_count ?? 0,
    };
  }
  if (mode === "checks") {
    const count = checkResultCount(checks);
    return {
      phase: "check_results",
      phase_label: "检查结果",
      status_message: checks ? `已加载 ${count} 条检查结果。` : "正在读取检查结果。",
      percent_complete: checks ? 100 : 35,
      checked: count,
      total: count,
    };
  }
  return {
    phase: "idle",
    phase_label: "等待操作",
    status_message: "选择一个操作后，系统会在这里展示真实进度。",
    percent_complete: 0,
  };
}

function progressState(
  mode: OperationMode,
  syncRunning: boolean,
  syncStatus: JobStatus | null,
  readinessLoading: boolean,
  checksLoading: boolean,
  error: string | null,
) {
  if (error) return "error";
  if (syncRunning || readinessLoading || checksLoading) return "progress";
  if (mode === "context_refresh" && syncStatus?.status === "failed") return "error";
  if (mode !== "idle") return "success";
  return "idle";
}

function currentModeError(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  errors: { syncStart: string | null; syncStatus: string | null; readiness: string | null; checks: string | null },
) {
  if (mode === "context_refresh") return operationFailureMessage(syncStatus?.error || errors.syncStart || errors.syncStatus, "");
  if (mode === "readiness") return operationFailureMessage(errors.readiness, "");
  if (mode === "checks") return operationFailureMessage(errors.checks, "");
  return null;
}

function operationStatusMessage(status: JobStatus | null) {
  if (!status) return "尚未启动。";
  const scanMessage = runningScanStatusMessage(status);
  if (scanMessage) return scanMessage;
  const message = (
    status.progress?.status_message ||
    status.status_message ||
    status.error ||
    `当前状态: ${status.status || "unknown"}`
  );
  return readableBackendText(message) || message;
}

function normalizedProgressPercent(status: JobStatus | null) {
  const terminal = isTerminalSyncStatus(status);
  const raw = status?.progress?.percent_complete ?? status?.progress?.percent ?? status?.percent_complete;
  const value = Number(raw);
  if (Number.isFinite(value)) return boundedProgressPercent(value, terminal);
  const scanned = numberField(status?.progress, "scanned");
  const total = numberField(status?.progress, "total");
  if (total > 0) return boundedProgressPercent((scanned / total) * 100, terminal);
  if (terminal) return 100;
  if (status?.status === "running") return 35;
  return 0;
}

function boundedProgressPercent(value: number, terminal: boolean) {
  const upperBound = terminal ? 100 : 99;
  return Math.max(0, Math.min(upperBound, value));
}

function isTerminalSyncStatus(status: JobStatus | null) {
  return ["completed", "completed_with_warnings", "failed", "stopped", "cancelled", "canceled"].includes(String(status?.status || ""));
}

function isRunningScanStatus(status: JobStatus | null) {
  const code = String(status?.progress?.status_code || status?.phase || status?.progress?.phase || "").toUpperCase();
  return !isTerminalSyncStatus(status) && code === "SCAN";
}

function runningScanStatusMessage(status: JobStatus | null) {
  if (!isRunningScanStatus(status)) return "";
  const scanned = numberField(status?.progress, "scanned");
  const reportedTotal = numberField(status?.progress, "total");
  if (scanned <= 0) return "正在扫描云端 Alpha，官方报告总量仍在确认。";
  if (reportedTotal > 0) {
    return `已扫描 ${formatCount(scanned)} 条云端 Alpha；官方当前报告总量 ${formatCount(reportedTotal)}，这不是同步上限，仍会继续读取后续页面。`;
  }
  return `已扫描 ${formatCount(scanned)} 条云端 Alpha；官方报告总量仍在确认。`;
}

function phaseLabel(status: JobStatus | null) {
  const code = String(status?.progress?.status_code || status?.phase || status?.progress?.phase || "context_refresh");
  const normalizedCode = code.toUpperCase();
  const labels: Record<string, string> = {
    AUTH: "认证",
    SCAN: "扫描云端",
    MERGE: "合并快照",
    CONTEXT_FIELDS: "刷新字段",
    CONTEXT_OPERATORS: "刷新算子",
    CONTEXT_FAILED: "上下文失败",
    COMPLETED: "完成",
    COMPLETED_WITH_WARNINGS: "带警告完成",
    STOPPED: "已停止",
    FAILED: "失败",
  };
  return labels[normalizedCode] || code;
}

function syncContextStatus(status: JobStatus | null) {
  const text = String(status?.status || "");
  if (!text) return "待启动";
  if (text === "completed_with_warnings") return "带警告";
  if (text === "completed") return "已刷新";
  if (text === "running" || text === "queued") return "进行中";
  if (text === "failed") return "失败";
  if (text === "stopped" || text === "cancelled") return "已停止";
  return text;
}

function fieldFromProgress(status: JobStatus | null, field: string) {
  const fromProgress = numberField(status?.progress, field);
  if (fromProgress > 0) return String(fromProgress);
  const result = status?.result as Record<string, unknown> | undefined;
  const fromResult = Number(result?.[field]);
  return Number.isFinite(fromResult) && fromResult > 0 ? String(fromResult) : "-";
}

function resultNumberField(status: JobStatus | null, field: string) {
  const result = status?.result;
  if (!result || typeof result !== "object" || Array.isArray(result)) return 0;
  const value = Number((result as Record<string, unknown>)[field]);
  return Number.isFinite(value) ? value : 0;
}

function firstPositiveNumber(...values: number[]) {
  return values.find((value) => Number.isFinite(value) && value > 0) || 0;
}

function numberField(source: Record<string, unknown> | undefined, field: string) {
  const value = Number(source?.[field]);
  return Number.isFinite(value) ? value : 0;
}

function syncStatusUpdatedAt(status: JobStatus | null) {
  const progressUpdated = numberField(status?.progress, "updated_at_ms");
  if (progressUpdated > 0) return new Date(progressUpdated);
  const resultUpdated = resultNumberField(status, "updated_at_ms");
  if (resultUpdated > 0) return new Date(resultUpdated);
  const startedAt = Date.parse(String(status?.started_at || ""));
  if (Number.isFinite(startedAt)) return new Date(startedAt);
  return status ? new Date() : null;
}

function formatCount(value: number) {
  return Math.max(0, Math.trunc(value)).toLocaleString("zh-CN");
}

function checkResultCount(payload: CheckResultsResponse | null | { count?: number; items?: unknown; checks?: unknown }) {
  if (!payload) return 0;
  const direct = Number(payload.count);
  if (Number.isFinite(direct) && direct >= 0) return direct;
  if (Array.isArray(payload.items)) return payload.items.length;
  if (Array.isArray(payload.checks)) return payload.checks.length;
  return 0;
}

function credentialsPayload(credentials?: BrainCredentials) {
  const payload: Record<string, string> = {};
  const username = credentials?.username.trim() || "";
  const password = credentials?.password || "";
  const token = credentials?.token.trim() || "";
  if (username) payload.username = username;
  if (password) payload.password = password;
  if (token) payload.token = token;
  return payload;
}

function logTone(tone: OperationLogEntry["tone"]) {
  if (tone === "success") return "text-positive";
  if (tone === "warning") return "text-warning";
  if (tone === "error") return "text-negative";
  return "text-text-secondary";
}

function logDotTone(tone: OperationLogEntry["tone"]) {
  if (tone === "success") return "status-dot status-dot-active";
  if (tone === "warning") return "status-dot status-dot-warning";
  if (tone === "error") return "status-dot status-dot-error";
  return "status-dot status-dot-idle";
}

function formatClock(date = new Date()) {
  return [date.getHours(), date.getMinutes(), date.getSeconds()]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

function shortOperationId(value: string) {
  const text = String(value || "").trim();
  if (text.length <= 12) return text;
  return `${text.slice(0, 6)}...${text.slice(-4)}`;
}
