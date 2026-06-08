/** Unified progress and loading feedback — Terminal Precision design */
import { useEffect, useMemo, useState, useRef } from "react";
import type { ProgressLifecycle, UnifiedProgress } from "@/types";

interface Props {
  state: ProgressLifecycle;
  title?: string;
  progress?: UnifiedProgress | null;
  error?: string | null;
  idleText?: string;
  successText?: string;
  retryLabel?: string;
  compact?: boolean;
  onRetry?: () => void;
}

export default function ProgressFeedback({
  state, title = "进度", progress, error,
  idleText = "就绪", successText = "完成",
  retryLabel = "重试", compact = false, onRetry,
}: Props) {
  const [remaining, setRemaining] = useState(() => Number(progress?.eta_seconds || 0));
  const [elapsed, setElapsed] = useState(0);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const startedAtRef = useRef(Date.now());

  useEffect(() => { setRemaining(Number(progress?.eta_seconds || 0)); }, [progress?.eta_seconds, progress?.task_id, progress?.job_id]);

  useEffect(() => {
    if (state === "idle") { startedAtRef.current = Date.now(); return; }
    if (state === "loading" || state === "progress") {
      if (lastUpdatedAt === null) startedAtRef.current = Date.now();
    }
    setLastUpdatedAt(new Date());
  }, [error, progress?.message, progress?.phase, progress?.status, progress?.status_message, progress?.percent, progress?.percent_complete, state]);

  useEffect(() => {
    if (state !== "loading" && state !== "progress") return;
    if (!remaining || remaining <= 0) return;
    const timer = setInterval(() => setRemaining((v) => Math.max(0, v - 1)), 1000);
    return () => clearInterval(timer);
  }, [remaining, state]);

  // Elapsed timer
  useEffect(() => {
    if (state !== "loading" && state !== "progress") { setElapsed(0); return; }
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [state]);

  const percent = useMemo(() => normalizedPercent(progress), [progress]);
  const roundedPercent = percent == null ? 0 : Math.round(percent);
  const isBusy = state === "loading" || state === "progress";
  const isDeterminate = isBusy && percent != null;
  const label = progress?.phase_label || progress?.phase || title;
  const message = progress?.status_message || progress?.message || statusText(state, idleText, successText);
  const eta = remaining > 0 ? fmtDuration(remaining) : "";

  // Stall detection: >10s elapsed with no progress (0% and scanning)
  const isStalled = isBusy && !isDeterminate && elapsed > 10;
  const scanCount = progress?.scanned != null ? `${progress.scanned} / ${progress.total || "—"}` : null;

  if (state === "idle" && compact) return null;

  const errorBorder = state === "error" ? { borderColor: "oklch(0.48 0.08 22 / 0.30)", background: "oklch(0.48 0.06 22 / 0.08)" } : {};
  const successBorder = state === "success" ? { borderColor: "oklch(0.52 0.06 155 / 0.30)", background: "oklch(0.52 0.06 155 / 0.08)" } : {};
  const stallBorder = isStalled ? { borderColor: "oklch(0.65 0.08 85 / 0.30)", background: "oklch(0.65 0.06 85 / 0.06)" } : {};

  return (
    <div
      className="panel animate-fade-in"
      style={{ marginBottom: 16, ...errorBorder, ...successBorder, ...stallBorder }}
      role={isBusy ? "status" : undefined}
      aria-live={state === "error" ? "assertive" : "polite"}
    >
      <div className={`panel-body-${compact ? "compact" : "padded"}`}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 12 }}>
          <div style={{ minWidth: 0 }}>
            <p className="text-base font-medium text-text-primary">{title}</p>
            <p className="text-sm text-text-tertiary mt-1">{label}</p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            {isBusy && percent == null && <span className="spinner" />}
            {isBusy && percent != null && (
              <span className="text-sm tabular text-accent font-medium">{roundedPercent}%</span>
            )}
            {state === "success" && (
              <span style={{ width: 24, height: 24, borderRadius: "50%", background: "oklch(0.52 0.06 155 / 0.18)", display: "flex", alignItems: "center", justifyContent: "center", color: "oklch(0.62 0.10 160)", fontSize: 12, fontWeight: 600 }} aria-hidden="true">&#10003;</span>
            )}
          </div>
        </div>

        {/* Progress bar */}
        {isBusy && (
          <div className={`progress-bar ${isDeterminate ? "" : "indeterminate"}`}
            role="progressbar"
            aria-label={`${title}: ${label}`}
            aria-valuemin={0} aria-valuemax={100}
            aria-valuenow={isDeterminate ? roundedPercent : undefined}
            style={{ marginBottom: 12 }}
          >
            <div className={`progress-bar-fill${isStalled ? " warning" : ""}`} style={isDeterminate ? { width: `${percent}%` } : undefined} />
          </div>
        )}

        {/* Message + stall warning */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, fontSize: "0.8125rem", lineHeight: 1.6, color: "oklch(0.72 0.005 45)" }}>
            <span className="min-w-0 break-words">
              {state === "error" ? (error || progress?.error || "操作失败。") : message}
            </span>
            <span style={{ display: "flex", gap: 12 }}>
              {scanCount && <span style={{ color: "oklch(0.52 0.006 45)" }}>{scanCount} 条</span>}
              {elapsed > 0 && <span className="tabular" style={{ color: "oklch(0.52 0.006 45)" }}>已耗时 {fmtDuration(elapsed)}</span>}
              {eta && <span className="tabular" style={{ color: "oklch(0.52 0.006 45)" }}>预计剩余 {eta}</span>}
            </span>
          </div>
          {/* Stall warning */}
          {isStalled && (
            <div style={{ fontSize: 12, color: "oklch(0.75 0.10 88)", padding: "4px 0" }}>
              BRAIN 服务器仍在响应中，请耐心等待。
            </div>
          )}
        </div>

        {/* Meta info */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", marginTop: 8, fontSize: "0.75rem", color: "oklch(0.52 0.006 45)" }}>
          {lastUpdatedAt && <span>最后更新 {fmtClock(lastUpdatedAt)}</span>}
          {state === "error" && <span>{interruptionText(error || progress?.error || message, progress?.phase)}</span>}
        </div>

        {/* Recovery actions */}
        {state === "error" && (
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            {onRetry && (
              <button type="button" className="btn btn-primary" onClick={onRetry}>
                {retryLabel}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function normalizedPercent(progress?: UnifiedProgress | null): number | null {
  const raw = progress?.percent_complete ?? progress?.percent;
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    const done = Number(progress?.done ?? progress?.checked ?? progress?.submitted ?? progress?.scanned);
    const total = Number(progress?.total);
    if (Number.isFinite(done) && Number.isFinite(total) && total > 0) return Math.max(0, Math.min(100, (done / total) * 100));
    return null;
  }
  return Math.max(0, Math.min(100, value));
}

function statusText(state: ProgressLifecycle, idle: string, ok: string) {
  if (state === "idle") return idle;
  if (state === "success") return ok;
  if (state === "error") return "操作失败。";
  return "处理中...";
}

function interruptionText(msg: string, phase?: string) {
  const text = String(msg || "");
  const p = humanPhase(phase);
  if (/实时|中断|取消|状态连续刷新失败/.test(text)) return `自动中断原因: ${p || "状态不明确"}`;
  if (p) return `失败阶段: ${p}`;
  return "";
}

function humanPhase(phase?: string) {
  const labels: Record<string, string> = {
    watchdog_failed: "长时间没有明确进度",
    candidate_generation: "候选生成", scoring: "评分",
    checking: "提交前检查", submitting: "提交请求", failed: "流程失败",
  };
  return labels[String(phase || "").toLowerCase()] || "";
}

function fmtClock(d: Date) {
  return d.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDuration(s: number) {
  const safe = Math.max(0, Math.round(s));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}
