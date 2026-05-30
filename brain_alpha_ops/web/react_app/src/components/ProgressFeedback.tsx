/** Unified progress and loading feedback for async operations. */

import { useEffect, useMemo, useState } from "react";
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
  state,
  title = "Progress",
  progress,
  error,
  idleText = "Ready",
  successText = "Done",
  retryLabel = "Retry",
  compact = false,
  onRetry,
}: Props) {
  const [remaining, setRemaining] = useState(() => Number(progress?.eta_seconds || 0));

  useEffect(() => {
    setRemaining(Number(progress?.eta_seconds || 0));
  }, [progress?.eta_seconds, progress?.task_id, progress?.job_id]);

  useEffect(() => {
    if (state !== "loading" && state !== "progress") return;
    if (!remaining || remaining <= 0) return;
    const timer = setInterval(() => setRemaining((value) => Math.max(0, value - 1)), 1000);
    return () => clearInterval(timer);
  }, [remaining, state]);

  const percent = useMemo(() => normalizedPercent(progress), [progress]);
  const roundedPercent = percent == null ? 0 : Math.round(percent);
  const isBusy = state === "loading" || state === "progress";
  const isDeterminate = isBusy && percent != null;
  const label = progress?.phase_label || progress?.phase || title;
  const message = progress?.status_message || progress?.message || statusText(state, idleText, successText);
  const eta = remaining > 0 ? formatDuration(remaining) : "";

  if (state === "idle" && compact) return null;

  return (
    <div
      className={`progress-feedback ${compact ? "progress-feedback-compact" : ""} ${
        state === "error" ? "is-error" : state === "success" ? "is-success" : ""
      }`}
      role={isBusy ? "status" : undefined}
      aria-live={state === "error" ? "assertive" : "polite"}
    >
      <div className="progress-feedback-header">
        <div>
          <p className="progress-feedback-title">{title}</p>
          <p className="progress-feedback-phase">{label}</p>
        </div>
        {isBusy && percent == null && <span className="progress-spinner" aria-hidden="true" />}
        {isBusy && percent != null && (
          <span className="progress-feedback-percent">{roundedPercent}%</span>
        )}
        {state === "success" && <span className="progress-feedback-done" aria-hidden="true">✓</span>}
      </div>

      {isBusy && (
        <div
          className={`progress-feedback-track ${isDeterminate ? "" : "is-indeterminate"}`}
          role="progressbar"
          aria-label={`${title}: ${label}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={isDeterminate ? roundedPercent : undefined}
        >
          <div className="progress-feedback-fill" style={isDeterminate ? { width: `${percent}%` } : undefined} />
        </div>
      )}

      <div className="progress-feedback-body">
        <span>{state === "error" ? error || progress?.error || "Operation failed." : message}</span>
        {eta && <span className="progress-feedback-eta">ETA {eta}</span>}
      </div>

      {state === "error" && onRetry && (
        <button type="button" className="btn-secondary text-sm" onClick={onRetry}>
          {retryLabel}
        </button>
      )}
    </div>
  );
}

function normalizedPercent(progress?: UnifiedProgress | null): number | null {
  const raw = progress?.percent_complete ?? progress?.percent;
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    const done = Number(progress?.done ?? progress?.checked ?? progress?.submitted ?? progress?.scanned);
    const total = Number(progress?.total);
    if (Number.isFinite(done) && Number.isFinite(total) && total > 0) {
      return Math.max(0, Math.min(100, (done / total) * 100));
    }
    return null;
  }
  return Math.max(0, Math.min(100, value));
}

function statusText(state: ProgressLifecycle, idleText: string, successText: string) {
  if (state === "idle") return idleText;
  if (state === "success") return successText;
  if (state === "error") return "Operation failed.";
  return "Working...";
}

function formatDuration(seconds: number) {
  const safe = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}
