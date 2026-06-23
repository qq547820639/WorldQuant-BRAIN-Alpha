import { RAW_UNSAFE_DISPLAY_TEXT_PATTERN } from "@/helpers/errorExperience";

const BACKEND_STATUS_CODE_PATTERN = /^[A-Z][A-Z0-9_]{2,}$/;
const SNAKE_STATUS_CODE_PATTERN = /^[a-z]+(?:_[a-z0-9]+)+$/;

const LIFECYCLE_STATUS_LABELS: Record<string, string> = {
  completed: "已完成",
  submission_ready: "待提交复核",
  running_backtest: "回测运行中",
  pending_backtest: "等待回测",
  candidate_pool_retained: "候选池保留",
  local_prefilter_rejected: "本地预筛未通过",
  local_prefilter_passed: "本地预筛通过",
  official_validation_queue: "等待官方验证",
  optimize: "继续优化",
  failed: "未通过",
  blocked: "已阻断",
  running: "运行中",
};

const LOCAL_PREFILTER_STATUSES = new Set([
  "local_prefilter_rejected",
  "local_prefilter_passed",
  "pending_backtest",
  "running_backtest",
]);

export function fmtNum(value: unknown, digits: number) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : "--";
}

export function safeScoringText(value: unknown, fallback: string) {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : fallback;
  if (typeof value === "boolean") return value ? "是" : "否";
  const text = String(value).trim();
  if (!text) return fallback;
  if (isUnsafeScoringText(text)) return fallback;
  return text;
}

function isUnsafeScoringText(text: string) {
  return RAW_UNSAFE_DISPLAY_TEXT_PATTERN.test(text) || BACKEND_STATUS_CODE_PATTERN.test(text);
}

export function lifecycleStatusLabel(value: unknown) {
  const text = String(value || "").trim();
  if (!text) return "--";
  const normalized = text.toLowerCase();
  if (LIFECYCLE_STATUS_LABELS[normalized]) return LIFECYCLE_STATUS_LABELS[normalized];
  if (isUnsafeScoringText(text) || BACKEND_STATUS_CODE_PATTERN.test(text) || SNAKE_STATUS_CODE_PATTERN.test(text)) {
    return "状态待确认";
  }
  return text;
}

export function isLocalPrefilterStatus(status: unknown): boolean {
  return typeof status === "string" && LOCAL_PREFILTER_STATUSES.has(status.toLowerCase());
}

export function metricWithStatus(primary: unknown, status: unknown, fallback: unknown): string | number | undefined {
  return metricValue(primary) ?? metricValue(status) ?? metricValue(fallback);
}

function metricValue(value: unknown): string | number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  return typeof value === "number" || typeof value === "string" ? value : undefined;
}

export function nonEmpty<T>(items?: T[] | null): T[] | null {
  return Array.isArray(items) && items.length ? items : null;
}

export function childNodes(node: { children?: unknown[] }) {
  return Array.isArray(node.children) ? node.children : [];
}
