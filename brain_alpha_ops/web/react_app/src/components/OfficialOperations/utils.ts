/** Shared utilities for OfficialOperationsPanel sub-components. */

import { apiErrorMessage, knownApiErrorMessage } from "@/helpers/errorExperience";
import { readinessNextActionLabel, readinessProductionGapLabel, readinessReasonLabel } from "@/helpers/readinessLabels";
import { classifyJobState, jobStatusMessage } from "@/helpers/runPayload";
import type { BrainCredentials, CloudAlphaCache, JobStatus, OfficialContextCache, SubmitReadinessResponse, UnifiedProgress } from "@/types";
import { isRecord } from "@/types";

export const POLL_INTERVAL_MS = 2000;
export const SYNC_STATUS_FAILURE_LIMIT = 3;
export const SYNC_PROGRESS_STALL_WARNING_MS = 30_000;
export const SYNC_PROGRESS_STALL_STOP_MS = 90_000;
export const OPERATION_REQUEST_TIMEOUT_MS = 10000;
export const STOP_RETRY_AFTER_MS = 60_000;
export const MAX_LOG_ROWS = 80;
export const ACTIVE_SYNC_JOB_ID_KEY = "brain_alpha_active_sync_job_id";

export interface OperationLogEntry {
  time: string;
  tone: "info" | "success" | "warning" | "error";
  message: string;
}

export type OperationMode = "idle" | "context_refresh" | "readiness" | "checks";
export type OverviewTone = "success" | "warning" | "neutral";
export type SyncStageKind = "scan" | "fields" | "operators" | "datasets" | "other";
export type SyncRange = "3d" | "7d" | "recent" | "6months" | "all";

export interface SyncStageMetric {
  kind: SyncStageKind;
  label: string;
  rateLabel: string;
  unit: string;
  rateUnit: string;
  current: number;
  total: number;
  elapsedSeconds: number;
  etaSeconds: number;
  ratePerSecond: number;
  pageNumber: number;
  expectedPages: number;
  pageSize: number;
  pageLimit: number;
  nextOffset: number;
  newUniqueItems: number;
  uniqueItems: number;
  confirmingTotalBoundary: boolean;
}

export interface SyncProgressMonitorState {
  jobId: string;
  signature: string;
  sinceMs: number;
  warned: boolean;
  interrupting: boolean;
}

export function formatClock(date = new Date()): string {
  return [date.getHours(), date.getMinutes(), date.getSeconds()]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

export function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return "0s";
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.round(totalSeconds % 60);
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export function formatCount(value: number): string {
  return Math.max(0, Math.trunc(value)).toLocaleString("zh-CN");
}

export function firstPositiveFloat(...values: number[]): number {
  return values.find((value) => Number.isFinite(value) && value > 0) || 0;
}

export function shortOperationId(value: string): string {
  const text = String(value || "").trim();
  if (text.length <= 12) return text;
  return `${text.slice(0, 6)}...${text.slice(-4)}`;
}

export function credentialsPayload(credentials?: BrainCredentials): Record<string, string> {
  const payload: Record<string, string> = {};
  const username = credentials?.username.trim() || "";
  const password = credentials?.password || "";
  const token = credentials?.token.trim() || "";
  if (username) payload.username = username;
  if (password) payload.password = password;
  if (token) payload.token = token;
  return payload;
}

export function hasPageCredentials(credentials?: BrainCredentials): boolean {
  return Boolean(
    credentials?.username?.trim() ||
    credentials?.password ||
    credentials?.token?.trim()
  );
}

export function saveStoredSyncJobId(jobId: string): void {
  const value = String(jobId || "").trim();
  if (value) {
    try {
      sessionStorage.setItem(ACTIVE_SYNC_JOB_ID_KEY, value);
    } catch { console.warn("OfficialOperations: non-critical operation skipped"); }
  }
}

export function loadStoredSyncJobId(): string {
  try {
    return String(sessionStorage.getItem(ACTIVE_SYNC_JOB_ID_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function clearStoredSyncJobId(): void {
  try {
    sessionStorage.removeItem(ACTIVE_SYNC_JOB_ID_KEY);
  } catch { console.warn("OfficialOperations: non-critical operation skipped"); }
}

export function logTone(tone: OperationLogEntry["tone"]): string {
  if (tone === "success") return "text-positive";
  if (tone === "warning") return "text-warning";
  if (tone === "error") return "text-negative";
  return "text-text-secondary";
}

export function logDotTone(tone: OperationLogEntry["tone"]): string {
  if (tone === "success") return "status-dot status-dot-active";
  if (tone === "warning") return "status-dot status-dot-warning";
  if (tone === "error") return "status-dot status-dot-error";
  return "status-dot status-dot-idle";
}

export function syncProgressMonitorSignature(result: JobStatus): string {
  const progress = result?.progress || {};
  return [
    progress.phase || "",
    progress.status_code || "",
    progress.percent_complete ?? "",
    progress.scanned ?? "",
    progress.added ?? "",
    progress.skipped ?? "",
    progress.failed ?? "",
  ].join("|");
}

export function isTerminalSyncStatus(result: JobStatus | null): boolean {
  if (!result) return false;
  const status = String(result?.status || "").toLowerCase();
  return ["completed", "failed", "stopped", "error"].includes(status);
}

export function operationFailureMessage(result: unknown, fallback: string): string {
  if (!result) return fallback;
  const error = isRecord(result) ? result.error : undefined;
  if (typeof error === "string" && error.trim()) return error.trim();
  return fallback;
}

export function requestDeadline(): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), OPERATION_REQUEST_TIMEOUT_MS);
  return {
    signal: controller.signal,
    clear: () => clearTimeout(timer),
  };
}

export function syncContextStatus(status: JobStatus | null): string {
  if (!status) return "待启动";
  const cache = status?.official_context_cache;
  if (cache?.complete) return "已缓存";
  if (cache?.in_progress) return "同步中";
  return "待刷新";
}

export function contextCacheComplete(cache?: Record<string, unknown>): boolean {
  return Boolean(cache?.complete);
}

export function checkResultCount(payload: { count?: number; items?: unknown; checks?: unknown } | null): number {
  if (!payload) return 0;
  const direct = Number(payload.count);
  if (Number.isFinite(direct) && direct >= 0) return direct;
  if (Array.isArray(payload.items)) return payload.items.length;
  if (Array.isArray(payload.checks)) return payload.checks.length;
  return 0;
}

// --- Functions extracted from OfficialOperationsPanel.tsx ---

export function countTitle(label: string, total: number) {
  return total > 0 ? `${label}（共 ${total}）` : label;
}

export function reasonCountText(row: { reason: string; count: number }) {
  return `${readinessReasonLabel(row.reason)} (${row.count})`;
}

export function findingText(row: { code?: string; message?: string }) {
  return readinessProductionGapLabel(row);
}

export function riskLevelLabel(level: string) {
  const normalized = String(level || "").toLowerCase();
  const labels: Record<string, string> = {
    high: "高",
    medium: "中",
    low: "低",
  };
  return labels[normalized] || (normalized ? "风险待确认" : "-");
}

export function actionStepLabel(step: string) {
  return readinessNextActionLabel(step);
}

export function formatOptionalNumber(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(3);
}

export function formatLocalBacktestStatus(value: unknown, hasEvidence: boolean) {
  if (!hasEvidence) return "-";
  if (value === true) return "通过";
  if (value === false) return "未通过";
  return "-";
}

export function syncStatusForDisplay(status: JobStatus | null, officialContextCache?: OfficialContextCache): JobStatus | null {
  const cache = status?.official_context_cache || officialContextCache;
  if (status) {
    return cache && status.official_context_cache !== cache
      ? { ...status, official_context_cache: cache }
      : status;
  }
  if (!cache) return null;
  return {
    job_id: "",
    task_id: "",
    status: "idle",
    phase: "local_cache",
    progress: {
      phase: "local_cache",
      status_code: contextCacheComplete(cache) ? "LOCAL_CACHE" : "LOCAL_CACHE_INVALID",
      status_message: contextCacheComplete(cache)
        ? "本地官方上下文缓存已加载。"
        : "本地官方上下文缓存完整性未通过，需要手动刷新。",
    },
    official_context_cache: cache,
  };
}

export function syncDataOverview(syncStatus: JobStatus | null, syncRunning: boolean, cloudAlphaCache?: CloudAlphaCache) {
  const localCacheReady = !syncRunning && cloudAlphaCacheReady(cloudAlphaCache) && contextCacheComplete(syncStatus?.official_context_cache);
  const statusValue = syncRunning ? "同步中" : syncContextStatus(syncStatus);
  const stage = syncStageMetric(syncStatus);
  const statusDetail = localCacheReady
    ? "本地云端 Alpha 快照与官方能力集缓存已通过完整性校验；需要最新数据时可手动刷新。"
    : syncStatus
    ? `${phaseLabel(syncStatus)}: ${operationStatusMessage(syncStatus)}`
    : "等待启动云端 Alpha 同步。";
  let statusTone: OverviewTone = "neutral";
  if (syncRunning) statusTone = "warning";
  else if (localCacheReady) statusTone = "success";
  else if (isSuccessfulSyncStatus(syncStatus)) statusTone = "success";
  else if (classifyJobState(syncStatus).failed || classifyJobState(syncStatus).missing) statusTone = "warning";
  const updatedAt = syncStatusUpdatedAt(syncStatus) || cloudAlphaCacheUpdatedAt(cloudAlphaCache);
  const total = syncDataTotal(syncStatus, cloudAlphaCache);

  const hasLiveMetrics = syncRunning && (stage.current > 0 || stage.elapsedSeconds > 0);
  const scanIndeterminate = syncRunning && stage.kind === "scan";
  const scanHasTotal = stage.kind === "scan" && stage.total > 0;
  const etaValue = scanIndeterminate
    ? (scanHasTotal ? "分页继续确认" : "等待分页参考数")
    : stage.etaSeconds > 0
      ? formatDuration(stage.etaSeconds)
      : stage.elapsedSeconds > 0
        ? "计算中..."
        : "-";
  const etaDetail = scanIndeterminate
    ? scanEtaDetail(stage)
    : stage.etaSeconds > 0
      ? (stage.total > 0
        ? `预计 ${formatDuration(stage.etaSeconds)} 后完成${stage.label}（${formatCount(stage.current)} / ${formatCount(stage.total)} ${stage.unit}）。`
        : `预计 ${formatDuration(stage.etaSeconds)} 后完成${stage.label}。`)
      : stage.elapsedSeconds > 0
        ? `已用时 ${formatDuration(stage.elapsedSeconds)}，正在刷新${stage.label}，剩余时间计算中。`
        : `等待${stage.label}进度更新。`;
  const rateValue = stage.ratePerSecond > 0 ? `${stage.ratePerSecond.toFixed(1)} ${stage.rateUnit}` : "-";
  const rateDetail = stage.current > 0 && stage.elapsedSeconds > 0
    ? `${stage.label}已处理 ${formatCount(stage.current)} ${stage.unit}，历时 ${formatDuration(stage.elapsedSeconds)}。`
    : `${stage.rateLabel}来自当前阶段的官方 API 进度反馈。`;

  return {
    statusValue,
    statusDetail,
    statusTone,
    updatedAtValue: updatedAt ? formatClock(updatedAt) : "-",
    updatedAtDetail: updatedAt ? (localCacheReady ? "来自本地云端 Alpha 快照。" : "来自本次同步进度。") : "暂无同步更新时间。",
    ...total,
    hasLiveMetrics,
    etaLabel: stage.kind === "scan" ? "分页进度" : "阶段估算",
    etaValue,
    etaDetail,
    rateLabel: stage.rateLabel,
    rateValue,
    rateDetail,
  };
}

export function syncDataTotal(syncStatus: JobStatus | null, cloudAlphaCache?: CloudAlphaCache) {
  const terminal = isTerminalSyncStatus(syncStatus);
  const successful = isSuccessfulSyncStatus(syncStatus);
  const scanned = firstPositiveNumber(
    numberField(syncStatus?.progress, "scanned"),
    resultNumberField(syncStatus, "scanned"),
    resultNumberField(syncStatus, "count"),
  );
  const reportedTotal = firstPositiveNumber(
    numberField(syncStatus?.progress, "api_reported_total"),
    numberField(syncStatus?.progress, "filter_window_count"),
    resultNumberField(syncStatus, "api_reported_total"),
    resultNumberField(syncStatus, "filter_window_count"),
  );
  const completedCount = firstPositiveNumber(
    resultNumberField(syncStatus, "count"),
    resultNumberField(syncStatus, "scanned"),
    numberField(syncStatus?.progress, "scanned"),
  );
  if (successful && completedCount > 0) {
      const detail = reportedTotal > 0 && reportedTotal !== completedCount
        ? `本次同步实际保存 ${formatCount(completedCount)} 条；接口分页参考数 ${formatCount(reportedTotal)} 条仅用于分页边界判断。`
        : "本次同步实际保存数量；来自本地同步结果。";
    return {
      totalValue: formatCount(completedCount),
      totalDetail: detail,
      totalTone: "success" as const,
    };
  }
  if (scanned > 0) {
    if (terminal && !successful) {
      return {
        totalValue: `已拉取 ${formatCount(scanned)}`,
        totalDetail: "本次未完成；结果未确认完成，官方分页参考值不作为完成判断。",
        totalTone: "warning" as const,
      };
    }
    return {
      totalValue: `已拉取 ${formatCount(scanned)}`,
      totalDetail: terminal
        ? (reportedTotal > 0
          ? `本次未完成；接口分页参考数 ${formatCount(reportedTotal)} 条仅用于分页边界判断，已拉取 ${formatCount(scanned)} 条。`
          : "本次未完成；接口分页参考数仍在确认。")
        : reportedTotal > 0
        ? `接口分页参考数 ${formatCount(reportedTotal)} 条，不是云端 Alpha 总量；${syncScanPageSummary(syncStatus)}`
        : "接口分页参考数仍在确认；会按官方分页继续读取。",
      totalTone: "warning" as const,
    };
  }
  if (terminal && !successful) {
    return {
      totalValue: "-",
      totalDetail: "本次未完成；结果未确认完成，官方分页参考值不作为完成判断。",
      totalTone: "warning" as const,
    };
  }
  if (reportedTotal > 0) {
    return {
      totalValue: `分页参考数 ${formatCount(reportedTotal)}`,
      totalDetail: "接口分页参考数；尚未完成实际同步确认，不是云端 Alpha 总量。",
      totalTone: "neutral" as const,
    };
  }
  if (cloudAlphaCacheReady(cloudAlphaCache)) {
    const count = firstPositiveNumber(cloudAlphaCache?.count, cloudAlphaCache?.total);
    if (count <= 0) {
      return {
        totalValue: "本地快照可用",
        totalDetail: cloudAlphaCache?.is_stale
          ? "本地云端 Alpha 快照可用但已过期；精确数量请刷新云端快照。"
          : "本地云端 Alpha 快照已确认可用；精确数量由云端快照页加载。",
        totalTone: (cloudAlphaCache?.is_stale ? "warning" : "success") as OverviewTone,
      };
    }
    return {
      totalValue: `本地保存 ${formatCount(count)}`,
      totalDetail: cloudAlphaCache?.is_stale
        ? "本地云端 Alpha 快照可用但已过期；需要最新数据时点击开始刷新。"
        : "来自本地云端 Alpha 快照；后续登录默认直接使用该缓存。",
      totalTone: (cloudAlphaCache?.is_stale ? "warning" : "success") as OverviewTone,
    };
  }
  return {
    totalValue: "-",
    totalDetail: "等待云端 Alpha 同步；会先读取接口分页参考数，再按分页参数循环拉取。",
    totalTone: "neutral" as const,
  };
}

export function operationProgress(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  readiness: SubmitReadinessResponse | null,
  checks: { count?: number; items?: unknown; checks?: unknown } | null,
): UnifiedProgress {
  if (mode === "context_refresh") {
    const stage = syncStageMetric(syncStatus);
    const terminal = isTerminalSyncStatus(syncStatus);
    const successful = isSuccessfulSyncStatus(syncStatus);
    const terminalFailure = terminal && !successful;
    const scanStillRunning = stage.kind === "scan" && !terminal;
    const hasStageTotal = stage.total > 0;
    const syncProgress = syncStatus?.progress;
    const stagePercent = terminalFailure
      ? null
      : stage.total > 0
      ? boundedProgressPercent((stage.current / stage.total) * 100, terminal)
      : terminal
        ? normalizedProgressPercent(syncStatus)
        : null;
    return {
      operation: scanStillRunning ? "sync_alphas" : undefined,
      status_code: scanStillRunning ? "SCAN" : stringField(syncProgress, "status_code"),
      status: syncStatus?.status,
      status_kind: syncStatus?.status_kind || stringField(syncProgress, "status_kind"),
      terminal: syncStatus?.terminal ?? booleanField(syncProgress, "terminal"),
      active: syncStatus?.active ?? booleanField(syncProgress, "active"),
      interrupted: syncStatus?.interrupted ?? booleanField(syncProgress, "interrupted"),
      recoverable: syncStatus?.recoverable ?? booleanField(syncProgress, "recoverable"),
      retryable: syncStatus?.retryable ?? booleanField(syncProgress, "retryable"),
      error: syncStatus?.error || stringField(syncProgress, "error"),
      error_code: stringField(syncProgress, "error_code"),
      user_error: syncStatus?.user_error || userErrorField(syncProgress),
      user_error_kind: syncStatus?.user_error_kind || stringField(syncProgress, "user_error_kind"),
      user_message: syncStatus?.user_message || stringField(syncProgress, "user_message"),
      next_action: syncStatus?.next_action || stringField(syncProgress, "next_action"),
      phase: scanStillRunning ? "scan" : syncStatus?.phase || syncStatus?.progress?.phase || "context_refresh",
      phase_label: phaseLabel(syncStatus),
      status_message: operationStatusMessage(syncStatus),
      percent_complete: scanStillRunning ? null : stagePercent,
      eta_seconds: terminalFailure ? null : stage.etaSeconds || null,
      eta_deadline_at_ms: stage.kind === "scan" || terminalFailure || !hasStageTotal ? null : firstPositiveNumber(numberField(syncStatus?.progress, "eta_deadline_at_ms"), resultNumberField(syncStatus, "eta_deadline_at_ms")) || null,
      done: stage.kind === "scan" ? undefined : stage.current || undefined,
      scanned: stage.kind === "scan" && !terminalFailure ? stage.current : undefined,
      total: stage.kind === "scan" || terminalFailure || stage.total <= 0 ? undefined : stage.total,
      api_reported_total: numberField(syncStatus?.progress, "api_reported_total") || undefined,
      remaining_items: numberField(syncStatus?.progress, "remaining_items") || undefined,
      has_more: typeof syncStatus?.progress?.has_more === "boolean" ? syncStatus.progress.has_more : undefined,
      pagination_complete: typeof syncStatus?.progress?.pagination_complete === "boolean" ? syncStatus.progress.pagination_complete : undefined,
      pagination_target: typeof syncStatus?.progress?.pagination_target === "string" ? syncStatus.progress.pagination_target : undefined,
      stop_reason: typeof syncStatus?.progress?.stop_reason === "string" ? syncStatus.progress.stop_reason : undefined,
      page_number: stage.pageNumber || undefined,
      pages_fetched: stage.pageNumber || undefined,
      expected_pages: stage.expectedPages || undefined,
      page_size: stage.pageSize || undefined,
      page_limit: stage.pageLimit || undefined,
      next_offset: stage.nextOffset || undefined,
      new_unique_items: stage.newUniqueItems || undefined,
      unique_items: stage.uniqueItems || undefined,
      confirming_total_boundary: stage.confirmingTotalBoundary || undefined,
      indeterminate: scanStillRunning || undefined,
      open_ended: scanStillRunning || undefined,
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

export function progressState(
  mode: OperationMode,
  syncRunning: boolean,
  syncStatus: JobStatus | null,
  readinessLoading: boolean,
  checksLoading: boolean,
  error: string | null,
) {
  if (error) return "error";
  if (syncRunning || readinessLoading || checksLoading) return "progress";
  const syncState = classifyJobState(syncStatus);
  if (mode === "context_refresh" && (syncState.failed || syncState.missing || syncState.interrupted)) return "error";
  if (mode !== "idle") return "success";
  return "idle";
}

export function currentModeError(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  errors: { syncStart: string | null; syncStatus: string | null; readiness: string | null; checks: string | null },
) {
  if (mode === "context_refresh") {
    const syncState = classifyJobState(syncStatus);
    const stopped = syncState.interrupted;
    const recoverableMessage = stopped
      ? (syncStatus?.progress?.status_message || syncStatus?.status_message || "官方上下文刷新已停止，可重新刷新。")
      : "";
    if (syncStatus && (syncState.failed || syncState.missing || syncState.interrupted)) {
      return operationFailureMessage(syncStatus, "") || operationFailureMessage(errors.syncStart || errors.syncStatus || recoverableMessage, "");
    }
    return operationFailureMessage(
      syncStatus?.error || errors.syncStart || errors.syncStatus || recoverableMessage,
      "",
    );
  }
  if (mode === "readiness") return operationFailureMessage(errors.readiness, "");
  if (mode === "checks") return operationFailureMessage(errors.checks, "");
  return null;
}

export function operationStatusMessage(status: JobStatus | null) {
  if (!status) return "尚未启动。";
  const scanMessage = runningScanStatusMessage(status);
  if (scanMessage) return scanMessage;
  const state = classifyJobState(status);
  const apiMessage = apiErrorMessage(status, "");
  if (apiMessage) return readableBackendText(apiMessage) || apiMessage;
  if (state.interrupted) return "官方上下文刷新已停止，结果未确认完成。";
  if (state.failed || state.missing) return "官方上下文刷新失败，请稍后重试或重新启动流程。";
  const sharedMessage = jobStatusMessage(status, "");
  const readableSharedMessage = readableBackendText(sharedMessage);
  if (readableSharedMessage) return readableSharedMessage;
  const message = (
    status.progress?.status_message ||
    status.status_message ||
    status.error ||
    `当前状态: ${status.status || "未知"}`
  );
  const readableMessage = readableBackendText(message);
  if (readableMessage) return readableMessage;
  if (state.active || status.status === "running") return "官方上下文刷新正在运行，等待下一次状态更新。";
  return "官方上下文状态暂不明确，请刷新状态或重新启动流程。";
}

export function normalizedProgressPercent(status: JobStatus | null) {
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

export function boundedProgressPercent(value: number, terminal: boolean) {
  const upperBound = terminal ? 100 : 99;
  return Math.max(0, Math.min(upperBound, value));
}

export function isSuccessfulSyncStatus(status: JobStatus | null) {
  return classifyJobState(status).successful;
}

export function isRunningScanStatus(status: JobStatus | null) {
  return !isTerminalSyncStatus(status) && syncStageCode(status) === "SCAN";
}

export function runningScanStatusMessage(status: JobStatus | null) {
  if (!isRunningScanStatus(status)) return "";
  const scanned = numberField(status?.progress, "scanned");
  const apiTotal = firstPositiveNumber(
    numberField(status?.progress, "api_reported_total"),
    numberField(status?.progress, "filter_window_count"),
  );
  if (scanned <= 0) return "正在扫描云端 Alpha，等待官方接口返回第一页和接口分页参考数；首次全量同步可能需要 3-5 分钟，近 3/7 天范围通常更快。";
  if (apiTotal > 0) {
    return `已拉取 ${formatCount(scanned)} 条云端 Alpha；接口分页参考数 ${formatCount(apiTotal)} 条，不是云端 Alpha 总量，会继续按分页自动确认边界；${syncScanPageSummary(status)}`;
  }
  return `已拉取 ${formatCount(scanned)} 条云端 Alpha；接口分页参考数仍在确认，会按分页返回继续读取。`;
}

export function syncStageMetric(status: JobStatus | null): SyncStageMetric {
  const progress = status?.progress;
  const code = syncStageCode(status);
  const elapsedSeconds = firstPositiveNumber(
    numberField(progress, "elapsed_seconds"),
    resultNumberField(status, "elapsed_seconds"),
  );
  if (code === "SCAN") {
    return buildSyncStageMetric({
      kind: "scan",
      label: "云端 Alpha 扫描",
      rateLabel: "扫描速率",
      unit: "条云端 Alpha",
      rateUnit: "条/秒",
      current: firstPositiveNumber(numberField(progress, "scanned"), resultNumberField(status, "scanned")),
      total: firstPositiveNumber(
        numberField(progress, "api_reported_total"),
        numberField(progress, "filter_window_count"),
        resultNumberField(status, "api_reported_total"),
        resultNumberField(status, "filter_window_count"),
      ),
      elapsedSeconds,
      progress,
      status,
    });
  }
  if (code === "CONTEXT_FIELDS") {
    return buildSyncStageMetric({
      kind: "fields",
      label: "官方字段缓存",
      rateLabel: "字段刷新速率",
      unit: "个官方字段",
      rateUnit: "个/秒",
      current: firstPositiveNumber(numberField(progress, "fields_count"), resultNumberField(status, "fields_count")),
      total: firstPositiveNumber(numberField(progress, "fields_total"), resultNumberField(status, "fields_total")),
      elapsedSeconds,
      progress,
      status,
    });
  }
  if (code === "CONTEXT_OPERATORS") {
    return buildSyncStageMetric({
      kind: "operators",
      label: "官方算子缓存",
      rateLabel: "算子刷新速率",
      unit: "个官方算子",
      rateUnit: "个/秒",
      current: firstPositiveNumber(numberField(progress, "operators_count"), resultNumberField(status, "operators_count")),
      total: firstPositiveNumber(numberField(progress, "operators_total"), resultNumberField(status, "operators_total")),
      elapsedSeconds,
      progress,
      status,
    });
  }
  if (code === "CONTEXT_DATASETS") {
    return buildSyncStageMetric({
      kind: "datasets",
      label: "官方数据集缓存",
      rateLabel: "数据集刷新速率",
      unit: "个官方数据集",
      rateUnit: "个/秒",
      current: firstPositiveNumber(numberField(progress, "datasets_count"), resultNumberField(status, "datasets_count")),
      total: firstPositiveNumber(numberField(progress, "datasets_total"), resultNumberField(status, "datasets_total")),
      elapsedSeconds,
      progress,
      status,
    });
  }
  return buildSyncStageMetric({
    kind: "other",
    label: "当前阶段",
    rateLabel: "处理速率",
    unit: "项",
    rateUnit: "项/秒",
    current: 0,
    total: 0,
    elapsedSeconds,
    progress,
    status,
  });
}

function buildSyncStageMetric({
  kind,
  label,
  rateLabel,
  unit,
  rateUnit,
  current,
  total,
  elapsedSeconds,
  progress,
  status,
}: {
  kind: SyncStageKind;
  label: string;
  rateLabel: string;
  unit: string;
  rateUnit: string;
  current: number;
  total: number;
  elapsedSeconds: number;
  progress?: Record<string, unknown>;
  status: JobStatus | null;
}): SyncStageMetric {
  const etaSeconds = kind !== "scan" && current > 0 && total > current
    ? firstPositiveNumber(numberField(progress, "eta_seconds"), resultNumberField(status, "eta_seconds"))
    : 0;
  const reportedRate = firstPositiveFloat(numberField(progress, "rate_per_second"), resultNumberField(status, "rate_per_second"));
  const derivedRate = current > 0 && elapsedSeconds > 0 ? current / elapsedSeconds : 0;
  return {
    kind,
    label,
    rateLabel,
    unit,
    rateUnit,
    current: Math.max(0, Math.trunc(current || 0)),
    total: Math.max(0, Math.trunc(total || 0)),
    elapsedSeconds,
    etaSeconds,
    ratePerSecond: firstPositiveFloat(reportedRate, derivedRate),
    pageNumber: firstPositiveNumber(numberField(progress, "pages_fetched"), numberField(progress, "page_number")),
    expectedPages: firstPositiveNumber(numberField(progress, "expected_pages")),
    pageSize: firstPositiveNumber(numberField(progress, "page_size")),
    pageLimit: firstPositiveNumber(numberField(progress, "page_limit")),
    nextOffset: firstPositiveNumber(numberField(progress, "next_offset")),
    newUniqueItems: firstPositiveNumber(numberField(progress, "new_unique_items")),
    uniqueItems: firstPositiveNumber(numberField(progress, "unique_items")),
    confirmingTotalBoundary: Boolean(progress?.confirming_total_boundary),
  };
}

function scanEtaDetail(stage: SyncStageMetric) {
  if (stage.current <= 0) {
    return "正在扫描云端 Alpha；等待官方接口返回第一页和接口分页参考数；首次全量同步可能需要 3-5 分钟，近 3/7 天范围通常更快。";
  }
  if (stage.total > 0) {
    return `接口分页参考数 ${formatCount(stage.total)} 条；${syncStagePageSummary(stage)}`;
  }
  return `已拉取 ${formatCount(stage.current)} 条云端 Alpha；接口分页参考数仍在确认，会按分页返回继续读取。`;
}

export function syncScanPageSummary(status: JobStatus | null) {
  return syncStagePageSummary(syncStageMetric(status));
}

function syncStagePageSummary(stage: SyncStageMetric) {
  const page = stage.pageNumber > 0
    ? `当前第 ${formatCount(stage.pageNumber)} 页`
    : "分页页码确认中";
  const parts = [page];
  if (stage.pageSize > 0) parts.push(`本页 ${formatCount(stage.pageSize)} 条`);
  if (stage.pageLimit > 0) parts.push(`分页参数 ${formatCount(stage.pageLimit)} 条/页`);
  if (stage.nextOffset > 0) parts.push(syncNextOffsetLabel(stage.nextOffset, stage.total));
  if (stage.newUniqueItems > 0) parts.push(`本页新增 ${formatCount(stage.newUniqueItems)} 条`);
  if (stage.uniqueItems > 0) parts.push(`已确认唯一 ${formatCount(stage.uniqueItems)} 条`);
  if (stage.confirmingTotalBoundary) parts.push("本页已满，继续确认下一页");
  return parts.join("；");
}

function syncNextOffsetLabel(nextOffset: number, filterWindowCount: number) {
  if (filterWindowCount > 0 && nextOffset >= filterWindowCount) {
    return "下一请求确认分页边界";
  }
  return "下一轮继续拉取";
}

export function syncStageCode(status: JobStatus | null) {
  return String(status?.progress?.status_code || status?.phase || status?.progress?.phase || "context_refresh").toUpperCase();
}

export function phaseLabel(status: JobStatus | null) {
  const code = String(status?.progress?.status_code || status?.phase || status?.progress?.phase || "context_refresh");
  const normalizedCode = code.toUpperCase();
  const labels: Record<string, string> = {
    AUTH: "认证",
    SCAN: "扫描云端",
    MERGE: "合并快照",
    CONTEXT_FIELDS: "刷新字段",
    CONTEXT_OPERATORS: "刷新算子",
    CONTEXT_DATASETS: "刷新数据集",
    CONTEXT_FAILED: "上下文失败",
    CONTEXT_REFRESH: "刷新上下文",
    REFRESH_CONTEXT: "刷新上下文",
    LOCAL_CACHE: "本地缓存",
    LOCAL_CACHE_INVALID: "缓存需刷新",
    SESSION_INVALID: "需要重新连接",
    COMPLETED: "完成",
    COMPLETED_WITH_WARNINGS: "带警告完成",
    QUEUED: "已排队",
    RUNNING: "运行中",
    STOPPED: "已停止",
    FAILED: "失败",
  };
  return labels[normalizedCode] || "当前阶段";
}

export function fieldFromProgress(status: JobStatus | null, field: string) {
  const fromProgress = numberField(status?.progress, field);
  if (fromProgress > 0) return String(fromProgress);
  const result = isRecord(status?.result) ? status.result : undefined;
  const fromResult = Number(result?.[field]);
  if (Number.isFinite(fromResult) && fromResult > 0) return String(fromResult);
  const fromCache = contextCacheNumber(status?.official_context_cache, field);
  return fromCache > 0 ? String(fromCache) : "-";
}

export function contextSummaryField(status: JobStatus | null, field: string) {
  const value = contextSummaryNumber(status, field);
  return value > 0 ? String(value) : "-";
}

export function officialContextSummaryMessage(status: JobStatus | null) {
  const cache = status?.official_context_cache;
  const cacheCounts = {
    fields: contextCacheNumber(cache, "fields_count"),
    operators: contextCacheNumber(cache, "operators_count"),
    datasets: contextCacheNumber(cache, "datasets_count"),
  };
  const displayCounts = {
    fields: contextSummaryNumber(status, "fields_count"),
    operators: contextSummaryNumber(status, "operators_count"),
    datasets: contextSummaryNumber(status, "datasets_count"),
  };
  const hasCache = cacheCounts.fields > 0 || cacheCounts.operators > 0 || cacheCounts.datasets > 0;
  const hasDisplayCounts = displayCounts.fields > 0 || displayCounts.operators > 0 || displayCounts.datasets > 0;
  const cacheError = typeof cache?.error === "string" ? cache.error.trim() : "";
  const cacheCompleteVal = contextCacheComplete(cache);
  const statusMessage = status
    ? operationStatusMessage(status)
    : "尚未启动官方上下文刷新。";
  if (cacheError && !hasCache) {
    return `${statusMessage} 本地官方上下文缓存摘要读取失败，请点击开始刷新或稍后重试。`;
  }
  if (cache && !cacheCompleteVal && !hasDisplayCounts) {
    const invalid = cache.manifest?.invalid_files?.length
      ? `异常文件: ${cache.manifest.invalid_files.join("、")}`
      : "缓存文件数量或校验和不一致";
    return `${statusMessage} 本地官方上下文缓存完整性未通过，已停止加载展示；请点击开始刷新。${invalid}。`;
  }
  if (!hasCache && !hasDisplayCounts) return statusMessage;
  const stale = Boolean(cache?.manifest?.is_stale);
  const cacheLabel = stale ? "本地缓存存在但需要刷新" : "本地缓存可用";
  const countSourceLabel = cacheCompleteVal ? cacheLabel : "本次刷新结果";
  const counts = cacheCompleteVal ? cacheCounts : displayCounts;
  const cacheText = `${countSourceLabel}: 字段 ${formatCount(counts.fields)}，算子 ${formatCount(counts.operators)}，数据集 ${formatCount(counts.datasets)}`;
  const statusText = String(status?.status || "");
  const state = classifyJobState(status);
  if (state.failed || state.interrupted) {
    return `最近刷新未完成: ${statusMessage}；${cacheText}。`;
  }
  if (!status || statusText === "idle") return `${statusMessage} ${cacheText}。`;
  return `${statusMessage} ${cacheText}。`;
}

export function officialContextInlineSummary(status: JobStatus | null) {
  const fields = contextSummaryField(status, "fields_count");
  const operators = contextSummaryField(status, "operators_count");
  const datasets = contextSummaryField(status, "datasets_count");
  const contextError = String(status?.progress?.context_error || resultStringField(status, "context_error") || "").trim();
  if (fields === "-" && operators === "-" && datasets === "-") {
    return "暂无通过完整性校验的官方上下文缓存统计，等待同步状态返回或手动刷新。";
  }
  if (contextError) {
    return `上下文刷新未完成，可仅重试上下文；当前缓存：字段 ${fields}，算子 ${operators}，数据集 ${datasets}。`;
  }
  if (!status) return "启动后这里会显示字段、算子和数据集缓存的快速摘要。";
  return `快速摘要：字段 ${fields}，算子 ${operators}，数据集 ${datasets}。`;
}

export function canRetryContextOnly(status: JobStatus | null) {
  if (!status) return false;
  const result = isRecord(status.result) ? status.result : {};
  const contextStatus = String(status.progress?.context_status || result.context_status || "").toLowerCase();
  const contextError = String(status.progress?.context_error || result.context_error || "").trim();
  return Boolean(contextError || contextStatus === "failed");
}

export function contextSummaryNumber(status: JobStatus | null, field: string) {
  return firstPositiveNumber(
    contextCacheNumber(status?.official_context_cache, field),
    numberField(status?.progress, field),
    resultNumberField(status, field),
  );
}

export function contextCacheNumber(cache: OfficialContextCache | undefined, field: string) {
  if (!contextCacheComplete(cache)) return 0;
  return firstPositiveNumber(
    isRecord(cache) ? numberField(cache, field) : 0,
    contextCacheManifestRecordCount(cache, field),
  );
}

function contextCacheManifestRecordCount(cache: OfficialContextCache | undefined, field: string) {
  const filename = {
    fields_count: "official_fields.json",
    operators_count: "official_operators.json",
    datasets_count: "official_datasets.json",
  }[field];
  return filename ? numberField(cache?.manifest?.record_counts, filename) : 0;
}

export function cloudAlphaCacheReady(cache: CloudAlphaCache | undefined) {
  if (!cache?.ok) return false;
  const count = firstPositiveNumber(cache.count, cache.total);
  return count > 0 || (cache.count == null && cache.total == null);
}

export function cloudAlphaCacheUpdatedAt(cache: CloudAlphaCache | undefined) {
  const loadedAt = Date.parse(String(cache?.loaded_at || ""));
  return Number.isFinite(loadedAt) ? new Date(loadedAt) : null;
}

export function resultNumberField(status: JobStatus | null, field: string) {
  const result = status?.result;
  if (!isRecord(result)) return 0;
  const value = Number(result[field]);
  return Number.isFinite(value) ? value : 0;
}

export function resultStringField(status: JobStatus | null, field: string) {
  const result = status?.result;
  if (!isRecord(result)) return "";
  return String(result[field] || "");
}

export function firstPositiveNumber(...values: Array<number | null | undefined>) {
  const value = values.find((item) => Number.isFinite(item) && Number(item) > 0);
  return Number.isFinite(value) ? Number(value) : 0;
}

export function numberField(source: Record<string, unknown> | undefined, field: string) {
  const value = Number(source?.[field]);
  return Number.isFinite(value) ? value : 0;
}

export function stringField(source: Record<string, unknown> | undefined, field: string) {
  const value = source?.[field];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function booleanField(source: Record<string, unknown> | undefined, field: string) {
  const value = source?.[field];
  return typeof value === "boolean" ? value : undefined;
}

function userErrorField(source: Record<string, unknown> | undefined) {
  const value = source?.user_error;
  return value && typeof value === "object" ? value as UnifiedProgress["user_error"] : undefined;
}

export function syncStatusUpdatedAt(status: JobStatus | null) {
  const progressUpdated = numberField(status?.progress, "updated_at_ms");
  if (progressUpdated > 0) return new Date(progressUpdated);
  const resultUpdated = resultNumberField(status, "updated_at_ms");
  if (resultUpdated > 0) return new Date(resultUpdated);
  const startedAt = Date.parse(String(status?.started_at || ""));
  if (Number.isFinite(startedAt)) return new Date(startedAt);
  return status ? new Date() : null;
}

export function isSessionInvalidResult(result: ({ ok?: boolean; error_code?: string; error?: string } & Partial<JobStatus>) | null) {
  if (!result || result.ok !== false) return false;
  const errorCode = String(result.error_code || "").toUpperCase();
  const error = String(result.error || "").toLowerCase();
  return errorCode === "SESSION_INVALID" || error.includes("session_invalid") || error.includes("invalid local session");
}

export function syncHistoryReadErrorTitle(raw: unknown) {
  return readableBackendText(raw) || "同步历史读取受限，无法展示原始错误详情。";
}

function readableBackendText(raw: unknown) {
  const value = String(raw || "").trim();
  const sharedMessage = knownApiErrorMessage(value);
  if (sharedMessage) return sharedMessage;
  const fieldRefreshMatch = value.match(/^Updating official fields cache:\s*(.+)$/);
  if (fieldRefreshMatch) return `正在刷新官方字段缓存: ${fieldRefreshMatch[1]}`;
  const operatorRefreshMatch = value.match(/^Updating official operators cache:\s*(.+)$/);
  if (operatorRefreshMatch) return `正在刷新官方算子缓存: ${operatorRefreshMatch[1]}`;
  const labels: Record<string, string> = {
    "Official context refreshed.": "官方上下文已刷新。",
    "candidate family lacks official simulation metrics": "候选族缺少官方仿真指标",
    "official context timeout": "官方上下文刷新超时，请稍后重试。",
    "unknown sync job": "找不到本次同步任务，请重新启动刷新。",
    "unknown job": "找不到本次任务，请重新启动流程。",
    JOB_NOT_FOUND: "找不到本次任务，请重新启动流程。",
    SESSION_INVALID: "本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。",
    "invalid local session": "本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。",
    OFFICIAL_CONTEXT_REFRESH_TIMEOUT: "官方上下文刷新超时，请稍后重试。",
  };
  if (labels[value]) return labels[value];
  if (isAllowedOfficialStatusText(value)) return value;
  return null;
}

function isAllowedOfficialStatusText(value: string) {
  if (!value) return false;
  return [
    /^官方上下文已刷新/,
    /^官方上下文刷新/,
    /^官方上下文刷新已停止/,
    /^正在刷新官方字段缓存/,
    /^正在刷新官方算子缓存/,
    /^云端同步完成/,
    /^连续读取刷新状态失败/,
    /^用户已停止本次官方上下文刷新/,
  ].some((pattern) => pattern.test(value));
}
