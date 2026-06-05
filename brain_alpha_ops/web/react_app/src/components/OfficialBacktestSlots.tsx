/** Read-only rendering for the three independent official backtest slots. */

import { useCallback, useEffect } from "react";
import { useApi } from "@/hooks/useApi";
import type { BacktestQueueSummary, BacktestSlot, BacktestSlotsResponse } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

const POLL_INTERVAL_MS = 5000;

export default function OfficialBacktestSlots({ notify }: Props) {
  const api = useApi<BacktestSlotsResponse>();
  const callApi = api.call;

  const load = useCallback(async () => {
    const result = await callApi<BacktestSlotsResponse>("/api/backtest_slots");
    if (result?.error) notify("error", result.error);
  }, [callApi, notify]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => { void load(); }, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const slots = normalizeSlots(api.data);
  const slotLimit = backtestSlotLimit(api.data);
  const activeCount = slots.filter((slot) => isActiveSlot(slot.status)).length;
  const queueSummary = api.data?.queue_summary;

  if (api.loading && !api.data) {
    return (
      <ProgressFeedback
        state="loading"
        title="官方回测"
        progress={{ phase: "backtest_slots_load", status_message: "正在加载官方回测槽位。" }}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-4 animate-fade-in">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-gray-100">官方回测槽位</h2>
          <p className="text-xs text-muted">活跃 {activeCount}/{slotLimit}</p>
        </div>
        <p className="text-xs text-muted" role="status" aria-live="polite">
          {api.data?.updated_at || api.data?.source || "本地快照"}
        </p>
      </div>

      <BacktestQueueSummaryStrip summary={queueSummary} activeCount={activeCount} slotLimit={slotLimit} />

      {api.error && (
        <div className="card border-danger/40 bg-danger/10" role="alert" aria-live="assertive">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-danger">回测槽位加载失败: {api.error}</p>
            <button type="button" onClick={load} className="btn-secondary text-sm">
              重试
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {slots.map((slot) => (
          <article key={slot.slot} className={`card min-w-0 border-l-4 ${slotTone(slot.status)}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-gray-100">官方回测槽 #{slot.slot}</h3>
                <p className="mt-1 text-xs text-muted">{slot.message || slotMessage(slot.status)}</p>
              </div>
              <span
                className={`badge max-w-[9rem] truncate text-xs ${slotBadge(slot.status)}`}
                title={String(slot.status || "EMPTY")}
              >
                {slotStatusLabel(slot.status)}
              </span>
            </div>

            <dl className="mt-4 space-y-2 text-xs">
              <SlotMetric label="Alpha ID" value={slot.alpha_id || "-"} mono />
              <SlotMetric label="仿真 ID" value={slot.simulation_id || "-"} mono />
              <SlotMetric label="官方 ID" value={slot.official_alpha_id || "-"} mono />
              <SlotMetric label="得分" value={slot.score == null ? "-" : Number(slot.score).toFixed(2)} />
              <SlotMetric label="轮询次数" value={String(slot.poll_count ?? 0)} />
              <SlotMetric label="下次轮询" value={formatSeconds(slot.next_poll_seconds)} />
            </dl>

            <div className="mt-4 h-2 overflow-hidden rounded-full bg-gray-800" aria-hidden="true">
              <div
                className="h-full rounded-full bg-brand-500"
                style={{ width: `${boundedPercent(slot.progress_percent)}%` }}
              />
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function BacktestQueueSummaryStrip({
  summary,
  activeCount,
  slotLimit,
}: {
  summary?: BacktestQueueSummary;
  activeCount: number;
  slotLimit: number;
}) {
  const openSlots = summary?.open_slot_count ?? Math.max(0, slotLimit - activeCount);
  const reviewBlockers = (summary?.top_blocking_reasons || [])
    .slice(0, 3)
    .map((row) => `${row.reason} ${row.count}`)
    .join(" · ");
  const submitBlockers = (summary?.top_submit_blocking_reasons || [])
    .slice(0, 3)
    .map((row) => `${row.reason} ${row.count}`)
    .join(" · ");
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2">
      <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <QueueMetric label="Open slots" value={`${openSlots}/${slotLimit}`} />
        <QueueMetric label="Submit evidence" value={formatCount(summary?.submit_evidence_blocking_count)} />
        <QueueMetric label="Live API" value={summary?.official_api_called ? "called" : "not called"} />
        <QueueMetric label="Slot records" value={formatCount(summary?.official_slot_record_count)} />
      </dl>
      <p className="mt-2 truncate text-xs text-muted" title={reviewBlockers || "none"}>
        Review blockers: {reviewBlockers || "none"}
      </p>
      <p className="mt-1 truncate text-xs text-muted" title={submitBlockers || "none"}>
        Submit evidence: {submitBlockers || "none"}
      </p>
    </div>
  );
}

function QueueMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted">{label}</dt>
      <dd className="mt-0.5 truncate font-medium text-gray-100" title={value}>{value}</dd>
    </div>
  );
}

function SlotMetric({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className={`min-w-0 truncate text-right text-gray-300 ${mono ? "font-mono" : ""}`} title={value}>
        {value}
      </dd>
    </div>
  );
}

function normalizeSlots(payload: BacktestSlotsResponse | null): BacktestSlot[] {
  const rows = Array.isArray(payload?.slots) ? payload.slots : [];
  return Array.from({ length: backtestSlotLimit(payload) }, (_, index) => index + 1)
    .map((slot) => rows.find((row) => Number(row.slot) === slot) || { slot, status: "EMPTY" });
}

function backtestSlotLimit(payload: BacktestSlotsResponse | null) {
  const fromPayload = Number(payload?.slot_limit);
  const fromSummary = Number(payload?.queue_summary?.slot_limit);
  const value = Number.isFinite(fromPayload) && fromPayload > 0 ? fromPayload : fromSummary;
  return Math.max(3, Number.isFinite(value) && value > 0 ? Math.trunc(value) : 3);
}

function isActiveSlot(status: unknown) {
  const text = String(status || "").toUpperCase();
  return Boolean(text && !["", "EMPTY", "COMPLETED", "FAILED", "ERROR", "CAPACITY_WAIT"].includes(text));
}

function slotTone(status: unknown) {
  const text = String(status || "").toUpperCase();
  if (text === "EMPTY") return "border-gray-700";
  if (text.includes("FAILED") || text.includes("ERROR")) return "border-danger";
  if (text.includes("COMPLETE")) return "border-success";
  if (text.includes("DEFERRED") || text.includes("WAIT")) return "border-warning";
  return "border-blue-400";
}

function slotBadge(status: unknown) {
  const text = String(status || "").toUpperCase();
  if (text === "EMPTY") return "badge-neutral";
  if (text.includes("FAILED") || text.includes("ERROR")) return "badge-danger";
  if (text.includes("COMPLETE")) return "badge-success";
  return "badge-warning";
}

function slotStatusLabel(status: unknown) {
  const text = String(status || "EMPTY").toUpperCase();
  if (text.includes("DEFERRED")) return "已延迟";
  if (text.includes("CONCURRENCY")) return "等待中";
  if (text.includes("RUNNING")) return "运行中";
  if (text.includes("SUBMITTED")) return "已提交";
  if (text.includes("COMPLETE")) return "已完成";
  if (text.includes("FAILED")) return "失败";
  return text || "空闲";
}

function slotMessage(status: unknown) {
  const text = String(status || "EMPTY").toUpperCase();
  if (text === "EMPTY") return "空闲";
  if (text.includes("DEFERRED")) return "等待官方容量";
  if (text.includes("RUNNING") || text.includes("SUBMITTED")) return "官方回测进行中";
  if (text.includes("COMPLETE")) return "官方回测完成";
  return "等待更新";
}

function boundedPercent(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, number));
}

function formatSeconds(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number) || number <= 0) return "-";
  return `${number.toFixed(1)}s`;
}

function formatCount(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return "0";
  return String(Math.max(0, Math.trunc(number)));
}

function nextActionLabel(value: unknown) {
  const text = String(value || "");
  if (text === "trusted_environment_official_simulation_required") return "official review";
  if (text === "wait_for_open_backtest_slot") return "等待槽位";
  if (text === "generate_candidates") return "生成候选";
  if (text === "improve_or_regenerate_candidates") return "改进候选";
  return text || "-";
}
