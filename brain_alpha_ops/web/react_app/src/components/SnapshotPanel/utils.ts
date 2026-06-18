/** Shared utilities for SnapshotPanel sub-components. */

import { knownApiErrorMessage } from "@/helpers/errorExperience";

export const MAX_FILTER_LENGTH = 200;
export const RAW_SNAPSHOT_TEXT_PATTERN = /(?:raw\s+backend|raw_backend|RAW_BACKEND|SESSION_INVALID|session_invalid|invalid local session|unknown sync job|unknown job|csrf[_-]?token|session[_-]?id|access[_-]?token|refresh[_-]?token|password|passwd|pwd|set[_-]?cookie|cookie|authorization|client[_-]?secret|api[_-]?key)/i;
export const LOCAL_SNAPSHOT_PATH_PATTERN = /(?:\/Users\/|\/Volumes\/|\/private\/tmp\/|\/tmp\/|[A-Za-z]:\\|run_history\.json|Traceback|File\s+")/i;

export const SNAPSHOT_STATUS_LABELS: Record<string, string> = {
  active: "活跃",
  analytics: "趋势",
  blocked: "已阻断",
  cancelled: "已取消",
  canceled: "已取消",
  completed: "已完成",
  complete: "已完成",
  delta: "变化",
  done: "已完成",
  error: "错误",
  fail: "失败",
  failed: "失败",
  false: "未通过",
  missing: "缺失",
  pass: "通过",
  passed: "通过",
  pending: "等待中",
  production: "生产中",
  queued: "排队中",
  ready: "就绪",
  recorded: "已记录",
  rejected: "已拒绝",
  resume_available: "可续跑",
  review: "复核中",
  running: "运行中",
  stale: "需刷新",
  stopped: "已停止",
  submitted: "已提交",
  success: "成功",
  true: "通过",
  unknown: "状态待确认",
  warn: "警告",
  warning: "警告",
};

export type SnapshotRow = {
  id: string;
  kind: string;
  title: string;
  status: string;
  metric: string;
  detail: string;
  timestamp: string;
};

export type SnapshotMetric = {
  label: string;
  value: string;
};

export function text(value: unknown): string {
  if (value === undefined || value === null) return "";
  return String(value);
}

export function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function truthy(value: unknown): boolean {
  return value === true || value === "true" || value === "True" || value === 1 || value === "1";
}

export function safeSnapshotDisplayText(value: unknown, fallback: string): string {
  const raw = text(value).trim();
  if (!raw) return "";
  if (knownApiErrorMessage(raw) || RAW_SNAPSHOT_TEXT_PATTERN.test(raw) || LOCAL_SNAPSHOT_PATH_PATTERN.test(raw)) return fallback;
  return raw;
}

export function snapshotStatusLabel(value: unknown): string {
  const raw = text(value).trim();
  if (!raw) return "";
  const known = knownApiErrorMessage(raw);
  if (known) return known;
  if (RAW_SNAPSHOT_TEXT_PATTERN.test(raw)) return "状态待确认";
  const normalized = raw.toLowerCase();
  return SNAPSHOT_STATUS_LABELS[normalized] || "状态待确认";
}

export function safeSnapshotDetail(value: unknown): string {
  const raw = text(value).trim();
  if (!raw) return "";
  const known = knownApiErrorMessage(raw);
  if (known) return known;
  if (RAW_SNAPSHOT_TEXT_PATTERN.test(raw) || LOCAL_SNAPSHOT_PATH_PATTERN.test(raw)) return "详情待确认";
  return raw;
}

export function statusBadge(status: string): string {
  const normalized = status.toLowerCase();
  if (["ready", "pass", "passed", "true", "submitted", "production", "就绪", "通过", "已提交", "生产中", "成功", "已完成", "活跃", "可续跑"].some((item) => normalized.includes(item))) return "badge badge-positive";
  if (["fail", "false", "missing", "blocked", "error", "rejected", "失败", "未通过", "缺失", "阻断", "错误", "已拒绝"].some((item) => normalized.includes(item))) return "badge badge-negative";
  if (["warn", "stale", "caution", "unknown", "警告", "需刷新", "需注意", "状态待确认"].some((item) => normalized.includes(item))) return "badge badge-warning";
  return "badge badge-neutral";
}

export function isSnapshotPassStatus(status: string): boolean {
  return ["pass", "passed", "ready", "true", "通过", "成功", "已完成", "就绪"].includes(status.trim().toLowerCase());
}

export function metricText(label: string, value: unknown): string {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "number") return `${label}:${Number.isInteger(value) ? value : value.toFixed(3)}`;
  const parsed = Number(value);
  if (Number.isFinite(parsed) && String(value).trim() !== "") return `${label}:${Number.isInteger(parsed) ? parsed : parsed.toFixed(3)}`;
  return `${label}:${text(value)}`;
}

export function ratioText(numerator: unknown, denominator: unknown): string {
  return `${countText(numerator)}/${countText(denominator)}`;
}

export function countText(value: unknown): string {
  if (value === undefined || value === null || value === "") return "0";
  const parsed = Number(value);
  if (Number.isFinite(parsed)) return String(Number.isInteger(parsed) ? parsed : Number(parsed.toFixed(3)));
  return safeSnapshotDisplayText(value, "0") || "0";
}

export function sanitizeTextInput(value: string, maxLength: number): string {
  return value.replace(/[\x00-\x1F\x7F]/g, "").slice(0, maxLength);
}

export function formatOptionalNumber(value: unknown): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(3);
}

export function formatLocalBacktestStatus(value: unknown, hasEvidence: boolean): string {
  if (!hasEvidence) return "-";
  if (value === true) return "通过";
  if (value === false) return "未通过";
  return "-";
}
