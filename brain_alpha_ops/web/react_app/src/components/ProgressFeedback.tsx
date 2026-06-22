/** Unified progress and loading feedback — Terminal Precision design */
import { useEffect, useMemo, useState, useRef } from "react";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { classifyProgressState, type JobStateClassification } from "@/helpers/runPayload";
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
  const [remaining, setRemaining] = useState(() => etaSecondsFromProgress(progress));
  const [elapsed, setElapsed] = useState(0);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const startedAtRef = useRef(Date.now());

  useEffect(() => {
    setRemaining(etaSecondsFromProgress(progress));
  }, [progress?.eta_deadline_at_ms, progress?.eta_seconds, progress?.task_id, progress?.job_id]);

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
    const timer = setInterval(() => {
      const deadlineRemaining = etaSecondsFromProgress(progress, { deadlineOnly: true });
      setRemaining((v) => deadlineRemaining > 0 ? deadlineRemaining : Math.max(0, v - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [progress?.eta_deadline_at_ms, remaining, state]);

  // Elapsed timer
  useEffect(() => {
    if (state !== "loading" && state !== "progress") { setElapsed(0); return; }
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [state]);

  const progressState = useMemo(() => classifyProgressState(state, progress), [progress, state]);
  const rawPercent = useMemo(() => normalizedPercent(progress, progressState), [progress, progressState]);
  const percent = state === "success" && rawPercent == null ? 100 : rawPercent;
  const roundedPercent = percent == null ? 0 : Math.round(percent);
  const isBusy = state === "loading" || state === "progress";
  const showProgressBar = isBusy || state === "success" || (state === "error" && percent != null);
  const isDeterminate = showProgressBar && percent != null;
  const label = displayProgressPhase(progress, title);
  const message = safeProgressMessage(progress, state, idleText, successText);
  const openEndedCloudScan = isOpenEndedCloudScan(progress);
  const displayMessage = openEndedCloudScan ? openEndedScanStatusMessage(progress, message) : message;
  const structuredError = useMemo(() => progressUserFacingError(progress), [progress]);
  const displayError = structuredError || error || "操作失败。";
  const cloudScanWithApiTotal = isCloudScanWithApiTotal(progress);
  const estimatedEta = estimatedEtaSeconds(progress, elapsed, remaining);
  const eta = estimatedEta > 0 ? fmtDuration(estimatedEta) : "";

  const isStalled = isBusy && !isDeterminate && !openEndedCloudScan && elapsed > 10;
  const scanCount = scanCountText(progress, openEndedCloudScan);

  if (state === "idle" && compact) return null;

  const errorBorder = state === "error" ? { borderColor: "var(--color-error-border)", background: "var(--color-error-bg)" } : {};
  const successBorder = state === "success" ? { borderColor: "var(--color-success-border)", background: "var(--color-success-bg)" } : {};
  const stallBorder = isStalled ? { borderColor: "var(--color-stall-border)", background: "var(--color-stall-bg)" } : {};
  const badge = progressStatusBadge(state, progress, progressState, percent);
  const fillClass = progressFillClass(state, progress, progressState, isStalled);

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
            <span className={`badge ${badge.className}`}>{badge.label}</span>
            {isBusy && percent == null && <span className="spinner" />}
            {showProgressBar && percent != null && state !== "success" && (
              <span className="text-sm tabular text-accent font-medium">{roundedPercent}%</span>
            )}
            {state === "success" && (
              <span style={{ width: 24, height: 24, borderRadius: "50%", background: "var(--color-success-check-bg)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-status-complete-text)", fontSize: 12, fontWeight: 600 }} aria-hidden="true">&#10003;</span>
            )}
          </div>
        </div>

        {/* Progress bar */}
        {showProgressBar && (
          <div className={`progress-bar ${isDeterminate ? "" : "indeterminate"}`}
            role="progressbar"
            aria-label={`${title}: ${label}`}
            aria-valuemin={0} aria-valuemax={100}
            aria-valuenow={isDeterminate ? roundedPercent : undefined}
            style={{ marginBottom: 12 }}
          >
            <div className={`progress-bar-fill ${fillClass}`} style={isDeterminate ? { width: `${percent}%` } : undefined} />
          </div>
        )}

        {/* Message + stall warning */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, fontSize: "0.8125rem", lineHeight: 1.6, color: "var(--color-text-body)" }}>
            <span className="min-w-0 break-words">
              {state === "error" ? displayError : displayMessage}
            </span>
            <span style={{ display: "flex", gap: 12 }}>
              {scanCount && <span style={{ color: "var(--color-text-muted)" }}>{scanCount}</span>}
              {elapsed > 0 && <span className="tabular" style={{ color: "var(--color-text-muted)" }}>已耗时 {fmtDuration(elapsed)}</span>}
              {eta && <span className="tabular" style={{ color: "var(--color-text-muted)" }}>预计剩余 {eta}</span>}
            </span>
          </div>
          {/* Stall warning */}
          {isStalled && (
            <div style={{ fontSize: 12, color: "var(--color-stall-text)", padding: "4px 0" }}>
              BRAIN 服务器仍在响应中，请耐心等待。
            </div>
          )}
        </div>

        {/* Meta info */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", marginTop: 8, fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
          {lastUpdatedAt && <span>最后更新 {fmtClock(lastUpdatedAt)}</span>}
          {state === "error" && <span>{interruptionText(displayError || displayMessage, progress?.phase)}</span>}
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

function progressStatusBadge(
  state: ProgressLifecycle,
  progress: UnifiedProgress | null | undefined,
  classification: JobStateClassification,
  percent?: number | null,
) {
  if (classification.missing) {
    return { label: "监控受阻", className: "badge-warning" };
  }
  if (classification.interrupted) {
    return { label: "已停止", className: "badge-warning" };
  }
  if (classification.failed) {
    return { label: percent != null ? "中断" : "失败", className: "badge-negative" };
  }
  if (classification.warning) {
    return { label: "带警告", className: "badge-warning" };
  }
  if (classification.successful) {
    return { label: "已完成", className: "badge-positive" };
  }
  if (state === "error") {
    return { label: percent != null ? "中断" : "失败", className: "badge-negative" };
  }
  if (state === "loading" || state === "progress") {
    if (isOpenEndedCloudScan(progress) && percent == null) {
      return { label: "运行中", className: "badge-info" };
    }
    if (((progress?.open_ended === true || progress?.indeterminate === true) && percent == null) || percent == null) {
      return { label: "等待中", className: "badge-warning" };
    }
    return { label: "运行中", className: "badge-info" };
  }
  return { label: "就绪", className: "badge-neutral" };
}

function progressFillClass(
  state: ProgressLifecycle,
  progress: UnifiedProgress | null | undefined,
  classification: JobStateClassification,
  stalled = false,
) {
  if (classification.warning) return "warning";
  if (classification.successful) return "positive";
  if (classification.failed || classification.interrupted || classification.missing || state === "error") return "negative";
  if (stalled || progress?.open_ended === true || progress?.indeterminate === true) return "warning";
  return "";
}

function normalizedPercent(progress?: UnifiedProgress | null, classification?: JobStateClassification): number | null {
  if (isOpenEndedCloudScan(progress)) {
    return null;
  }
  if (isCloudScanWithApiTotal(progress)) {
    return null;
  }
  const raw = progress?.percent_complete ?? progress?.percent;
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    const done = Number(progress?.done ?? progress?.checked ?? progress?.submitted ?? progress?.scanned);
    const total = Number(progress?.total);
    if (Number.isFinite(done) && Number.isFinite(total) && total > 0) return Math.max(0, Math.min(100, (done / total) * 100));
    return null;
  }
  if ((classification?.failed || classification?.interrupted || classification?.missing) && value >= 100 && !hasCompletedProgress(progress)) {
    const ratio = ratioPercent(progress);
    return ratio != null && ratio < 100 ? ratio : null;
  }
  return Math.max(0, Math.min(100, value));
}

function ratioPercent(progress?: UnifiedProgress | null) {
  const done = Number(progress?.done ?? progress?.checked ?? progress?.submitted ?? progress?.scanned);
  const total = Number(progress?.total);
  if (Number.isFinite(done) && Number.isFinite(total) && total > 0) {
    return Math.max(0, Math.min(100, (done / total) * 100));
  }
  return null;
}

function progressUserFacingError(progress?: UnifiedProgress | null) {
  const explicit = textField(progress?.user_error?.message) || textField(progress?.user_message);
  if (explicit) return explicit;
  const shared = apiErrorMessage(progress || null, "");
  if (!shared) return "";
  const rawError = textField(progress?.error);
  const rawCode = textField(progress?.error_code || progress?.status_code || progress?.user_error_kind);
  if (rawError && shared === rawError && !rawCode) return "";
  return shared;
}

function safeProgressMessage(
  progress: UnifiedProgress | null | undefined,
  state: ProgressLifecycle,
  idleText: string,
  successText: string,
) {
  if (state === "idle" || state === "error") {
    return statusText(state, idleText, successText);
  }
  const structured = textField(progress?.user_error?.message) || textField(progress?.user_message);
  if (structured) return structured;
  const safe = readableProgressStatusText(progress?.status_message || progress?.message);
  return safe || statusText(state, idleText, successText);
}

function readableProgressStatusText(raw: unknown) {
  const value = textField(raw);
  if (!value) return "";
  const labels: Record<string, string> = {
    "Official context refreshed.": "官方上下文已刷新。",
    "Status recovered.": "状态已恢复。",
  };
  if (labels[value]) return labels[value];
  if (looksLikeBackendDiagnostic(value)) return "";
  return /[\u3400-\u9fff]/.test(value) ? value : "";
}

function looksLikeBackendDiagnostic(value: string) {
  return /traceback|exception|stack|private|invalid local session|unknown job|unknown sync job/i.test(value)
    || /\b[A-Z][A-Z0-9_]{2,}\b/.test(value)
    || /[{}[\]<>]/.test(value);
}

function textField(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function hasCompletedProgress(progress?: UnifiedProgress | null) {
  return classifyProgressState("progress", progress).successful;
}

function isCloudScanWithApiTotal(progress?: UnifiedProgress | null) {
  const phase = String(progress?.phase || "").toLowerCase();
  const statusCode = String(progress?.status_code || "").toUpperCase();
  const operation = String(progress?.operation || "").toLowerCase();
  const total = scanWindowTotal(progress);
  return total > 0
    && phase === "scan"
    && (!statusCode || statusCode === "SCAN")
    && (!operation || operation === "sync_alphas" || operation === "cloud_sync");
}

function isOpenEndedCloudScan(progress?: UnifiedProgress | null) {
  if (progress?.open_ended === true || progress?.indeterminate === true) {
    return true;
  }
  const phase = String(progress?.phase || "").toLowerCase();
  const statusCode = String(progress?.status_code || "").toUpperCase();
  const operation = String(progress?.operation || "").toLowerCase();
  const scanOperation = phase === "scan"
    && (!statusCode || statusCode === "SCAN")
    && (!operation || operation === "sync_alphas" || operation === "cloud_sync");
  if (!scanOperation || hasCompletedProgress(progress)) return false;
  return true;
}

function scanCountText(progress?: UnifiedProgress | null, openEndedCloudScan = false) {
  if (progress?.scanned == null) return null;
  const scanned = Number(progress.scanned);
  if (!Number.isFinite(scanned)) return null;
  if (openEndedCloudScan) {
    return `已拉取 ${fmtCount(scanned)} 条${scanPageText(progress)}`;
  }
  const total = Number(progress.total);
  const totalText = Number.isFinite(total) && total > 0 ? fmtCount(total) : "—";
  return `已拉取 ${fmtCount(scanned)} / ${totalText} 条${scanPageText(progress)}`;
}

function openEndedScanStatusMessage(progress?: UnifiedProgress | null, fallback = "") {
  const scanned = positiveNumber(progress?.scanned);
  const total = positiveNumber(progress?.api_reported_total ?? progress?.filter_window_count);
  if (scanned <= 0) return fallback || "正在扫描云端 Alpha；等待官方接口返回第一页和接口分页参考数；首次全量同步可能需要 3-5 分钟，近 3/7 天范围通常更快。";
  if (total > 0) {
    return `已拉取 ${fmtCount(scanned)} 条云端 Alpha；接口分页参考数 ${fmtCount(total)} 条，不是云端 Alpha 总量，会继续按分页自动确认边界。`;
  }
  return `已拉取 ${fmtCount(scanned)} 条云端 Alpha；接口分页参考数仍在确认，会按分页返回继续读取。`;
}

function scanPageText(progress?: UnifiedProgress | null) {
  const page = positiveNumber(progress?.pages_fetched ?? progress?.page_number);
  const pageSize = positiveNumber(progress?.page_size);
  const pageLimit = positiveNumber(progress?.page_limit);
  const nextOffset = positiveNumber(progress?.next_offset);
  const chunks: string[] = [];
  if (page) chunks.push(`当前第 ${fmtCount(page)} 页`);
  if (pageSize) chunks.push(`本页 ${fmtCount(pageSize)} 条`);
  if (pageLimit) chunks.push(`${fmtCount(pageLimit)} 条/页`);
  if (nextOffset) chunks.push(scanNextOffsetText(progress, nextOffset));
  if (progress?.confirming_total_boundary) chunks.push("确认下一页");
  return chunks.length ? `；${chunks.join(" · ")}` : "";
}

function scanNextOffsetText(progress: UnifiedProgress | null | undefined, nextOffset: number) {
  const filterWindowCount = scanWindowTotal(progress);
  if (filterWindowCount > 0 && nextOffset >= filterWindowCount) {
    return "下一请求确认分页边界";
  }
  return "下一轮继续拉取";
}

function etaSecondsFromProgress(progress?: UnifiedProgress | null, options?: { deadlineOnly?: boolean }) {
  const deadline = Number(progress?.eta_deadline_at_ms);
  if (Number.isFinite(deadline) && deadline > 0) {
    return Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
  }
  if (options?.deadlineOnly) return 0;
  const seconds = Number(progress?.eta_seconds || 0);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
}

function estimatedEtaSeconds(progress: UnifiedProgress | null | undefined, elapsed: number, fallback: number) {
  const scanned = positiveNumber(progress?.scanned);
  const cloudScan = isOpenEndedCloudScan(progress) || isCloudScanWithApiTotal(progress);
  if (cloudScan) return 0;
  const total = positiveNumber(progress?.total);
  if (scanned > 0 && total > scanned && elapsed > 0) {
    return Math.ceil((total - scanned) / (scanned / elapsed));
  }
  return fallback > 0 ? fallback : 0;
}

function scanWindowTotal(progress?: UnifiedProgress | null) {
  return positiveNumber(progress?.api_reported_total ?? progress?.filter_window_count);
}

function statusText(state: ProgressLifecycle, idle: string, ok: string) {
  if (state === "idle") return idle;
  if (state === "success") return ok;
  if (state === "error") return "操作失败。";
  return "处理中...";
}

function displayProgressPhase(progress: UnifiedProgress | null | undefined, fallback: string) {
  const explicit = String(progress?.phase_label || "").trim();
  if (explicit) return explicit;
  const phase = String(progress?.phase || "").trim();
  if (!phase) return fallback;
  return humanPhase(phase) || "当前阶段";
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
    session_invalid: "本地会话需重新确认",
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

function fmtCount(value: number) {
  return Math.max(0, Math.trunc(value)).toLocaleString("zh-CN");
}

function positiveNumber(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : 0;
}
