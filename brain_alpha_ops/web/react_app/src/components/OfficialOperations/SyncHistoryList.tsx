/** Sync history list display component. */

import type { SyncHistoryItem } from "@/types";
import { classifyJobState } from "@/helpers/runPayload";
import { formatClock, formatCount, shortOperationId } from "./utils";

function syncHistoryStatusLabel(status: string) {
  const value = String(status || "").toLowerCase();
  const labels: Record<string, string> = {
    completed: "已完成",
    completed_with_warnings: "带警告",
    failed: "失败",
    running: "进行中",
    queued: "已排队",
    stopping: "停止中",
    stopped: "已停止",
    cancelled: "已取消",
    canceled: "已取消",
    idle: "待启动",
  };
  return labels[value] || "状态待确认";
}

function syncHistoryDotTone(status: string) {
  const state = classifyJobState({ status });
  if (state.successful && !state.warning) return "status-dot-active";
  if (state.warning || state.active) return "status-dot-warning";
  if (state.failed || state.interrupted || state.missing) return "status-dot-error";
  return "status-dot-idle";
}

function syncHistoryDate(row: SyncHistoryItem) {
  const ms = firstPositiveNumber(row.updated_at_ms, row.updated_at ? row.updated_at * 1000 : 0);
  return ms > 0 ? new Date(ms) : null;
}

function firstPositiveNumber(...values: Array<number | null | undefined>) {
  const value = values.find((item) => Number.isFinite(item) && Number(item) > 0);
  return Number.isFinite(value) ? Number(value) : 0;
}

function phaseLabel(status: { job_id?: string; status?: string; phase?: string }) {
  const code = String(status?.phase || "idle");
  const labels: Record<string, string> = {
    context_refresh: "刷新上下文",
    scan: "扫描云端",
    context_fields: "刷新字段",
    context_operators: "刷新算子",
    context_datasets: "刷新数据集",
  };
  return labels[code.toLowerCase()] || "当前阶段";
}

interface SyncHistoryListProps {
  rows: SyncHistoryItem[];
}

export default function SyncHistoryList({ rows }: SyncHistoryListProps) {
  return (
    <ul className="mt-3 divide-y divide-border-subtle rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)]" aria-label="最近官方同步列表">
      {rows.slice(0, 5).map((row) => (
        <li key={row.job_id} className="grid gap-3 p-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`status-dot ${syncHistoryDotTone(row.status)}`} aria-hidden="true" />
              <span className="text-sm font-semibold text-text-primary">{syncHistoryStatusLabel(row.status)}</span>
              <span className="badge badge-neutral text-xs">{row.context_only ? "仅上下文" : "云端同步"}</span>
              <span className="font-mono-value text-xs text-text-tertiary" title={row.job_id}>{shortOperationId(row.job_id)}</span>
            </div>
            <p className="mt-1 break-words text-sm leading-6 text-text-secondary">
              {syncHistoryMessage(row)}
            </p>
          </div>
          <time className="text-xs text-text-tertiary sm:text-right" dateTime={syncHistoryDate(row)?.toISOString()}>
            {syncHistoryDate(row) ? formatClock(syncHistoryDate(row) as Date) : "-"}
          </time>
        </li>
      ))}
    </ul>
  );
}

function syncHistoryMessage(row: SyncHistoryItem) {
  const explicit = readableBackendText(row.status_message || "");
  const scanned = firstPositiveNumber(row.scanned);
  const total = firstPositiveNumber(row.api_reported_total, row.filter_window_count, row.total);
  const deltas = [
    row.added && row.added > 0 ? `新增 ${formatCount(row.added)}` : "",
    row.updated && row.updated > 0 ? `更新 ${formatCount(row.updated)}` : "",
    row.skipped && row.skipped > 0 ? `跳过 ${formatCount(row.skipped)}` : "",
    row.failed && row.failed > 0 ? `失败 ${formatCount(row.failed)}` : "",
  ].filter(Boolean);
  const scanText = scanned > 0 && total > 0
    ? `已拉取 ${formatCount(scanned)} 条；分页参考数 ${formatCount(total)} 条`
    : scanned > 0
      ? `已拉取 ${formatCount(scanned)} 条`
      : "";
  const parts = [scanText, deltas.length ? deltas.join("，") : ""].filter(Boolean);
  if (explicit && parts.length) return `${explicit}；${parts.join("；")}。`;
  if (explicit) return explicit;
  if (parts.length) return `${parts.join("；")}。`;
  return row.phase ? `阶段: ${phaseLabel({ job_id: row.job_id, status: "idle", phase: row.phase })}` : "暂无同步摘要。";
}

function readableBackendText(raw: unknown) {
  const value = String(raw || "").trim();
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
