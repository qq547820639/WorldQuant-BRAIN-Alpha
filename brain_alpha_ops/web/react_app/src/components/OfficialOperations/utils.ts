/** Shared utilities for OfficialOperationsPanel sub-components. */

import type { BrainCredentials, JobStatus } from "@/types";

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
    } catch { /* ignore */ }
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
  } catch { /* ignore */ }
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
  const error = (result as Record<string, unknown>)?.error;
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
